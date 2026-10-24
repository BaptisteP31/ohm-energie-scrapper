"""Dates, plafond horaire, extraction du PDL et conversion CSV (hors ligne)."""

from __future__ import annotations

from datetime import date

import pytest

from ohm_scraper.consumption import (
    MAX_HOURLY_DAYS,
    ConsumptionError,
    extract_pdl,
    flatten,
    hourly_rows,
    iter_days,
    parse_date,
    render_output,
    resolve_range,
    rows_to_csv,
    validate_range,
)

TODAY = date(2026, 10, 24)

HOURLY_PAYLOAD = {
    "success": True,
    "meta": {"status": 200},
    "body": {
        "consumptions": {
            "data": [500, 750, None],
            "dataString": ["0,5", "0,75", "-"],
            "time": ["00:00", "00:30", "01:00"],
            "heuresCreuseColors": ["bleu", "bleu", "rouge"],
        }
    },
}


def test_parse_date_accepts_french_and_iso() -> None:
    assert parse_date("23/10/2026") == date(2026, 10, 23)
    assert parse_date(" 2026-10-23 ") == date(2026, 10, 23)


def test_parse_date_rejects_invalid_input() -> None:
    with pytest.raises(ConsumptionError):
        parse_date("2026/10/23")
    with pytest.raises(ConsumptionError):
        parse_date("")


def test_default_ranges() -> None:
    start, end = resolve_range("hourly", None, None, today=TODAY)
    assert (start, end) == (date(2026, 10, 23), date(2026, 10, 23))

    start, end = resolve_range("daily", None, None, today=TODAY)
    assert end == date(2026, 10, 23)
    assert (end - start).days + 1 == 7

    start, end = resolve_range("power-days", None, None, today=TODAY)
    assert (end - start).days + 1 == 31

    start, end = resolve_range("power-months", None, None, today=TODAY)
    assert end == date(2026, 10, 23)
    assert start == date(2025, 11, 1)


def test_explicit_range_overrides_defaults() -> None:
    start, end = resolve_range("hourly", "20/10/2026", "2026-10-22", today=TODAY)
    assert (start, end) == (date(2026, 10, 20), date(2026, 10, 22))


def test_reversed_range_is_rejected() -> None:
    with pytest.raises(ConsumptionError):
        resolve_range("daily", "23/10/2026", "01/10/2026", today=TODAY)


def test_hourly_cap_is_31_days() -> None:
    validate_range(date(2026, 10, 1), date(2026, 10, 31), "hourly")  # 31 jours : autorisé

    with pytest.raises(ConsumptionError) as excinfo:
        resolve_range("hourly", "01/10/2026", "01/11/2026", today=TODAY)
    assert str(MAX_HOURLY_DAYS) in str(excinfo.value)
    assert "plafond" in str(excinfo.value)


def test_iter_days_is_inclusive() -> None:
    days = iter_days(date(2026, 10, 20), date(2026, 10, 23))
    assert len(days) == 4
    assert days[0] == date(2026, 10, 20)
    assert days[-1] == date(2026, 10, 23)


def test_extract_pdl_reads_body_others() -> None:
    assert extract_pdl({"body": {"others": {"pdl": "12345678901234"}}}) == "12345678901234"
    assert extract_pdl({"body": {"others": {"prm": "PRM-TEST"}}}) == "PRM-TEST"
    assert extract_pdl({"body": {}}) is None
    assert extract_pdl(None) is None


def test_hourly_rows_and_csv_conversion() -> None:
    rows = hourly_rows(date(2026, 10, 23), HOURLY_PAYLOAD)
    assert [row["time"] for row in rows] == ["00:00", "00:30", "01:00"]
    assert rows[0]["date"] == "2026-10-23"
    assert rows[1]["wh"] == 750
    assert rows[1]["kwh"] == 0.75
    assert rows[2]["kwh"] is None

    csv_text = rows_to_csv(rows)
    lines = csv_text.splitlines()
    assert lines[0] == "date,time,wh,kwh,kwh_text,color"
    assert lines[1] == '2026-10-23,00:00,500,0.5,"0,5",bleu'
    assert len(lines) == 4


def test_rows_to_csv_is_empty_without_rows() -> None:
    assert rows_to_csv([]) == ""


def test_rows_to_csv_quotes_commas_and_json_values() -> None:
    rows = [{"date": "2026-10-23", "label": "a,b", "meta": {"x": 1}}]
    assert rows_to_csv(rows) == 'date,label,meta\n2026-10-23,"a,b","{""x"":1}"\n'


def test_flatten_and_render_json_shape() -> None:
    rows = flatten("hourly", [("2026-10-23", HOURLY_PAYLOAD)])
    assert len(rows) == 3

    text = render_output("hourly", date(2026, 10, 23), date(2026, 10, 23), rows, [], "json")
    assert '"granularity": "hourly"' in text
    assert '"from": "2026-10-23"' in text
    assert '"rows"' in text


def test_generic_rows_handle_parallel_arrays_and_object_lists() -> None:
    rows = flatten(
        "power-months",
        [("2026-01-01..2026-10-23", {"body": {"labels": ["jan", "fev"], "data": [10, 20]}})],
    )
    assert rows == [{"labels": "jan", "data": 10}, {"labels": "fev", "data": 20}]

    rows = flatten("power-days", [("2026-10-23", {"body": [{"date": "2026-10-22", "kwh": 1.5}]})])
    assert rows == [{"date": "2026-10-22", "kwh": 1.5}]


def test_daily_rows_sum_half_hours_in_kwh() -> None:
    payload = {"body": {"consumptions": {"data": [426] * 48, "time": [f"{i}" for i in range(48)]}}}
    rows = flatten("daily", [("2026-10-23", payload), ("2026-10-24", HOURLY_PAYLOAD)])
    assert rows[0] == {"date": "2026-10-23", "kwh": 20.448, "wh": 20448, "points": 48, "complete": True}
    assert rows[1]["date"] == "2026-10-24"
    assert rows[1]["points"] == 2
    assert rows[1]["complete"] is False
    assert rows[1]["kwh"] == 1.25


def test_daily_cap_is_enforced() -> None:
    with pytest.raises(ConsumptionError):
        resolve_range("daily", "01/09/2026", "23/10/2026", today=TODAY)
