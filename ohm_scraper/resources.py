"""Données amont de l'API v1 : appels cachés et correspondance avec le contrat.

Seuls ``OhmService.fetch_json`` touche le réseau (verrou, espacement, cache TTL).
Les réponses amont sont lues de façon tolérante : une valeur absente donne None,
jamais une valeur inventée.

Les endpoints portant ``{ct}`` ne renvoient que le contrat sélectionné côté
service (``OHM_CT`` ou contrat par défaut de la connexion). Les routes de données
refusent donc tout autre contrat (422, voir :func:`ensure_selected`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from ohm_scraper import analytics
from ohm_scraper.analytics import HalfHour
from ohm_scraper.consumption import hourly_body
from ohm_scraper.endpoints import ENDPOINTS_BY_NAME
from ohm_scraper.ids import opaque_id
from ohm_scraper.problems import unavailable, unprocessable

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
NUMBER_RE = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
USAGE_LABELS = {
    "Cooking": "cuisson",
    "Light": "éclairage",
    "ECS": "eau chaude sanitaire",
    "Other": "autres",
    "Multimedia": "multimédia",
    "BigApp": "gros électroménager",
    "EV": "véhicule électrique",
    "Pool": "piscine",
    "Heat": "chauffage",
    "HVAC": "chauffage et climatisation",
    "StandBy": "veille",
    "Cold": "froid",
}


@dataclass(frozen=True)
class ContractRef:
    """Contrat et compteur rattachés, tels que connus de l'amont. Le PDL reste interne."""

    contract_nbr: str
    pdl: str
    contract_id: str
    meter_id: str
    raw: dict[str, Any]


# ----------------------------------------------------------- lecture tolérante


def _body(payload: Any) -> Any:
    return payload.get("body") if isinstance(payload, dict) else None


