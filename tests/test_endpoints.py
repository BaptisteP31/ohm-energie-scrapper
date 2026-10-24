"""Catalogue d'endpoints : unicité, allowlist, exclusions et templating."""

from __future__ import annotations

import re

import pytest

from ohm_scraper.endpoints import (
    ALL_ENDPOINTS,
    CONSUMPTION_ENDPOINTS,
    DUMP_ENDPOINTS,
    EXCLUDED_ENDPOINTS,
    ENDPOINTS_BY_NAME,
    EndpointError,
    get_endpoint,
    render_endpoint_list,
)

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def test_dump_contains_the_get_read_endpoints() -> None:
    # 37 GET ; le 38e endpoint vérifié est la courbe horaire (POST), servie par `consumption`.
    assert len(DUMP_ENDPOINTS) == 37
    assert len({endpoint.name for endpoint in DUMP_ENDPOINTS}) == 37


def test_names_are_stable_and_unique() -> None:
    names = [endpoint.name for endpoint in ALL_ENDPOINTS]
    assert len(names) == len(set(names))
    for name in names:
        assert NAME_RE.match(name), name


def test_directory_names_used_by_the_cli() -> None:
    assert {"consumption_six_months", "invoices", "balance"} <= set(ENDPOINTS_BY_NAME)
    assert "consumption_kwh_data" in ENDPOINTS_BY_NAME


def test_dump_endpoints_are_get_only_and_documented() -> None:
    for endpoint in DUMP_ENDPOINTS:
        assert endpoint.method == "GET"
        assert endpoint.category
        assert endpoint.description
        assert endpoint.template.startswith("user/") or endpoint.template.startswith("salesforce-")


def test_consumption_endpoints_are_post_reads() -> None:
    assert {endpoint.name for endpoint in CONSUMPTION_ENDPOINTS} == {
        "consumption_hourly",
        "consumption_power_days",
        "consumption_power_months",
        "consumption_power_years",
        "consumption_period",
    }
    for endpoint in CONSUMPTION_ENDPOINTS:
        assert endpoint.method == "POST"
        assert endpoint.body


def test_path_templating_and_missing_parameters() -> None:
    invoices = get_endpoint("invoices")
    assert invoices.path("CM-TEST", "CT-TEST") == "user/CM-TEST/billing/invoices/CT-TEST"
    with pytest.raises(EndpointError):
        invoices.path(None, "CT-TEST")
    with pytest.raises(EndpointError):
        invoices.path("CM-TEST", None)
    assert get_endpoint("salesforce_questions").path(None, None) == "salesforce-request-questions"


def test_unknown_endpoint_lists_available_names() -> None:
    with pytest.raises(EndpointError) as excinfo:
        get_endpoint("nope")
    assert "consumption_six_months" in str(excinfo.value)


def test_mutating_endpoints_are_excluded_with_a_reason() -> None:
    paths = {path for _, path, _ in EXCLUDED_ENDPOINTS}
    assert "logout/{number}" in paths
    assert "user/{number}/initparrainage" in paths
    assert "user/{number}/stripe/cancel" in paths
    for method, path, reason in EXCLUDED_ENDPOINTS:
        assert method and path and reason


def test_render_endpoint_list_is_offline_and_readable() -> None:
    text = render_endpoint_list()
    lines = text.splitlines()
    assert len(lines) == len(DUMP_ENDPOINTS)
    assert "consumption_six_months" in text
    assert "Tableau de bord" in text
    assert "user/{number}" not in text
