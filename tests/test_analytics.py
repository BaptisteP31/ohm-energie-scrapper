"""Tests unitaires des fonctions pures de ohm_scraper.analytics (données synthétiques)."""

from __future__ import annotations

import statistics
from datetime import date, timedelta

import pytest

from ohm_scraper import analytics as an
from tests.fakes import hourly_payload, synthetic_day_values

DAY = date(2026, 10, 12)


def readings(day: date, values: list[float], colors: list[str] | None = None) -> list[an.HalfHour]:
    return an.parse_hourly(day, hourly_payload(values, colors))


def full_day(day: date, wh: float = 500.0) -> list[an.HalfHour]:
    return readings(day, [wh] * 48)


# ----------------------------------------------------------- temps / DST


def test_expected_points_follow_dst_changes() -> None:
    assert an.expected_points(date(2026, 10, 24)) == 48
    assert an.expected_points(date(2026, 3, 29)) == 46  # passage à l'heure d'été
    assert an.expected_points(date(2026, 10, 25)) == 50  # passage à l'heure d'hiver


def test_slot_start_is_absolute_across_dst_change() -> None:
    day = date(2026, 10, 25)
    assert an.slot_start(day, 0).isoformat() == "2026-10-25T00:00:00+02:00"
    assert an.slot_start(day, 6).isoformat() == "2026-10-25T02:00:00+01:00"


def test_month_helpers() -> None:
    assert an.month_end(date(2026, 2, 1)) == date(2026, 2, 28)
    assert an.month_end(date(2026, 12, 1)) == date(2026, 12, 31)
    assert an.add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert an.add_months(date(2026, 10, 1), -5) == date(2026, 5, 1)


# ------------------------------------------------------------- relevés


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("bleu", "off_peak"),
        ("Heures Creuses", "off_peak"),
        ("Blanc", "peak"),
        ("rouge", "peak"),
        ("vert", None),
        ("", None),
        (None, None),
        (42, None),
    ],
)
def test_tariff_from_color(value, expected) -> None:
    assert an.tariff_from_color(value) == expected


def test_parse_hourly_skips_missing_points_and_keeps_positions() -> None:
    values = [500, None, 300]
    parsed = readings(DAY, values, ["bleu", "bleu", "blanc"])
    assert [(r.index, r.wh, r.tariff) for r in parsed] == [
        (0, 500.0, "off_peak"),
        (2, 300.0, "peak"),
    ]


def test_parse_hourly_tolerates_unexpected_payloads() -> None:
    assert an.parse_hourly(DAY, {"success": False}) == []
    assert an.parse_hourly(DAY, {"body": {"consumptions": {"data": "x"}}}) == []


def test_day_totals_complete_and_partial() -> None:
    partial = readings(DAY + timedelta(days=1), [500.0] * 30)
    data = {DAY: full_day(DAY), DAY + timedelta(days=1): partial, DAY + timedelta(days=2): []}
    totals = an.day_totals(data)
    assert set(totals) == {DAY, DAY + timedelta(days=1)}
    assert totals[DAY].kwh == 24.0
    assert totals[DAY].complete is True
    assert totals[DAY + timedelta(days=1)].complete is False
    assert totals[DAY + timedelta(days=1)].points == 30


# ------------------------------------------------------------ résumé


def test_summary_uses_only_complete_days() -> None:
    days = [DAY + timedelta(days=offset) for offset in range(3)]
    data = {
        days[0]: full_day(days[0], 400.0),  # 19.2 kWh
        days[1]: full_day(days[1], 600.0),  # 28.8 kWh
        days[2]: readings(days[2], [9000.0] * 10),  # incomplet, ignoré
    }
    summary = an.summarize(days, an.day_totals(data))
    assert summary["days_count"] == 3
    assert summary["complete_days_count"] == 2
    assert summary["total_kwh"] == 48.0
    assert summary["average_kwh_per_day"] == 24.0
    assert summary["min_day"] == {"date": "2026-10-12", "kwh": 19.2}
    assert summary["max_day"] == {"date": "2026-10-13", "kwh": 28.8}


def test_summary_without_complete_day_has_no_derived_values() -> None:
    summary = an.summarize([DAY], an.day_totals({DAY: readings(DAY, [500.0])}))
    assert summary["days_count"] == 1
    assert summary["complete_days_count"] == 0
    assert summary["total_kwh"] is None
    assert summary["average_kwh_per_day"] is None
    assert summary["min_day"] is None and summary["max_day"] is None


# -------------------------------------------------------- comparaison


def test_compare_delta_and_percent() -> None:
    assert an.compare(81.6, 88.2) == (-6.6, -7.5)


def test_compare_with_zero_reference_has_no_percent() -> None:
    assert an.compare(5.0, 0.0) == (5.0, None)


def test_split_complete_weeks_takes_last_two_spans_of_complete_days() -> None:
    end = date(2026, 10, 23)
    totals = {}
    for offset in range(21):
        day = end - timedelta(days=offset)
        if offset == 3:  # un jour incomplet : sauté, la fenêtre s'élargit
            totals[day] = an.DayTotal(day, 1000.0, 10, 48)
        else:
            totals[day] = an.DayTotal(day, 500.0 * (offset + 1), 48, 48)
    current, reference = an.split_complete_weeks(totals, end)
    assert len(current) == 7 and len(reference) == 7
    assert current[-1].day == end
    assert all(t.complete for t in current + reference)
    assert max(t.day for t in reference) < min(t.day for t in current)
    assert end - timedelta(days=3) not in {t.day for t in current + reference}