def _records(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        return [body]
    return []


def _find_records(node: Any, key: str) -> list[dict[str, Any]]:
    """Tous les objets contenant ``key``, à n'importe quelle profondeur."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if key in node:
            found.append(node)
        for value in node.values():
            found.extend(_find_records(value, key))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_records(item, key))
    return found


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = NUMBER_RE.search(value.replace(" ", "").replace(" ", "").replace(",", "."))
        if match:
            return float(match.group(0))
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _date_text(value: Any) -> str | None:
    if isinstance(value, str) and DATE_RE.match(value):
        return value[:10]
    return None


def _as_date(value: Any) -> date | None:
    text = _date_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


# ------------------------------------------------------------ contrats


def contract_refs(service: Any) -> list[ContractRef]:
    """Contrats avec leur compteur (PDL), depuis la liste des contrats du compte."""
    payload = service.fetch_json("v1:contracts", ENDPOINTS_BY_NAME["contracts"])
    refs: list[ContractRef] = []
    for raw in _records(_body(payload)):
        contract_nbr = raw.get("contract_nbr")
        pdl = raw.get("pdl")
        if not contract_nbr or not pdl:
            continue
        nbr, pdl_text = str(contract_nbr), str(pdl)
        refs.append(
            ContractRef(nbr, pdl_text, opaque_id(nbr), opaque_id(pdl_text), raw)
        )
    return refs


def ensure_selected(service: Any, ref: ContractRef) -> None:
    """Refuse les routes de données pour un contrat autre que celui du service."""
    current = service.client.ct
    if not current:
        raise unavailable("Numéro de contrat inconnu côté service. Vérifiez la configuration.")
    if str(current) != ref.contract_nbr:
        raise unprocessable(
            "contract-not-selected",
            "Contrat non sélectionné",
            "Les données de consommation ne sont disponibles que pour le contrat sélectionné "
            "sur le service (OHM_CT).",
        )


def meter_view(ref: ContractRef) -> dict[str, Any]:
    raw = ref.raw
    power = _number(raw.get("subscribed_power_EL"))
    if power is not None and power.is_integer():
        power = int(power)
    return {
        "id": ref.meter_id,
        "pdl": ref.pdl,
        "subscribed_power_kva": power,
        "is_linky": bool(raw.get("linky")),
        "contract_id": ref.contract_id,
        "data_access_enabled": bool(raw.get("access_to_cons_data")),
        "start_date": _date_text(raw.get("contractual_start_date")),
    }


def contract_view(ref: ContractRef) -> dict[str, Any]:
    raw = ref.raw
    return {
        "contract_id": ref.contract_id,
        "meter_id": ref.meter_id,
        "status": _text(raw.get("contract_status")),
        "category": _text(raw.get("contract_category_NG")),
        "start_date": _date_text(raw.get("contractual_start_date")),
    }


# -------------------------------------------------------------- relevés


def hourly_day(service: Any, ref: ContractRef, day: date) -> list[HalfHour]:
    """Une requête amont par jour : courbe horaire (Wh par demi-heure)."""
    payload = service.fetch_json(
        f"v1:hourly:{ref.meter_id}:{day.isoformat()}",
        ENDPOINTS_BY_NAME["consumption_hourly"],
        hourly_body(day, ref.pdl),
    )
    return analytics.parse_hourly(day, payload)


def readings_by_day(service: Any, ref: ContractRef, days: Iterable[date]) -> dict[date, list[HalfHour]]:
    return {day: hourly_day(service, ref, day) for day in days}


def monthly_kwh(service: Any) -> dict[date, float]:
    """kWh par mois (clé : premier jour du mois), série des 6 derniers mois."""
    payload = service.fetch_json("v1:six-months", ENDPOINTS_BY_NAME["consumption_six_months"])
    monthly: dict[date, float] = {}
    for raw in _records(_body(payload)):
        day = _as_date(raw.get("date"))
        value = _number(raw.get("consumption_kWh"))
        if day is not None and value is not None:
            monthly[day.replace(day=1)] = value
    return monthly


# ------------------------------------------------------------ facturation


def invoice_view(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "invoice_id": _text(raw.get("invoice_id")),
        "invoice_number": _int(raw.get("invoice_nbr")),
        "type": _text(raw.get("invoice_type_text")),
        "period": _text(raw.get("invoicing_period")),
        "invoice_date": _date_text(raw.get("invoice_date")),
        "due_date": _date_text(raw.get("invoice_due_date")),
        "amount_eur": _number(raw.get("amount_ttc")),
        "amount_paid_eur": _number(raw.get("invoice_amount_paid")),
        "amount_due_eur": _number(raw.get("invoice_amount_due")),
        "can_download": bool(raw.get("can_download")),
    }


def invoices(service: Any) -> list[dict[str, Any]]:
    payload = service.fetch_json("v1:invoices", ENDPOINTS_BY_NAME["invoices"])
    records = _find_records(_body(payload), "invoice_nbr")
    return [invoice_view(raw) for raw in records if raw.get("invoice_id")]


def _balance_from_body(body: Any) -> float | None:
    if isinstance(body, dict):
        for key in ("balance", "solde", "amount", "montant"):
            value = _number(body.get(key))
            if value is not None:
                return value
        return None
    if isinstance(body, (int, float, str)):
        return _number(body)
    return None


def balance(service: Any, ref: ContractRef) -> dict[str, Any]:
    direct = service.fetch_json("v1:balance", ENDPOINTS_BY_NAME["balance"])
    totals = service.fetch_json("v1:balance_total", ENDPOINTS_BY_NAME["balance_total"])
    total_body = _body(totals)
    total_body = total_body if isinstance(total_body, dict) else {}
    soldes = total_body.get("soldes")
    per_contract = soldes.get(ref.contract_nbr) if isinstance(soldes, dict) else None
    balance_eur = _balance_from_body(_body(direct))
    if balance_eur is None:
        balance_eur = _number(per_contract)
    return {
        "contract_id": ref.contract_id,
        "balance_eur": balance_eur,
        "total_balance_eur": _number(total_body.get("total_sum")),
        "currency": "EUR",
    }


def tariff_view(raw: dict[str, Any]) -> dict[str, Any]:
    display = raw.get("display_name_grille")
    display = display if isinstance(display, dict) else {}
    return {
        "offer_name": _text(raw.get("offer_name")),
        "start_date": _date_text(raw.get("start_date")),
        "end_date": _date_text(raw.get("end_date")),
        "document_file_name": _text(display.get("grille_file_name")),
    }


def tariffs(service: Any) -> list[dict[str, Any]]:
    payload = service.fetch_json("v1:price_sheets", ENDPOINTS_BY_NAME["price_sheets"])
    body = _body(payload)
    if isinstance(body, dict) and "grilles_tarifaires" in body:
        body = body["grilles_tarifaires"]
    return [tariff_view(raw) for raw in _records(body)]


def breakdown(service: Any) -> list[dict[str, Any]]:
    payload = service.fetch_json("v1:usage", ENDPOINTS_BY_NAME["usage_consumption"])
    body = _body(payload)
    nilm = body.get("nilmData") if isinstance(body, dict) else None
    if not isinstance(nilm, dict):
        return []
    items: list[dict[str, Any]] = []
    for usage, value in nilm.items():
        kwh = _number(value)
        if kwh is None:
            continue
        items.append({"usage": str(usage), "label": USAGE_LABELS.get(str(usage), str(usage)), "kwh": round(kwh, 3)})
    return items
