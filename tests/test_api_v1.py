"""Tests des routes /v1 (données synthétiques, client amont factice, aucun réseau)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

import pytest

from ohm_scraper import api_v1, consumption
from ohm_scraper.config import Config
from ohm_scraper.ids import opaque_id
from ohm_scraper.problems import ApiProblem
from ohm_scraper.server import OhmService, create_server
from tests.fakes import (
    SYNTH_CT,
    SYNTH_PDL,
    SYNTH_SECOND_CT,
    SYNTH_SECOND_PDL,
    FakeResponse,
    RoutedClient,
    hourly_payload,
    synthetic_day_values,
)

TODAY = date(2026, 10, 24)
METER_ID = opaque_id(SYNTH_PDL)
CONTRACT_ID = opaque_id(SYNTH_CT)
SECOND_METER_ID = opaque_id(SYNTH_SECOND_PDL)
SECOND_CONTRACT_ID = opaque_id(SYNTH_SECOND_CT)
INVOICE_ID = "INV-SYNTH-0003"
EMPTY_DAYS: set[date] = set()


def _contract(nbr: str, pdl: str, power: str = "6") -> dict[str, Any]:
    return {
        "customer_nbr": "CM-SYNTH",
        "contract_nbr": nbr,
        "pdl": pdl,
        "subscribed_power_EL": power,
        "linky": True,
        "access_to_cons_data": True,
        "contract_status": "active",
        "contract_category_NG": "Résidentiel",
        "contractual_start_date": "2026-01-12",
        "solde": 84.2,
    }


def _invoice(number: int) -> dict[str, Any]:
    return {
        "invoice_nbr": f"202609310{number}",
        "invoice_type_text": "Facture de régularisation",
        "invoicing_period": "Octobre 2026",
        "invoice_date": "2026-10-01",
        "invoice_due_date": "2026-10-20",
        "amount_ttc": f"84,{number}0",
        "invoice_amount_paid": "0,00",
        "invoice_amount_due": f"84,{number}0",
        "invoice_id": f"INV-SYNTH-000{number}",
        "invoice_type_hgz": "X",
        "contract_nbr": SYNTH_CT,
        "can_download": True,
    }


def synthetic_responses() -> dict[str, Any]:
    six_months = [
        {"date": "2026-05-01", "consumption_kWh": 90.0},
        {"date": "2026-06-01", "consumption_kWh": 85.0},
        {"date": "2026-07-01", "consumption_kWh": 70.0},
        {"date": "2026-08-01", "consumption_kWh": 320.0},
        {"date": "2026-09-01", "consumption_kWh": 300.0},
        {"date": "2026-10-01", "consumption_kWh": 75.0},
    ]
    return {
        "contracts": {
            "success": True,
            "meta": {"status": 200, "message": ""},
            "body": [_contract(SYNTH_CT, SYNTH_PDL), _contract(SYNTH_SECOND_CT, SYNTH_SECOND_PDL, "9")],
        },
        "consumption_six_months": {"success": True, "body": six_months},
        "invoices": {
            "success": True,
            "body": [3, [_invoice(1), _invoice(2), _invoice(3)], "métadonnée"],
        },
        "balance": {"success": True, "body": []},
        "balance_total": {"success": True, "body": {"soldes": {SYNTH_CT: 84.2}, "total_sum": "84,20"}},
        "price_sheets": {
            "success": True,
            "body": {
                "grilles_tarifaires": [
                    {
                        "offer_name": "Offre synthétique",
                        "start_date": "2026-01-12",
                        "end_date": None,
                        "display_name_grille": {"grille_month": "janvier", "grille_file_name": "grille-synth.pdf"},
                    }
                ]
            },
        },
        "usage_consumption": {
            "success": True,
            "body": {"nilmData": {"Heat": 3120, "Cooking": 310, "StandBy": 95.5}, "defaultNilm": True},
        },
    }


def hourly_handler(empty_days: set[date] | None = None):
    empty = empty_days or set()

    def handler(body: dict[str, Any]) -> dict[str, Any]:
        day = consumption.parse_date(body["date"])
        if day in empty:
            return hourly_payload([])
        return hourly_payload(synthetic_day_values(day))

    return handler


def make_client(empty_days: set[date] | None = None, **responses: Any) -> RoutedClient:
    data = synthetic_responses()
    data.update(responses)
    return RoutedClient(data, hourly=hourly_handler(empty_days))


def make_service(client: Any, *, api_token: str | None = None, cache_ttl: int = 900) -> OhmService:
    config = Config(
        login="synthetic@example.test",
        password="synthetic-password",
        customer_number=None,
        api_base="https://example.invalid",
        ct=None,
        api_token=api_token,
        cache_ttl=cache_ttl,
    )
    service = OhmService(config, client=client)
    service.today = lambda: TODAY  # horloge figée
    return service


def call(service: OhmService, path: str, query: str = "", accept: str = "") -> api_v1.Reply:
    parsed = urllib.parse.parse_qs(query, keep_blank_values=True)
    return api_v1.handle(service, "GET", path, parsed, accept=accept)


def body_of(reply: api_v1.Reply) -> Any:
    return json.loads(reply.body.decode("utf-8"))


def expected_kwh(day: date) -> float:
    return round(sum(synthetic_day_values(day)) / 1000, 3)


def problem_of(callable_, *args, **kwargs) -> ApiProblem:
    with pytest.raises(ApiProblem) as info:
        callable_(*args, **kwargs)
    return info.value


METER = f"/v1/meters/{METER_ID}"


# ------------------------------------------------------- compteurs et contrats


def test_meters_list_and_get_use_opaque_ids() -> None:
    service = make_service(make_client())
    items = body_of(call(service, "/v1/meters"))["items"]
    assert [item["id"] for item in items] == [METER_ID, SECOND_METER_ID]
    first = items[0]
    assert first["pdl"] == SYNTH_PDL
    assert first["contract_id"] == CONTRACT_ID
    assert first["subscribed_power_kva"] == 6
    assert first["is_linky"] is True and first["data_access_enabled"] is True
    assert first["start_date"] == "2026-01-12"
    assert body_of(call(service, METER)) == first


def test_opaque_id_is_first_twelve_hex_chars_of_sha256() -> None:
    assert METER_ID == hashlib.sha256(SYNTH_PDL.encode()).hexdigest()[:12]
    assert CONTRACT_ID == hashlib.sha256(SYNTH_CT.encode()).hexdigest()[:12]


def test_unknown_meter_id_is_404_and_malformed_is_400() -> None:
    service = make_service(make_client())
    unknown = problem_of(call, service, "/v1/meters/000000000000")
    assert (unknown.status, unknown.slug) == (404, "not-found")
    malformed = problem_of(call, service, "/v1/meters/ABC")
    assert malformed.status == 400
    assert malformed.slug == "invalid-parameter"
    assert SYNTH_PDL not in malformed.detail


def test_contracts_list_hides_contract_number_and_pdl() -> None:
    service = make_service(make_client())
    reply = call(service, "/v1/contracts")
    text = reply.body.decode("utf-8")
    assert SYNTH_CT not in text and SYNTH_PDL not in text
    items = body_of(reply)["items"]
    assert items[0] == {
        "contract_id": CONTRACT_ID,
        "meter_id": METER_ID,
        "status": "active",
        "category": "Résidentiel",
        "start_date": "2026-01-12",
    }


def test_status_reports_login_and_last_successful_call() -> None:
    client = make_client()
    service = make_service(client, cache_ttl=300)
    before = body_of(call(service, "/v1/status"))
    assert before["upstream"] == {"login_state": "unknown", "last_successful_call_at": None}
    call(service, "/v1/meters")
    after = body_of(call(service, "/v1/status"))
    assert after["upstream"]["login_state"] == "logged_in"
    assert after["upstream"]["last_successful_call_at"]
    assert after["cache"] == {"ttl_seconds": 300}
    assert after["service"] == {"version": "1.0.0"}


def test_upstream_cache_avoids_second_call() -> None:
    client = make_client()
    service = make_service(client)
    call(service, "/v1/meters")
    calls = len(client.calls)
    call(service, "/v1/meters")
    assert len(client.calls) == calls
    assert client.login_count == 1


# ------------------------------------------------------------- relevés


def test_readings_paginate_with_link_header() -> None:
    service = make_service(make_client())
    query = "from=2026-10-20&to=2026-10-21&limit=50&page=2"
    reply = call(service, f"{METER}/readings", query)
    body = body_of(reply)
    assert body["pagination"] == {
        "page": 2, "limit": 50, "total_items": 96, "total_pages": 2, "has_next": False,
    }
    assert len(body["items"]) == 46
    # Page 2 commence au 50e relevé : 48 relevés du 20/10, puis le 21/10 à 01 h 00 (2e demi-heure).
    assert body["items"][0]["timestamp"] == "2026-10-21T01:00:00+02:00"
    assert set(body["items"][0]) == {"timestamp", "wh", "kwh", "tariff_period"}
    link = reply.headers["Link"]
    assert 'rel="prev"' in link and 'rel="first"' in link and 'rel="last"' in link
    assert 'rel="next"' not in link
    assert "page=1" in link and "from=2026-10-20" in link


def test_readings_first_page_has_next_and_tariffs() -> None:
    service = make_service(make_client())
    reply = call(service, f"{METER}/readings", "from=2026-10-20&to=2026-10-20&limit=30")
    body = body_of(reply)
    assert body["pagination"]["has_next"] is True
    assert body["items"][0]["timestamp"] == "2026-10-20T00:00:00+02:00"
    assert body["items"][0]["tariff_period"] == "off_peak"
    assert body["items"][20]["tariff_period"] == "peak"
    assert 'rel="next"' in reply.headers["Link"]


def test_readings_csv_export_on_accept_header() -> None:
    service = make_service(make_client())
    reply = call(service, f"{METER}/readings", "from=2026-10-20&to=2026-10-20&limit=3", accept="text/csv")
    assert reply.content_type.startswith("text/csv")
    rows = list(csv.reader(io.StringIO(reply.body.decode("utf-8"))))
    assert rows[0] == ["timestamp", "wh", "kwh", "tariff_period"]
    assert len(rows) == 4
    assert rows[1][0] == "2026-10-20T00:00:00+02:00"
    assert float(rows[1][2]) == round(synthetic_day_values(date(2026, 10, 20))[0] / 1000, 3)
    assert rows[1][3] == "off_peak"


def test_readings_validation_errors() -> None:
    service = make_service(make_client())
    assert problem_of(call, service, f"{METER}/readings", "to=2026-10-20").status == 400
    assert problem_of(call, service, f"{METER}/readings", "from=2026-13-01&to=2026-10-20").status == 400
    assert problem_of(call, service, f"{METER}/readings", "from=20-10-2026&to=2026-10-20").status == 400
    inverted = problem_of(call, service, f"{METER}/readings", "from=2026-10-20&to=2026-10-19")
    assert (inverted.status, inverted.slug) == (422, "range-invalid")
    too_long = problem_of(call, service, f"{METER}/readings", "from=2026-09-01&to=2026-10-02")
    assert (too_long.status, too_long.slug) == (422, "range-too-long")
    assert problem_of(call, service, f"{METER}/readings", "from=2026-10-01&to=2026-10-02&limit=abc").status == 400
    assert problem_of(call, service, f"{METER}/readings", "from=2026-10-01&to=2026-10-02&limit=501").status == 422
    assert problem_of(call, service, f"{METER}/readings", "from=2026-10-01&to=2026-10-02&page=0").status == 422


def test_readings_skip_future_days_and_missing_data() -> None:
    client = make_client(empty_days={date(2026, 10, 23)})
    service = make_service(client)
    body = body_of(call(service, f"{METER}/readings", "from=2026-10-23&to=2026-10-30"))
    # 23/10 sans donnée (rien inventé), 24/10 (aujourd'hui) partiel, 25 à 30 non interrogés.
    assert body["pagination"]["total_items"] == 48
    assert body["items"][0]["timestamp"] == "2026-10-24T00:00:00+02:00"
    hourly_days = [consumption.parse_date(b["date"]) for b in client.hourly_calls()]
    assert hourly_days == [date(2026, 10, 23), date(2026, 10, 24)]  # aucun appel pour les jours futurs


def test_readings_request_one_upstream_call_per_day() -> None:
    client = make_client()
    service = make_service(client)
    call(service, f"{METER}/readings", "from=2026-10-20&to=2026-10-22")
    assert [b["date"] for b in client.hourly_calls()] == ["20/10/2026", "21/10/2026", "22/10/2026"]
    assert all(b["pdl"] == SYNTH_PDL for b in client.hourly_calls())


# ---------------------------------------------------------- consommation


def test_consumption_day_and_week_series() -> None:
    service = make_service(make_client())
    days = body_of(call(service, f"{METER}/consumption", "from=2026-10-12&to=2026-10-13"))
    assert days["meta"] == {
        "source": "ohm", "computed": True, "delay_notice": api_v1.DELAY_NOTICE,
    }
    assert [item["period_start"] for item in days["items"]] == ["2026-10-12", "2026-10-13"]
    first = days["items"][0]
    assert first["kwh"] == expected_kwh(date(2026, 10, 12))
    assert first["complete"] is True and first["points"] == 48

    week = body_of(call(service, f"{METER}/consumption", "from=2026-10-05&to=2026-10-11&granularity=week"))
    assert week["items"][0]["period_start"] == "2026-10-05"
    assert week["items"][0]["complete"] is True
    assert week["items"][0]["kwh"] == round(sum(expected_kwh(date(2026, 10, d)) for d in range(5, 12)), 3)


def test_consumption_hour_series_has_two_points_per_hour() -> None:
    service = make_service(make_client())
    body = body_of(call(service, f"{METER}/consumption", "from=2026-10-12&to=2026-10-12&granularity=hour"))
    assert len(body["items"]) == 24
    assert body["items"][0]["period_start"] == "2026-10-12T00:00:00+02:00"
    assert body["items"][0]["points"] == 2 and body["items"][0]["complete"] is True


def test_consumption_month_from_six_months_series() -> None:
    client = make_client()
    service = make_service(client)
    body = body_of(call(service, f"{METER}/consumption", "from=2026-08-01&to=2026-10-31&granularity=month"))
    periods = {item["period_start"]: item for item in body["items"]}
    assert periods["2026-08-01"]["kwh"] == 320.0
    assert periods["2026-08-01"]["complete"] is True
    assert periods["2026-10-01"]["complete"] is False and periods["2026-10-01"]["points"] == 0
    assert client.hourly_calls() == []  # la granularité mois ne passe pas par la courbe horaire


def test_consumption_month_outside_window_is_422() -> None:
    service = make_service(make_client())
    error = problem_of(call, service, f"{METER}/consumption", "from=2025-01-01&to=2025-02-01&granularity=month")
    assert (error.status, error.slug) == (422, "outside-window")


def test_consumption_invalid_granularity_is_400() -> None:
    service = make_service(make_client())
    error = problem_of(call, service, f"{METER}/consumption", "from=2026-10-12&to=2026-10-13&granularity=year")
    assert error.status == 400


# --------------------------------------------------------------- résumé


def test_summary_last_seven_days_uses_complete_days() -> None:
    service = make_service(make_client())
    body = body_of(call(service, f"{METER}/consumption/summary", "period=last-7-days"))
    days = [TODAY - timedelta(days=offset) for offset in range(7, 0, -1)]
    values = {d: expected_kwh(d) for d in days}
    assert body["period"] == "last-7-days"
    assert body["days_count"] == 7 and body["complete_days_count"] == 7
    assert body["total_kwh"] == round(sum(values.values()), 3)
    assert body["average_kwh_per_day"] == round(body["total_kwh"] / 7, 2)
    low = min(days, key=lambda d: (values[d], d))
    assert body["min_day"] == {"date": low.isoformat(), "kwh": values[low]}


def test_summary_yesterday_without_data_returns_nulls() -> None:
    yesterday = TODAY - timedelta(days=1)
    service = make_service(make_client(empty_days={yesterday}))
    body = body_of(call(service, f"{METER}/consumption/summary", "period=yesterday"))
    assert body["days_count"] == 1 and body["complete_days_count"] == 0
    assert body["total_kwh"] is None and body["min_day"] is None and body["max_day"] is None


def test_summary_last_month_covers_previous_calendar_month() -> None:
    service = make_service(make_client())
    body = body_of(call(service, f"{METER}/consumption/summary", "period=last-month"))
    assert body["days_count"] == 30  # septembre 2026
    assert body["complete_days_count"] == 30


def test_summary_period_validation() -> None:
    service = make_service(make_client())
    assert problem_of(call, service, f"{METER}/consumption/summary").status == 400
    assert problem_of(call, service, f"{METER}/consumption/summary", "period=last-year").status == 400


# ----------------------------------------------------------- comparaison


def test_comparison_week_compares_last_complete_weeks() -> None:
    service = make_service(make_client())
    body = body_of(call(service, f"{METER}/consumption/comparison", "period=week&against=previous"))
    current_days = [TODAY - timedelta(days=offset) for offset in range(7, 0, -1)]
    reference_days = [TODAY - timedelta(days=offset) for offset in range(14, 7, -1)]
    current_kwh = round(sum(expected_kwh(d) for d in current_days), 3)
    reference_kwh = round(sum(expected_kwh(d) for d in reference_days), 3)
    assert body["current"] == {"from": current_days[0].isoformat(), "to": current_days[-1].isoformat(), "kwh": current_kwh}
    assert body["reference"]["kwh"] == reference_kwh
    assert body["delta_kwh"] == round(current_kwh - reference_kwh, 3)
    assert body["against"] == "previous"


def test_comparison_month_uses_six_months_series() -> None:
    service = make_service(make_client())
    body = body_of(call(service, f"{METER}/consumption/comparison", "period=month&against=previous"))
    assert body["current"] == {"from": "2026-09-01", "to": "2026-09-30", "kwh": 300.0}
    assert body["reference"] == {"from": "2026-08-01", "to": "2026-08-31", "kwh": 320.0}
    assert body["delta_kwh"] == -20.0
    assert body["delta_percent"] == round(-20.0 / 320.0 * 100, 1)


def test_comparison_errors() -> None:
    service = make_service(make_client())
    last_year = problem_of(call, service, f"{METER}/consumption/comparison", "period=week&against=last-year")
    assert (last_year.status, last_year.slug) == (422, "unsupported-value")
    assert problem_of(call, service, f"{METER}/consumption/comparison", "period=week&against=foo").status == 400
    assert problem_of(call, service, f"{METER}/consumption/comparison", "period=week").status == 400


def test_comparison_month_without_data_is_422() -> None:
    short = [{"date": "2026-10-01", "consumption_kWh": 75.0}]
    service = make_service(make_client(consumption_six_months={"success": True, "body": short}))
    error = problem_of(call, service, f"{METER}/consumption/comparison", "period=month&against=previous")
    assert (error.status, error.slug) == (422, "insufficient-data")


# ------------------------------------------------------- profil / veille / anomalies


def test_profile_day_of_week_and_hour_of_day() -> None:
    service = make_service(make_client())
    by_day = body_of(call(service, f"{METER}/consumption/profile", "by=day-of-week&from=2026-10-12&to=2026-10-18"))
    assert by_day["by"] == "day-of-week"
    assert [item["bucket"] for item in by_day["items"]] == [1, 2, 3, 4, 5, 6, 7]
    assert by_day["items"][0]["label"] == "lundi" and by_day["items"][0]["samples"] == 1
    by_hour = body_of(call(service, f"{METER}/consumption/profile", "by=hour-of-day&from=2026-10-12&to=2026-10-12"))
    assert len(by_hour["items"]) == 24
    assert problem_of(call, service, f"{METER}/consumption/profile", "by=month&from=2026-10-12&to=2026-10-12").status == 400


def test_baseline_route_returns_watts() -> None:
    service = make_service(make_client())
    body = body_of(call(service, f"{METER}/consumption/baseline", "from=2026-10-12&to=2026-10-14"))
    assert body["nights_count"] == 3
    assert body["baseline_w"] is not None and body["baseline_w"] > 0
    assert "wh * 2" in body["method"]


def test_anomalies_range_and_threshold_validation() -> None:
    service = make_service(make_client())
    too_short = problem_of(call, service, f"{METER}/consumption/anomalies", "from=2026-10-12&to=2026-10-14")
    assert (too_short.status, too_short.slug) == (422, "range-too-short")
    low = problem_of(call, service, f"{METER}/consumption/anomalies", "from=2026-10-12&to=2026-10-18&threshold=0.5")
    assert low.status == 422
    assert problem_of(call, service, f"{METER}/consumption/anomalies", "from=2026-10-12&to=2026-10-18&threshold=x").status == 400
    body = body_of(call(service, f"{METER}/consumption/anomalies", "from=2026-10-12&to=2026-10-18&threshold=1.0"))
    assert body["threshold"] == 1.0
    assert body["meta"]["computed"] is True
    assert isinstance(body["items"], list)


# ---------------------------------------------------------- facturation


def test_breakdown_route_labels_usages() -> None:
    service = make_service(make_client())
    body = body_of(call(service, f"{METER}/consumption/breakdown"))
    assert body["estimated"] is True and body["source"] == "ohm"
    heat = next(item for item in body["items"] if item["usage"] == "Heat")
    assert heat == {"usage": "Heat", "label": "chauffage", "kwh": 3120}


def test_invoices_pagination_and_detail() -> None:
    service = make_service(make_client())
    reply = call(service, f"/v1/contracts/{CONTRACT_ID}/invoices", "limit=2&page=1")
    body = body_of(reply)
    assert body["pagination"] == {"page": 1, "limit": 2, "total_items": 3, "total_pages": 2, "has_next": True}
    assert [item["invoice_id"] for item in body["items"]] == ["INV-SYNTH-0001", "INV-SYNTH-0002"]
    assert body["items"][0]["amount_eur"] == 84.10 and body["items"][0]["invoice_number"] == 2026093101
    assert 'rel="next"' in reply.headers["Link"]
    detail = body_of(call(service, f"/v1/contracts/{CONTRACT_ID}/invoices/{INVOICE_ID}"))
    assert detail["invoice_id"] == INVOICE_ID and detail["can_download"] is True
    missing = problem_of(call, service, f"/v1/contracts/{CONTRACT_ID}/invoices/INV-NOPE")
    assert (missing.status, missing.slug) == (404, "not-found")


def test_balance_and_tariffs() -> None:
    service = make_service(make_client())
    balance = body_of(call(service, f"/v1/contracts/{CONTRACT_ID}/balance"))
    assert balance == {
        "contract_id": CONTRACT_ID, "balance_eur": 84.2, "total_balance_eur": 84.2, "currency": "EUR",
    }
    tariffs = body_of(call(service, f"/v1/contracts/{CONTRACT_ID}/tariffs"))
    assert tariffs["items"] == [
        {
            "offer_name": "Offre synthétique",
            "start_date": "2026-01-12",
            "end_date": None,
            "document_file_name": "grille-synth.pdf",
        }
    ]
    assert "price" not in json.dumps(tariffs).lower()


def test_balance_is_null_when_upstream_has_no_value() -> None:
    client = make_client(balance={"success": True, "body": []}, balance_total={"success": True, "body": {"soldes": {}, "total_sum": ""}})
    body = body_of(call(make_service(client), f"/v1/contracts/{CONTRACT_ID}/balance"))
    assert body["balance_eur"] is None and body["total_balance_eur"] is None


def test_contract_not_selected_is_422_for_data_routes() -> None:
    service = make_service(make_client())
    for path, query in (
        (f"/v1/meters/{SECOND_METER_ID}/readings", "from=2026-10-20&to=2026-10-20"),
        (f"/v1/contracts/{SECOND_CONTRACT_ID}/invoices", ""),
        (f"/v1/contracts/{SECOND_CONTRACT_ID}/balance", ""),
    ):
        error = problem_of(call, service, path, query)
        assert (error.status, error.slug) == (422, "contract-not-selected"), path
    assert SYNTH_SECOND_PDL not in problem_of(call, service, f"/v1/meters/{SECOND_METER_ID}/readings", "from=2026-10-20&to=2026-10-20").detail


def test_unknown_route_and_method_problems() -> None:
    service = make_service(make_client())
    missing = problem_of(call, service, "/v1/nothing")
    assert (missing.status, missing.slug) == (404, "route-not-found")
    with pytest.raises(ApiProblem) as info:
        api_v1.handle(service, "POST", "/v1/meters", {})
    assert info.value.status == 405 and info.value.headers == {"Allow": "GET"}


# ------------------------------------------------------ erreurs amont


class _ErrorClient(RoutedClient):
    def __init__(self, status: int) -> None:
        super().__init__(synthetic_responses())
        self.status = status

    def get(self, path: str) -> FakeResponse:
        self.calls.append(("GET", path, None))
        return FakeResponse(self.status, {"success": False, "meta": {"status": self.status}})


def test_upstream_http_error_is_502() -> None:
    error = problem_of(call, make_service(_ErrorClient(500)), "/v1/meters")
    assert (error.status, error.slug) == (502, "upstream-error")


def test_upstream_rate_limit_is_429_with_retry_after() -> None:
    error = problem_of(call, make_service(_ErrorClient(429)), "/v1/meters")
    assert error.status == 429 and error.headers == {"Retry-After": "60"}


def test_network_failure_is_503() -> None:
    client = make_client()
    client.fail_network = True
    error = problem_of(call, make_service(client), "/v1/meters")
    assert (error.status, error.slug) == (503, "unavailable")


def test_login_refused_is_503_and_status_reports_logged_out() -> None:
    client = make_client()
    client.fail_login = True
    service = make_service(client)
    error = problem_of(call, service, "/v1/meters")
    assert error.status == 503
    assert SYNTH_PDL not in error.detail
    assert body_of(call(service, "/v1/status"))["upstream"]["login_state"] == "logged_out"


# ------------------------------------------------- serveur HTTP (horloge figée)


@pytest.fixture
def http_server():
    servers = []

    def start(client: Any, api_token: str | None = None):
        config = Config(
            login="synthetic@example.test",
            password="synthetic-password",
            customer_number=None,
            api_base="https://example.invalid",
            ct=None,
            service_host="127.0.0.1",
            service_port=0,
            api_token=api_token,
            cache_ttl=900,
        )
        server = create_server(host="127.0.0.1", port=0, config=config, client=client)
        server.service.today = lambda: TODAY
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _http(url: str, method: str = "GET", headers: dict[str, str] | None = None):
    request = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def test_http_v1_responses_are_problem_json_and_authenticated(http_server) -> None:
    base = http_server(make_client(), api_token="synthetic-token-0123")
    status, headers, body = _http(f"{base}/v1/meters")
    assert status == 401
    assert headers["Content-Type"].startswith("application/problem+json")
    assert headers["WWW-Authenticate"] == "Bearer"
    assert json.loads(body)["status"] == 401
    status, _, _ = _http(f"{base}/v1/meters", headers={"Authorization": "Bearer mauvais"})
    assert status == 401
    status, headers, body = _http(f"{base}/v1/meters", headers={"Authorization": "Bearer synthetic-token-0123"})
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert len(json.loads(body)["items"]) == 2
    assert _http(f"{base}/health")[0] == 200


def test_http_non_get_methods_on_v1_are_405_problem(http_server) -> None:
    base = http_server(make_client())
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        status, headers, body = _http(f"{base}/v1/meters", method=method)
        assert status == 405, method
        assert headers["Content-Type"].startswith("application/problem+json")
        assert headers["Allow"] == "GET"
        assert json.loads(body)["type"] == "urn:ohm-scraper:problem:method-not-allowed"
    assert _http(f"{base}/health", method="POST")[0] == 405


def test_http_readings_csv_and_link_headers(http_server) -> None:
    base = http_server(make_client())
    status, headers, body = _http(
        f"{base}/v1/meters/{METER_ID}/readings?from=2026-10-20&to=2026-10-20&limit=2",
        headers={"Accept": "text/csv"},
    )
    assert status == 200
    assert headers["Content-Type"].startswith("text/csv")
    assert body.decode("utf-8").splitlines()[0] == "timestamp,wh,kwh,tariff_period"
    status, headers, _ = _http(f"{base}/v1/meters/{METER_ID}/readings?from=2026-10-20&to=2026-10-20&limit=2")
    assert 'rel="next"' in headers["Link"]


def test_http_legacy_routes_keep_their_format(http_server) -> None:
    base = http_server(make_client())
    status, headers, body = _http(f"{base}/endpoints")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert "endpoints" in json.loads(body)
    status, headers, body = _http(f"{base}/data/unknown_name")
    assert status == 404 and "error" in json.loads(body)
    status, headers, body = _http(f"{base}/v1/unknown")
    assert status == 404 and headers["Content-Type"].startswith("application/problem+json")
