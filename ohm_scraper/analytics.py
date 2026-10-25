"""Calculs de consommation de l'API v1 (fonctions pures, aucun réseau).

Convention : les relevés amont sont en Wh par demi-heure. Une journée locale
(Europe/Paris) compte 48 demi-heures, 46 le jour du passage à l'heure d'été et
50 le jour du passage à l'heure d'hiver. Un jour est « complet » lorsque tous
ses points attendus sont présents.

Les positions de demi-heure sont calculées en temps absolu à partir de minuit
local, ce qui reste correct les jours de changement d'heure.
"""

from __future__ import annotations

import statistics
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
UTC = timezone.utc
POINTS_PER_DAY = 48
NIGHT_END_HOUR = 5  # la veille est mesurée entre 00 h 00 et 05 h 00
WEEKDAYS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
OFF_PEAK_COLORS = frozenset({"bleu", "bleue", "hc", "heure creuse", "heures creuses", "creuse", "off_peak"})
PEAK_COLORS = frozenset({"blanc", "blanche", "rouge", "hp", "heure pleine", "heures pleines", "pleine", "peak"})


@dataclass(frozen=True)
class HalfHour:
    """Relevé demi-heure : ``index`` est la position dans la journée locale."""

    day: date
    index: int
    wh: float
    tariff: str | None


@dataclass(frozen=True)
class DayTotal:
    day: date
    wh: float
    points: int
    expected: int

    @property
    def kwh(self) -> float:
        return round(self.wh / 1000, 3)

    @property
    def complete(self) -> bool:
        return self.points == self.expected


# ------------------------------------------------------------------ temps


def local_midnight(day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=TZ)


def slot_start(day: date, index: int) -> datetime:
    """Début de la demi-heure ``index`` de la journée locale ``day`` (heure locale)."""
    start_utc = local_midnight(day).astimezone(UTC)
    return (start_utc + timedelta(minutes=30 * index)).astimezone(TZ)


