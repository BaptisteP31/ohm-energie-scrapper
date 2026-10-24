"""Séries de consommation : dates, requêtes, mise à plat et export CSV.

Fonctions pures (aucun réseau) pour que la logique de dates, de plafond et de
conversion CSV soit testable hors ligne. Les appels HTTP sont faits par
``ohm_scraper.cli`` avec :class:`ohm_scraper.client.OhmClient`.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Any

GRANULARITIES = ("hourly", "daily", "power-days", "power-months")
# hourly et daily s'appuient sur la courbe de charge : une requête par jour, plafond dur
PER_DAY_GRANULARITIES = ("hourly", "daily")
MAX_HOURLY_DAYS = 31
POINTS_PER_DAY = 48  # demi-heures
DATE_FR = "%d/%m/%Y"

# Durée par défaut des plages (la fin par défaut est la veille : données Enedis en retard).
DAILY_DEFAULT_DAYS = 7
POWER_DAYS_DEFAULT_DAYS = 31
POWER_MONTHS_DEFAULT = 12


class ConsumptionError(ValueError):
    """Plage de dates invalide ou réponse inexploitable."""


# --------------------------------------------------------------------- dates


def parse_date(text: str) -> date:
    """Accepte ``jj/mm/aaaa`` et ``aaaa-mm-jj`` (ISO), avec espaces autour."""
    value = (text or "").strip()
    for fmt in (DATE_FR, "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ConsumptionError(f"date invalide : {text!r} (formats acceptés : jj/mm/aaaa ou aaaa-mm-jj)")


def format_date_fr(value: date) -> str:
    return value.strftime(DATE_FR)


def _months_before(value: date, months: int) -> date:
    year = value.year
    month = value.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def default_range(granularity: str, today: date | None = None) -> tuple[date, date]:
    """Plage par défaut : fin = hier, début selon la granularité."""
    if granularity not in GRANULARITIES:
        raise ConsumptionError(f"granularité inconnue : {granularity!r}")
    end = (today or date.today()) - timedelta(days=1)
    if granularity == "hourly":
        return end, end
    if granularity == "daily":
        return end - timedelta(days=DAILY_DEFAULT_DAYS - 1), end
    if granularity == "power-days":
        return end - timedelta(days=POWER_DAYS_DEFAULT_DAYS - 1), end
    return _months_before(end, POWER_MONTHS_DEFAULT - 1), end


def resolve_range(
    granularity: str,
    date_from: str | None,
    date_to: str | None,
    today: date | None = None,
) -> tuple[date, date]:
    """Applique les valeurs fournies puis valide la plage."""
    start, end = default_range(granularity, today)
    if date_from:
        start = parse_date(date_from)
    if date_to:
        end = parse_date(date_to)
    validate_range(start, end, granularity)
    return start, end


def validate_range(start: date, end: date, granularity: str) -> None:
    if start > end:
        raise ConsumptionError(
            f"plage invalide : début {format_date_fr(start)} après fin {format_date_fr(end)}"
        )
    if granularity in PER_DAY_GRANULARITIES:
        days = (end - start).days + 1
        if days > MAX_HOURLY_DAYS:
            raise ConsumptionError(
                f"plage de {days} jours : plafond dur de {MAX_HOURLY_DAYS} jours "
                "(une requête par jour). Réduisez la plage."
            )


def iter_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


# ------------------------------------------------------------------ requêtes


def extract_pdl(payload: Any) -> str | None:
    """PDL utilisé par la SPA : ``body.others.pdl`` de consumption/kwh/{ct}/data."""
    if not isinstance(payload, dict):
        return None
    body = payload.get("body")
    if not isinstance(body, dict):
        return None
    others = body.get("others")
    if not isinstance(others, dict):
        return None
    value = others.get("pdl") or others.get("prm")
    return str(value) if value else None


def hourly_body(day: date, pdl: str) -> dict[str, str]:
    return {"date": format_date_fr(day), "pdl": pdl}


def range_body(start: date, end: date) -> dict[str, str]:
    return {"startDate": format_date_fr(start), "endDate": format_date_fr(end)}


# ------------------------------------------------------------ mise à plat


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "body" in payload:
        return payload["body"]
    return payload


def _wh_to_kwh(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(value / 1000, 3)


def daily_rows(hourly: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrège les relevés demi-horaires en un total par jour (kWh)."""
    totals: dict[str, dict[str, Any]] = {}
    for row in hourly:
        day = str(row.get("date"))
        entry = totals.setdefault(day, {"date": day, "wh": 0.0, "points": 0})
        wh = row.get("wh")
        if isinstance(wh, (int, float)) and not isinstance(wh, bool):
            entry["wh"] += wh
            entry["points"] += 1
    rows: list[dict[str, Any]] = []
    for entry in totals.values():
        wh = entry["wh"]
        rows.append(
            {
                "date": entry["date"],
                "kwh": round(wh / 1000, 3),
                "wh": int(wh) if float(wh).is_integer() else wh,
                "points": entry["points"],
                "complete": entry["points"] == POINTS_PER_DAY,
            }
        )
    return rows