def test_split_complete_weeks_returns_none_without_enough_days() -> None:
    end = date(2026, 10, 23)
    totals = {end: an.DayTotal(end, 500.0, 48, 48)}
    assert an.split_complete_weeks(totals, end) is None


# ------------------------------------------------------------ profil


def test_profile_day_of_week_averages_complete_days() -> None:
    monday = date(2026, 10, 12)
    assert monday.isoweekday() == 1
    days = [monday + timedelta(days=offset) for offset in range(14)]
    data = {d: full_day(d, 500.0) for d in days}  # 24 kWh par jour
    totals = an.day_totals(data)
    items = an.profile(data, totals, days, "day-of-week")
    monday_item = next(item for item in items if item["bucket"] == 1)
    assert monday_item == {"bucket": 1, "label": "lundi", "average_kwh": 24.0, "samples": 2}
    assert len(items) == 7


def test_profile_hour_of_day_needs_both_half_hours() -> None:
    days = [DAY, DAY + timedelta(days=1)]
    data = {d: full_day(d, 250.0) for d in days}  # 0,5 kWh par heure
    data[DAY] = readings(DAY, [250.0] * 47)  # la dernière demi-heure manque (23 h 30)
    items = an.profile(data, an.day_totals(data), days, "hour-of-day")
    hour_0 = next(item for item in items if item["bucket"] == 0)
    hour_23 = next(item for item in items if item["bucket"] == 23)
    assert hour_0 == {"bucket": 0, "label": "00 h", "average_kwh": 0.5, "samples": 2}
    assert hour_23["samples"] == 1
    assert len(items) == 24


# ------------------------------------------------------------ veille


def test_baseline_is_median_of_night_minimums_in_watts() -> None:
    days = [DAY + timedelta(days=offset) for offset in range(3)]
    data = {}
    for day, night_min in zip(days, (100.0, 200.0, 300.0)):
        values = [900.0] * 48  # le jour ne compte pas
        values[3] = night_min  # 01 h 30 : dans la fenêtre 00 h - 05 h
        values[20] = 1.0  # 10 h : hors fenêtre, ignoré
        data[day] = readings(day, values)
    result = an.baseline(data, days)
    assert result == {"baseline_w": 400.0, "nights_count": 3}


def test_baseline_without_night_data() -> None:
    assert an.baseline({}, [DAY]) == {"baseline_w": None, "nights_count": 0}


# ----------------------------------------------------------- anomalies


def test_anomalies_flag_days_beyond_threshold() -> None:
    days = [DAY + timedelta(days=offset) for offset in range(7)]
    kwh = [10.0] * 6 + [30.0]
    data = {d: full_day(d, value * 1000 / 48) for d, value in zip(days, kwh)}
    totals = an.day_totals(data)
    flagged = an.anomalies(totals, days, threshold=2.0)
    assert flagged["mean_kwh"] == pytest.approx(statistics.fmean(kwh), abs=0.01)
    assert [item["date"] for item in flagged["items"]] == [days[6].isoformat()]
    assert flagged["items"][0]["z_score"] > 2.0
    assert an.anomalies(totals, days, threshold=2.5)["items"] == []


def test_anomalies_without_variation_or_data() -> None:
    days = [DAY + timedelta(days=offset) for offset in range(7)]
    flat = {d: full_day(d) for d in days}
    assert an.anomalies(an.day_totals(flat), days, 2.0)["items"] == []
    assert an.anomalies({}, days, 2.0) == {"mean_kwh": None, "items": []}


# ----------------------------------------------------------- séries


def test_hour_series_marks_complete_hours() -> None:
    values = synthetic_day_values(DAY)[:3]
    data = {DAY: readings(DAY, values)}
    series = an.hour_series(data)
    assert series[0]["period_start"] == "2026-10-12T00:00:00+02:00"
    assert series[0]["complete"] is True and series[0]["points"] == 2
    assert series[1]["complete"] is False and series[1]["points"] == 1


def test_week_series_requires_whole_week_in_range() -> None:
    monday = date(2026, 10, 5)
    days = [monday + timedelta(days=offset) for offset in range(7)]
    totals = an.day_totals({d: full_day(d) for d in days})
    whole = an.week_series(totals, monday, monday + timedelta(days=6))
    assert whole[0]["complete"] is True and whole[0]["kwh"] == 168.0
    partial = an.week_series(totals, monday + timedelta(days=1), monday + timedelta(days=6))
    assert partial[0]["complete"] is False


def test_month_series_completeness_and_points() -> None:
    monthly = {date(2026, 8, 1): 300.0, date(2026, 10, 1): 80.0}
    series = an.month_series(monthly, date(2026, 8, 1), date(2026, 10, 31), date(2026, 10, 24))
    august, october = series
    assert august == {"period_start": "2026-08-01", "kwh": 300.0, "complete": True, "points": 48 * 31}
    assert october["complete"] is False and october["points"] == 0