def expected_points(day: date) -> int:
    """Nombre de demi-heures de la journée locale (46, 48 ou 50)."""
    start = local_midnight(day).astimezone(UTC)
    end = local_midnight(day + timedelta(days=1)).astimezone(UTC)
    return int((end - start).total_seconds() // 1800)


def month_start(value: date) -> date:
    return value.replace(day=1)


def month_end(value: date) -> date:
    following = value.replace(day=28) + timedelta(days=4)
    return following.replace(day=1) - timedelta(days=1)


def add_months(value: date, months: int) -> date:
    """Premier jour du mois situé ``months`` mois avant (négatif) ou après ``value``."""
    index = value.year * 12 + (value.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def days_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


# ------------------------------------------------------------- relevés


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def tariff_from_color(value: Any) -> str | None:
    """Période tarifaire d'après la couleur de la courbe horaire, ou None si inconnue."""
    if not isinstance(value, str):
        return None
    text = _strip_accents(value).strip().lower()
    if text in OFF_PEAK_COLORS:
        return "off_peak"
    if text in PEAK_COLORS:
        return "peak"
    return None


def parse_hourly(day: date, payload: Any) -> list[HalfHour]:
    """Lit une réponse ``consumption/kwh/{ct}/hours`` (une journée, Wh par demi-heure)."""
    body = payload.get("body", payload) if isinstance(payload, dict) else None
    consumptions = body.get("consumptions") if isinstance(body, dict) else None
    if not isinstance(consumptions, dict):
        return []
    values = consumptions.get("data")
    if not isinstance(values, list):
        return []
    colors = consumptions.get("heuresCreuseColors")
    if not isinstance(colors, list):
        colors = []
    readings: list[HalfHour] = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue  # point manquant : jamais remplacé par une valeur inventée
        color = colors[index] if index < len(colors) else None
        readings.append(HalfHour(day, index, float(value), tariff_from_color(color)))
    return readings


def group_by_day(readings: Iterable[HalfHour]) -> dict[date, list[HalfHour]]:
    grouped: dict[date, list[HalfHour]] = {}
    for reading in readings:
        grouped.setdefault(reading.day, []).append(reading)
    return grouped


def day_totals(readings_by_day: Mapping[date, Sequence[HalfHour]]) -> dict[date, DayTotal]:
    """Total par jour. Les jours sans aucun point ne sont pas retournés."""
    totals: dict[date, DayTotal] = {}
    for day, items in readings_by_day.items():
        if items:
            totals[day] = DayTotal(day, sum(r.wh for r in items), len(items), expected_points(day))
    return totals


def _complete_totals(days: Iterable[date], totals: Mapping[date, DayTotal]) -> list[DayTotal]:
    return [totals[d] for d in sorted(set(days)) if d in totals and totals[d].complete]


# ------------------------------------------------------------- résumé


def summarize(days: Sequence[date], totals: Mapping[date, DayTotal]) -> dict[str, Any]:
    """Résumé d'une période. Seuls les jours complets alimentent moyennes et extrêmes.

    Sans aucun jour complet, les valeurs dérivées valent None (aucune valeur inventée).
    """
    unique_days = sorted(set(days))
    complete = _complete_totals(unique_days, totals)
    summary: dict[str, Any] = {
        "days_count": len(unique_days),
        "complete_days_count": len(complete),
        "total_kwh": None,
        "average_kwh_per_day": None,
        "min_day": None,
        "max_day": None,
    }
    if not complete:
        return summary
    total_wh = sum(t.wh for t in complete)
    low = min(complete, key=lambda t: t.wh)  # à égalité : le plus ancien (liste triée)
    high = max(complete, key=lambda t: t.wh)
    summary.update(
        total_kwh=round(total_wh / 1000, 3),
        average_kwh_per_day=round(total_wh / 1000 / len(complete), 2),
        min_day={"date": low.day.isoformat(), "kwh": low.kwh},
        max_day={"date": high.day.isoformat(), "kwh": high.kwh},
    )
    return summary


# -------------------------------------------------------- comparaison


def compare(current_kwh: float, reference_kwh: float) -> tuple[float, float | None]:
    """Retourne (écart en kWh, variation en % de la référence ou None si référence nulle)."""
    delta = round(current_kwh - reference_kwh, 3)
    percent = None if reference_kwh == 0 else round(delta / reference_kwh * 100, 1)
    return delta, percent


def split_complete_weeks(
    totals: Mapping[date, DayTotal], end: date, span: int = 7, lookback: int = 21
) -> tuple[list[DayTotal], list[DayTotal]] | None:
    """Les ``span`` derniers jours complets jusqu'à ``end``, et les ``span`` précédents.

    Retourne (courante, référence), chacune triée par date, ou None si la fenêtre
    de ``lookback`` jours ne contient pas assez de jours complets.
    """
    found: list[DayTotal] = []
    day = end
    earliest = end - timedelta(days=lookback - 1)
    while day >= earliest and len(found) < 2 * span:
        total = totals.get(day)
        if total is not None and total.complete:
            found.append(total)
        day -= timedelta(days=1)
    if len(found) < 2 * span:
        return None
    current = sorted(found[:span], key=lambda t: t.day)
    reference = sorted(found[span : 2 * span], key=lambda t: t.day)
    return current, reference


def kwh_of(days: Sequence[DayTotal]) -> float:
    return round(sum(t.wh for t in days) / 1000, 3)


# ------------------------------------------------------------ profil


def profile(readings_by_day: Mapping[date, Sequence[HalfHour]], totals: Mapping[date, DayTotal],
            days: Sequence[date], by: str) -> list[dict[str, Any]]:
    """Consommation moyenne par heure locale (``hour-of-day``) ou par jour (``day-of-week``).

    Pour ``hour-of-day``, une heure n'est comptée que si ses deux demi-heures sont présentes.
    Pour ``day-of-week``, seuls les jours complets sont comptés. Seules les tranches
    observées sont retournées.
    """
    if by == "hour-of-day":
        hours: dict[tuple[date, int], list[float]] = {}
        for day in sorted(set(days)):
            for reading in readings_by_day.get(day, []):
                hour = slot_start(day, reading.index).hour
                hours.setdefault((day, hour), []).append(reading.wh)
        per_hour: dict[int, list[float]] = {}
        for (_, hour), values in hours.items():
            if len(values) == 2:
                per_hour.setdefault(hour, []).append(sum(values) / 1000)
        return [
            {
                "bucket": hour,
                "label": f"{hour:02d} h",
                "average_kwh": round(statistics.fmean(samples), 3),
                "samples": len(samples),
            }
            for hour, samples in sorted(per_hour.items())
        ]

    per_weekday: dict[int, list[float]] = {}
    for total in _complete_totals(days, totals):
        per_weekday.setdefault(total.day.isoweekday(), []).append(total.kwh)
    return [
        {
            "bucket": weekday,
            "label": WEEKDAYS_FR[weekday - 1],
            "average_kwh": round(statistics.fmean(samples), 3),
            "samples": len(samples),
        }
        for weekday, samples in sorted(per_weekday.items())
    ]


# ------------------------------------------------------------ veille


def baseline(readings_by_day: Mapping[date, Sequence[HalfHour]], days: Sequence[date]) -> dict[str, Any]:
    """Médiane, sur les nuits, du relevé demi-heure minimal entre 00 h 00 et 05 h 00 (en W)."""
    nightly_minimums: list[float] = []
    for day in sorted(set(days)):
        values = [
            reading.wh
            for reading in readings_by_day.get(day, [])
            if slot_start(day, reading.index).hour < NIGHT_END_HOUR
        ]
        if values:
            nightly_minimums.append(min(values))
    if not nightly_minimums:
        return {"baseline_w": None, "nights_count": 0}
    # Wh sur une demi-heure ; multiplier par 2 donne une puissance moyenne en W.
    return {
        "baseline_w": round(statistics.median(nightly_minimums) * 2, 1),
        "nights_count": len(nightly_minimums),
    }


# ----------------------------------------------------------- anomalies


def anomalies(totals: Mapping[date, DayTotal], days: Sequence[date], threshold: float) -> dict[str, Any]:
    """Jours complets dont la consommation s'écarte de la moyenne de plus de ``threshold`` écarts-types.

    L'écart-type est calculé sur la population (``pstdev``). Sans variation (ou avec
    moins de deux jours complets), aucun jour n'est signalé.
    """
    complete = _complete_totals(days, totals)
    if not complete:
        return {"mean_kwh": None, "items": []}
    values = [t.wh / 1000 for t in complete]
    mean = statistics.fmean(values)
    spread = statistics.pstdev(values) if len(values) > 1 else 0.0
    items: list[dict[str, Any]] = []
    if spread > 0:
        for total in complete:
            z_score = (total.wh / 1000 - mean) / spread
            if abs(z_score) > threshold:
                items.append(
                    {
                        "date": total.day.isoformat(),
                        "kwh": total.kwh,
                        "mean_kwh": round(mean, 3),
                        "z_score": round(z_score, 2),
                    }
                )
    return {"mean_kwh": round(mean, 3), "items": items}


# --------------------------------------------------------- séries


def hour_series(readings_by_day: Mapping[date, Sequence[HalfHour]]) -> list[dict[str, Any]]:
    """Séries horaires (heure locale). Une heure est complète si ses 2 demi-heures sont présentes."""
    bins: dict[datetime, list[float]] = {}
    for day in sorted(readings_by_day):
        for reading in readings_by_day[day]:
            start = slot_start(day, reading.index).replace(minute=0, second=0, microsecond=0)
            bins.setdefault(start, []).append(reading.wh)
    return [
        {
            "period_start": start.isoformat(),
            "kwh": round(sum(values) / 1000, 3),
            "complete": len(values) == 2,
            "points": len(values),
        }
        for start, values in sorted(bins.items())
    ]


def day_series(totals: Mapping[date, DayTotal]) -> list[dict[str, Any]]:
    return [
        {"period_start": total.day.isoformat(), "kwh": total.kwh, "complete": total.complete, "points": total.points}
        for total in sorted(totals.values(), key=lambda t: t.day)
    ]


def week_series(totals: Mapping[date, DayTotal], start: date, end: date) -> list[dict[str, Any]]:
    """Semaines ISO (lundi). Une semaine est complète si ses 7 jours, tous complets, sont dans la plage."""
    weeks: dict[date, list[DayTotal]] = {}
    for total in totals.values():
        monday = total.day - timedelta(days=total.day.weekday())
        weeks.setdefault(monday, []).append(total)
    series = []
    for monday in sorted(weeks):
        members = {t.day: t for t in weeks[monday]}
        full_week = [monday + timedelta(days=offset) for offset in range(7)]
        covered = start <= monday and monday + timedelta(days=6) <= end
        complete = covered and all(d in members and members[d].complete for d in full_week)
        series.append(
            {
                "period_start": monday.isoformat(),
                "kwh": round(sum(t.wh for t in members.values()) / 1000, 3),
                "complete": complete,
                "points": sum(t.points for t in members.values()),
            }
        )
    return series


def month_series(
    monthly: Mapping[date, float], start: date, end: date, today: date
) -> list[dict[str, Any]]:
    """Séries mensuelles issues de la série des 6 derniers mois (kWh par mois).

    Un mois est complet s'il est terminé depuis au moins 2 jours. Les points ne sont
    alors connus que par le nombre de jours du mois (48 par jour). Sinon ``points`` vaut 0.
    """
    series = []
    for first in sorted(monthly):
        last = month_end(first)
        if last < start or first > end:
            continue
        complete = last <= today - timedelta(days=2)
        days = (last - first).days + 1
        series.append(
            {
                "period_start": first.isoformat(),
                "kwh": round(monthly[first], 3),
                "complete": complete,
                "points": POINTS_PER_DAY * days if complete else 0,
            }
        )
    return series