def hourly_rows(day: date, payload: Any) -> list[dict[str, Any]]:
    """Convertit une réponse ``consumption/kwh/.../hours`` en lignes date/time/kWh."""
    body = _unwrap(payload)
    consumptions = body.get("consumptions") if isinstance(body, dict) else None
    if not isinstance(consumptions, dict):
        return generic_rows(body)

    values = consumptions.get("data") or []
    times = consumptions.get("time") or consumptions.get("times") or []
    texts = consumptions.get("dataString") or []
    colors = consumptions.get("heuresCreuseColors") or []
    if not isinstance(values, list):
        values = []
    count = max(len(values), len(times) if isinstance(times, list) else 0)
    rows: list[dict[str, Any]] = []
    for index in range(count):
        row: dict[str, Any] = {"date": day.isoformat()}
        if isinstance(times, list) and index < len(times):
            row["time"] = times[index]
        if index < len(values):
            # La courbe de charge est en Wh par demi-heure (ex. 426 = 0,426 kWh).
            row["wh"] = values[index]
            row["kwh"] = _wh_to_kwh(values[index])
        if isinstance(texts, list) and index < len(texts):
            row["kwh_text"] = texts[index]
        if isinstance(colors, list) and index < len(colors):
            row["color"] = colors[index]
        rows.append(row)
    return rows or generic_rows(consumptions)


def generic_rows(value: Any) -> list[dict[str, Any]]:
    """Mise à plat tolérante : listes d'objets, listes parallèles ou objet simple."""
    if value is None:
        return []
    if isinstance(value, list):
        if not value:
            return []
        if all(isinstance(item, dict) for item in value):
            return [dict(item) for item in value]
        return [{"index": index, "value": item} for index, item in enumerate(value)]
    if isinstance(value, dict):
        if not value:
            return []
        for nested in value.values():
            if isinstance(nested, list) and nested and all(isinstance(item, dict) for item in nested):
                return [dict(item) for item in nested]
        arrays = {key: item for key, item in value.items() if isinstance(item, list)}
        if arrays:
            length = max(len(item) for item in arrays.values())
            rows: list[dict[str, Any]] = []
            for index in range(length):
                row = {
                    key: (items[index] if index < len(items) else None)
                    for key, items in arrays.items()
                }
                rows.append(row)
            return rows
        return [dict(value)]
    return [{"value": value}]


def flatten(granularity: str, responses: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """Met à plat les réponses : ``responses`` = liste de (date demandée, charge utile)."""
    rows: list[dict[str, Any]] = []
    for label, payload in responses:
        if granularity in PER_DAY_GRANULARITIES:
            try:
                day = date.fromisoformat(label)
            except ValueError:
                rows.extend(generic_rows(_unwrap(payload)))
            else:
                rows.extend(hourly_rows(day, payload))
        else:
            rows.extend(generic_rows(_unwrap(payload)))
    return daily_rows(rows) if granularity == "daily" else rows


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Convertit des lignes en CSV (colonnes dans l'ordre d'apparition)."""
    if not rows:
        return ""
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _cell(row.get(key)) for key in fieldnames})
    return buffer.getvalue()


def json_document(
    granularity: str,
    start: date,
    end: date,
    rows: list[dict[str, Any]],
    responses: list[tuple[str, Any]],
) -> dict[str, Any]:
    return {
        "granularity": granularity,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "rows": rows,
        "responses": [{"request": label, "payload": payload} for label, payload in responses],
    }


def render_output(
    granularity: str,
    start: date,
    end: date,
    rows: list[dict[str, Any]],
    responses: list[tuple[str, Any]],
    output_format: str,
) -> str:
    if output_format == "csv":
        return rows_to_csv(rows)
    document = json_document(granularity, start, end, rows, responses)
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"
