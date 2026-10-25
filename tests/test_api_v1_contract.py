"""Contrat v1 : chaque opération de docs/openapi.yaml répond selon son schéma."""

from __future__ import annotations

import json
import urllib.parse

import pytest

from ohm_scraper import api_v1
from ohm_scraper.problems import ApiProblem
from tests.openapi_check import load_spec, operation_schema, validate
from tests.test_api_v1 import (
    CONTRACT_ID,
    INVOICE_ID,
    METER_ID,
    make_client,
    make_service,
)

SPEC = load_spec()
V1_OPERATIONS = [
    (path, item["get"])
    for path, item in SPEC["paths"].items()
    if path.startswith("/v1/") and "legacy" not in item["get"]["tags"]
]
QUERIES = {
    "getStatus": "",
    "listMeters": "",
    "getMeter": "",
    "listMeterReadings": "from=2026-10-20&to=2026-10-21&limit=5",
    "getMeterConsumption": "from=2026-10-20&to=2026-10-21&granularity=day",
    "getMeterConsumptionSummary": "period=last-7-days",
    "getMeterConsumptionComparison": "period=week&against=previous",
    "getMeterConsumptionProfile": "by=hour-of-day&from=2026-10-20&to=2026-10-21",
    "getMeterConsumptionBaseline": "from=2026-10-20&to=2026-10-22",
    "getMeterConsumptionAnomalies": "from=2026-10-16&to=2026-10-22&threshold=2.0",
    "getMeterConsumptionBreakdown": "",
    "listContracts": "",
    "listContractInvoices": "limit=2",
    "getContractInvoice": "",
    "getContractBalance": "",
    "listContractTariffs": "",
}


def _concrete(path: str) -> str:
    return (
        path.replace("{meterId}", METER_ID)
        .replace("{contractId}", CONTRACT_ID)
        .replace("{invoiceId}", INVOICE_ID)
    )


def _call(service, path: str, query: str):
    return api_v1.handle(
        service, "GET", _concrete(path), urllib.parse.parse_qs(query, keep_blank_values=True)
    )


def test_every_v1_operation_has_a_query_fixture() -> None:
    operation_ids = {operation["operationId"] for _, operation in V1_OPERATIONS}
    assert operation_ids == set(QUERIES)


def test_v1_route_count_matches_contract() -> None:
    assert len(V1_OPERATIONS) == 16


@pytest.mark.parametrize(
    ("path", "operation"),
    V1_OPERATIONS,
    ids=[operation["operationId"] for _, operation in V1_OPERATIONS],
)
def test_success_body_matches_openapi_schema(path: str, operation: dict) -> None:
    service = make_service(make_client())
    reply = _call(service, path, QUERIES[operation["operationId"]])
    assert reply.status == 200
    assert reply.content_type.startswith("application/json")
    documented = operation_schema(SPEC, path, "200")
    assert documented is not None, f"pas de schéma JSON 200 pour {path}"
    errors = validate(SPEC, documented, json.loads(reply.body.decode("utf-8")))
    assert errors == []


def test_documented_status_codes_cover_implemented_errors() -> None:
    expected = {
        "/v1/meters/{meterId}/readings": {"400", "401", "404", "422", "429", "502", "503"},
        "/v1/meters/{meterId}/consumption": {"400", "404", "422"},
        "/v1/meters/{meterId}/consumption/summary": {"400", "404"},
        "/v1/meters/{meterId}/consumption/comparison": {"400", "404", "422"},
        "/v1/contracts/{contractId}/invoices/{invoiceId}": {"404"},
    }
    for path, codes in expected.items():
        documented = set(SPEC["paths"][path]["get"]["responses"])
        assert codes <= documented, path


@pytest.mark.parametrize(
    ("path", "query", "status", "slug"),
    [
        ("/v1/meters/{meterId}/readings", "to=2026-10-20", 400, "invalid-parameter"),
        ("/v1/meters/{meterId}/readings", "from=2026-10-21&to=2026-10-20", 422, "range-invalid"),
        ("/v1/meters/{meterId}/readings", "from=2026-09-01&to=2026-10-02", 422, "range-too-long"),
        ("/v1/meters/{meterId}/consumption/summary", "period=decade", 400, "invalid-parameter"),
        ("/v1/meters/{meterId}/consumption/comparison", "period=week&against=last-year", 422, "unsupported-value"),
        ("/v1/meters/{meterId}/consumption/anomalies", "from=2026-10-01&to=2026-10-03", 422, "range-too-short"),
        ("/v1/meters/{meterId}/consumption/profile", "by=hour-of-day&from=2026-10-01&to=2026-10-40", 400, "invalid-parameter"),
    ],
)
def test_error_bodies_are_problem_documents(path: str, query: str, status: int, slug: str) -> None:
    service = make_service(make_client())
    with pytest.raises(ApiProblem) as info:
        _call(service, path, query)
    problem = info.value
    assert problem.status == status
    assert problem.slug == slug
    body = problem.body()
    assert validate(SPEC, SPEC["components"]["schemas"]["Problem"], body) == []
    assert body["type"] == f"urn:ohm-scraper:problem:{slug}"


def test_unknown_identifiers_are_404_problem_documents() -> None:
    service = make_service(make_client())
    for path in (
        "/v1/meters/000000000000",
        "/v1/contracts/000000000000/balance",
    ):
        with pytest.raises(ApiProblem) as info:
            api_v1.handle(service, "GET", path, {})
        assert info.value.status == 404
        assert validate(SPEC, SPEC["components"]["schemas"]["Problem"], info.value.body()) == []


def test_malformed_identifier_is_400() -> None:
    service = make_service(make_client())
    with pytest.raises(ApiProblem) as info:
        api_v1.handle(service, "GET", "/v1/meters/3F9A1C0B7E2D", {})
    assert info.value.status == 400


def test_validator_detects_violations() -> None:
    schema = SPEC["components"]["schemas"]["Pagination"]
    good = {"page": 1, "limit": 100, "total_items": 0, "total_pages": 0, "has_next": False}
    assert validate(SPEC, schema, good) == []
    bad = dict(good, limit=1000, has_next="non")
    assert len(validate(SPEC, schema, bad)) == 2
    assert validate(SPEC, schema, {"page": 1}) != []
    assert validate(SPEC, SPEC["components"]["schemas"]["Health"], {"status": "ko"}) != []
