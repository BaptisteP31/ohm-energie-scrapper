"""Routes /v1 de l'API en lecture seule (contrat docs/openapi.yaml).

``handle`` ne fait ni HTTP ni authentification : le handler de ``server.py``
s'en charge. Les erreurs sont levées sous forme d':class:`ApiProblem`.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from ohm_scraper import analytics, resources
from ohm_scraper.ids import is_opaque_id
from ohm_scraper.problems import ApiProblem, invalid_parameter, not_found, unprocessable

API_VERSION = "1.0.0"
DELAY_NOTICE = "Les relevés sont disponibles avec un délai de 24 à 48 h."
BASELINE_METHOD = (
    "Médiane, sur les nuits de la plage, du relevé demi-heure minimal entre 00 h 00 et 05 h 00, "
    "converti en W (wh * 2)."
)
MAX_RANGE_DAYS = 31
MIN_ANOMALY_DAYS = 7
MAX_LIMIT = 500
DEFAULT_LIMIT = 100
DEFAULT_THRESHOLD = 2.0
MIN_THRESHOLD = 1.0
SIX_MONTHS = 6
GRANULARITIES = ("hour", "day", "week", "month")
SUMMARY_PERIODS = ("yesterday", "last-7-days", "last-30-days", "last-month")
COMPARISON_PERIODS = ("week", "month")
PROFILE_BY = ("hour-of-day", "day-of-week")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
INT_RE = re.compile(r"[+-]?\d+")
FLOAT_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
CSV_COLUMNS = ("timestamp", "wh", "kwh", "tariff_period")


@dataclass
class Reply:
    status: int
    body: bytes
    content_type: str
    headers: dict[str, str] = field(default_factory=dict)


def _json_reply(data: Any, headers: dict[str, str] | None = None) -> Reply:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return Reply(200, payload, "application/json; charset=utf-8", dict(headers or {}))


def _meta() -> dict[str, Any]:
    return {"source": "ohm", "computed": True, "delay_notice": DELAY_NOTICE}


def _wh(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


@dataclass
class Request:
    service: Any
    path: str
    query: dict[str, list[str]]
    accept: str
    today: date

    def raw(self, name: str) -> str | None:
        values = self.query.get(name)
        return values[0] if values else None

    def _missing(self, name: str) -> ApiProblem:
        return invalid_parameter(f"Le paramètre '{name}' est requis.")

    def required(self, name: str) -> str:
        value = self.raw(name)
        if value is None or not value.strip():
            raise self._missing(name)
        return value.strip()

    def date_param(self, name: str) -> date:
        value = self.required(name)
        if DATE_RE.fullmatch(value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise invalid_parameter(f"Le paramètre '{name}' doit être une date au format YYYY-MM-DD.")

    def enum_param(self, name: str, choices: tuple[str, ...], default: str | None = None) -> str:
        value = self.raw(name)
        if value is None:
            if default is None:
                raise self._missing(name)
            return default
        if value not in choices:
            raise invalid_parameter(f"Le paramètre '{name}' doit valoir : {', '.join(choices)}.")
        return value

    def int_param(self, name: str, default: int, minimum: int, maximum: int) -> int:
        value = self.raw(name)
        if value is None:
            return default
        if not INT_RE.fullmatch(value.strip()):
            raise invalid_parameter(f"Le paramètre '{name}' doit être un entier.")
        number = int(value)
        if not minimum <= number <= maximum:
            raise unprocessable(
                "parameter-out-of-range", "Paramètre hors limites",
                f"Le paramètre '{name}' doit être compris entre {minimum} et {maximum}.",
            )
        return number

    def float_param(self, name: str, default: float, minimum: float) -> float:
        value = self.raw(name)
        if value is None:
            return default
        if not FLOAT_RE.fullmatch(value.strip()):
            raise invalid_parameter(f"Le paramètre '{name}' doit être un nombre.")
        number = float(value)
        if not math.isfinite(number) or number < minimum:
            raise unprocessable(
                "parameter-out-of-range", "Paramètre hors limites",
                f"Le paramètre '{name}' doit être supérieur ou égal à {minimum}.",
            )
        return number

    def range(self, max_days: int | None = MAX_RANGE_DAYS, min_days: int = 1) -> tuple[date, date]:
        start = self.date_param("from")
        end = self.date_param("to")
        if start > end:
            raise unprocessable(
                "range-invalid", "Plage invalide", "'from' doit être antérieur ou égal à 'to'."
            )
        span = (end - start).days + 1
        if max_days is not None and span > max_days:
            raise unprocessable(
                "range-too-long", "Plage trop longue",
                f"La plage demandée dépasse {max_days} jours. Découpez la requête.",
            )
        if span < min_days:
            raise unprocessable(
                "range-too-short", "Plage trop courte",
                f"La plage doit comporter au moins {min_days} jours.",
            )
        return start, end

    def days(self, start: date, end: date) -> list[date]:
        """Jours de la plage, sans les jours futurs (aucun relevé possible)."""
        return [day for day in analytics.days_between(start, end) if day <= self.today]

    def page_params(self) -> tuple[int, int]:
        page = self.int_param("page", 1, 1, 10**9)
        limit = self.int_param("limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        return page, limit

    def link_header(self, page: int, limit: int, total_pages: int) -> str:
        base = {key: values[0] for key, values in self.query.items() if key not in ("page", "limit")}

        def url(target: int) -> str:
            return f"{self.path}?{urlencode({**base, 'page': target, 'limit': limit})}"

        links = [f'<{url(1)}>; rel="first"', f'<{url(max(total_pages, 1))}>; rel="last"']
        if page > 1:
            links.append(f'<{url(page - 1)}>; rel="prev"')
        if page < total_pages:
            links.append(f'<{url(page + 1)}>; rel="next"')
        return ", ".join(links)


def _paginate(req: Request, items: list[Any], page: int, limit: int) -> tuple[list[Any], dict[str, Any], str]:
    total_pages = math.ceil(len(items) / limit)
    window = items[(page - 1) * limit : page * limit]
    pagination = {
        "page": page,
        "limit": limit,
        "total_items": len(items),
        "total_pages": total_pages,
        "has_next": page < total_pages,
    }
    return window, pagination, req.link_header(page, limit, total_pages)


# ------------------------------------------------------- identifiants


def _check_id(value: str, label: str) -> None:
    if not is_opaque_id(value):
        raise invalid_parameter(
            f"Le paramètre '{label}' doit être un identifiant de 12 caractères hexadécimaux."
        )


def _meter_ref(req: Request, meter_id: str) -> resources.ContractRef:
    _check_id(meter_id, "meterId")
    for ref in resources.contract_refs(req.service):
        if ref.meter_id == meter_id:
            return ref
    raise not_found("Aucun compteur ne correspond à cet identifiant.")


def _data_meter_ref(req: Request, meter_id: str) -> resources.ContractRef:
    ref = _meter_ref(req, meter_id)
    resources.ensure_selected(req.service, ref)
    return ref


def _contract_ref(req: Request, contract_id: str) -> resources.ContractRef:
    _check_id(contract_id, "contractId")
    for ref in resources.contract_refs(req.service):
        if ref.contract_id == contract_id:
            return ref
    raise not_found("Aucun contrat ne correspond à cet identifiant.")


# ------------------------------------------------------------ système


def _status(req: Request) -> Reply:
    service = req.service
    last = service.last_successful_call_at
    return _json_reply(
        {
            "service": {"version": API_VERSION},
            "upstream": {
                "login_state": service.login_state,
                "last_successful_call_at": last.isoformat() if last else None,
            },
            "cache": {"ttl_seconds": service.config.cache_ttl},
        }
    )


# ----------------------------------------------------- compteurs / contrats


def _list_meters(req: Request) -> Reply:
    refs = resources.contract_refs(req.service)
    return _json_reply({"items": [resources.meter_view(ref) for ref in refs]})


def _get_meter(req: Request, meter_id: str) -> Reply:
    return _json_reply(resources.meter_view(_meter_ref(req, meter_id)))


def _list_contracts(req: Request) -> Reply:
    refs = resources.contract_refs(req.service)
    return _json_reply({"items": [resources.contract_view(ref) for ref in refs]})


# ---------------------------------------------------------------- relevés


def _readings(req: Request, meter_id: str) -> Reply:
    ref = _data_meter_ref(req, meter_id)
    page, limit = req.page_params()
    start, end = req.range()
    grouped = resources.readings_by_day(req.service, ref, req.days(start, end))
    readings = [item for day in sorted(grouped) for item in grouped[day]]
    rows = [
        {
            "timestamp": analytics.slot_start(item.day, item.index).isoformat(),
            "wh": _wh(item.wh),
            "kwh": round(item.wh / 1000, 3),
            "tariff_period": item.tariff,
        }
        for item in readings
    ]
    window, pagination, link = _paginate(req, rows, page, limit)
    headers = {"Link": link}
    if "text/csv" in req.accept.lower():
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for row in window:
            writer.writerow([row["timestamp"], row["wh"], row["kwh"], row["tariff_period"] or ""])
        return Reply(200, buffer.getvalue().encode("utf-8"), "text/csv; charset=utf-8", headers)
    return _json_reply({"items": window, "pagination": pagination}, headers)


# ------------------------------------------------------------ consommation


def _consumption(req: Request, meter_id: str) -> Reply:
    granularity = req.enum_param("granularity", GRANULARITIES, default="day")
    if granularity == "month":
        start, end = req.range(max_days=None)
        earliest = analytics.add_months(req.today.replace(day=1), -(SIX_MONTHS - 1))
        if start < earliest:
            raise unprocessable(
                "outside-window", "Période hors fenêtre",
                "La granularité 'month' n'est disponible que pour les 6 derniers mois.",
            )
        _data_meter_ref(req, meter_id)
        items = analytics.month_series(resources.monthly_kwh(req.service), start, end, req.today)
        return _json_reply({"meta": _meta(), "items": items})

    ref = _data_meter_ref(req, meter_id)
    start, end = req.range()
    grouped = resources.readings_by_day(req.service, ref, req.days(start, end))
    if granularity == "hour":
        items = analytics.hour_series(grouped)
    else:
        totals = analytics.day_totals(grouped)
        if granularity == "day":
            items = analytics.day_series(totals)
        else:
            items = analytics.week_series(totals, start, end)
    return _json_reply({"meta": _meta(), "items": items})


def _summary_window(period: str, today: date) -> tuple[date, date]:
    yesterday = today - timedelta(days=1)
    if period == "yesterday":
        return yesterday, yesterday
    if period == "last-7-days":
        return today - timedelta(days=7), yesterday
    if period == "last-30-days":
        return today - timedelta(days=30), yesterday
    last_month_end = today.replace(day=1) - timedelta(days=1)
    return last_month_end.replace(day=1), last_month_end


def _summary(req: Request, meter_id: str) -> Reply:
    period = req.enum_param("period", SUMMARY_PERIODS)
    ref = _data_meter_ref(req, meter_id)
    start, end = _summary_window(period, req.today)
    days = analytics.days_between(start, end)
    totals = analytics.day_totals(resources.readings_by_day(req.service, ref, days))
    return _json_reply({"meta": _meta(), "period": period, **analytics.summarize(days, totals)})


def _against(req: Request) -> str:
    value = req.required("against")
    if value == "previous":
        return value
    if value == "last-year":
        raise unprocessable(
            "unsupported-value", "Valeur non supportée",
            "'against=last-year' n'est pas supporté. Utilisez 'previous'.",
        )
    raise invalid_parameter("Le paramètre 'against' doit valoir : previous.")


def _comparison(req: Request, meter_id: str) -> Reply:
    period = req.enum_param("period", COMPARISON_PERIODS)
    against = _against(req)
    insufficient = unprocessable(
        "insufficient-data", "Données insuffisantes",
        "Pas assez de données complètes pour cette comparaison.",
    )
    if period == "week":
        ref = _data_meter_ref(req, meter_id)
        yesterday = req.today - timedelta(days=1)
        days = analytics.days_between(req.today - timedelta(days=21), yesterday)
        totals = analytics.day_totals(resources.readings_by_day(req.service, ref, days))
        split = analytics.split_complete_weeks(totals, yesterday)
        if split is None:
            raise insufficient
        current_days, reference_days = split
        current = {
            "from": current_days[0].day.isoformat(),
            "to": current_days[-1].day.isoformat(),
            "kwh": analytics.kwh_of(current_days),
        }
        reference = {
            "from": reference_days[0].day.isoformat(),
            "to": reference_days[-1].day.isoformat(),
            "kwh": analytics.kwh_of(reference_days),
        }
    else:
        _data_meter_ref(req, meter_id)
        monthly = resources.monthly_kwh(req.service)
        current_start = analytics.add_months(req.today.replace(day=1), -1)
        reference_start = analytics.add_months(current_start, -1)
        if current_start not in monthly or reference_start not in monthly:
            raise insufficient
        current = {
            "from": current_start.isoformat(),
            "to": analytics.month_end(current_start).isoformat(),
            "kwh": round(monthly[current_start], 3),
        }
        reference = {
            "from": reference_start.isoformat(),
            "to": analytics.month_end(reference_start).isoformat(),
            "kwh": round(monthly[reference_start], 3),
        }
    delta, percent = analytics.compare(current["kwh"], reference["kwh"])
    return _json_reply(
        {
            "meta": _meta(),
            "period": period,
            "against": against,
            "current": current,
            "reference": reference,
            "delta_kwh": delta,
            "delta_percent": percent,
        }
    )


def _profile(req: Request, meter_id: str) -> Reply:
    by = req.enum_param("by", PROFILE_BY)
    start, end = req.range()
    ref = _data_meter_ref(req, meter_id)
    days = req.days(start, end)
    readings = resources.readings_by_day(req.service, ref, days)
    totals = analytics.day_totals(readings)
    items = analytics.profile(readings, totals, days, by)
    return _json_reply(
        {"meta": _meta(), "by": by, "from": start.isoformat(), "to": end.isoformat(), "items": items}
    )


def _baseline(req: Request, meter_id: str) -> Reply:
    start, end = req.range()
    ref = _data_meter_ref(req, meter_id)
    days = req.days(start, end)
    result = analytics.baseline(resources.readings_by_day(req.service, ref, days), days)
    return _json_reply(
        {
            "meta": _meta(),
            "from": start.isoformat(),
            "to": end.isoformat(),
            "baseline_w": result["baseline_w"],
            "nights_count": result["nights_count"],
            "method": BASELINE_METHOD,
        }
    )


def _anomalies(req: Request, meter_id: str) -> Reply:
    threshold = req.float_param("threshold", DEFAULT_THRESHOLD, MIN_THRESHOLD)
    start, end = req.range(min_days=MIN_ANOMALY_DAYS)
    ref = _data_meter_ref(req, meter_id)
    days = req.days(start, end)
    readings = resources.readings_by_day(req.service, ref, days)
    result = analytics.anomalies(analytics.day_totals(readings), days, threshold)
    return _json_reply(
        {
            "meta": _meta(),
            "from": start.isoformat(),
            "to": end.isoformat(),
            "threshold": threshold,
            "mean_kwh": result["mean_kwh"],
            "items": result["items"],
        }
    )


def _breakdown(req: Request, meter_id: str) -> Reply:
    _data_meter_ref(req, meter_id)
    return _json_reply(
        {"estimated": True, "source": "ohm", "items": resources.breakdown(req.service)}
    )


# ------------------------------------------------------------ facturation


def _invoices(req: Request, contract_id: str) -> Reply:
    page, limit = req.page_params()
    ref = _contract_ref(req, contract_id)
    resources.ensure_selected(req.service, ref)
    window, pagination, link = _paginate(req, resources.invoices(req.service), page, limit)
    return _json_reply({"items": window, "pagination": pagination}, {"Link": link})


def _invoice(req: Request, contract_id: str, invoice_id: str) -> Reply:
    if not 1 <= len(invoice_id) <= 64:
        raise invalid_parameter("Le paramètre 'invoiceId' doit comporter entre 1 et 64 caractères.")
    ref = _contract_ref(req, contract_id)
    resources.ensure_selected(req.service, ref)
    for item in resources.invoices(req.service):
        if item["invoice_id"] == invoice_id:
            return _json_reply(item)
    raise not_found("Aucune facture ne correspond à cet identifiant.")


def _balance(req: Request, contract_id: str) -> Reply:
    ref = _contract_ref(req, contract_id)
    resources.ensure_selected(req.service, ref)
    return _json_reply(resources.balance(req.service, ref))


def _tariffs(req: Request, contract_id: str) -> Reply:
    ref = _contract_ref(req, contract_id)
    resources.ensure_selected(req.service, ref)
    return _json_reply({"items": resources.tariffs(req.service)})


# ------------------------------------------------------------- routage

Handler = Callable[..., Reply]
_M = r"/v1/meters/(?P<meter_id>[^/]+)"
_C = r"/v1/contracts/(?P<contract_id>[^/]+)"
_ROUTES: tuple[tuple[re.Pattern[str], Handler], ...] = tuple(
    (re.compile(pattern), handler)
    for pattern, handler in (
        (r"/v1/status", _status),
        (r"/v1/meters", _list_meters),
        (_M, _get_meter),
        (_M + r"/readings", _readings),
        (_M + r"/consumption", _consumption),
        (_M + r"/consumption/summary", _summary),
        (_M + r"/consumption/comparison", _comparison),
        (_M + r"/consumption/profile", _profile),
        (_M + r"/consumption/baseline", _baseline),
        (_M + r"/consumption/anomalies", _anomalies),
        (_M + r"/consumption/breakdown", _breakdown),
        (r"/v1/contracts", _list_contracts),
        (_C + r"/invoices", _invoices),
        (_C + r"/invoices/(?P<invoice_id>[^/]+)", _invoice),
        (_C + r"/balance", _balance),
        (_C + r"/tariffs", _tariffs),
    )
)


def handle(
    service: Any,
    method: str,
    path: str,
    query: dict[str, list[str]],
    accept: str = "",
    today: date | None = None,
) -> Reply:
    """Traite une requête /v1 déjà authentifiée. Lève :class:`ApiProblem` en cas d'erreur."""
    if method != "GET":
        raise ApiProblem(
            405, "method-not-allowed", "Méthode non autorisée",
            f"Méthode {method} non autorisée. Seul GET est supporté.", {"Allow": "GET"},
        )
    for pattern, handler in _ROUTES:
        match = pattern.fullmatch(path)
        if match is None:
            continue
        req = Request(service, path, query, accept, today or service.today())
        return handler(req, **match.groupdict())
    raise ApiProblem(404, "route-not-found", "Route introuvable", "Aucune route ne correspond à ce chemin.")
