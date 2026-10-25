"""Tests du serveur HTTP ohm_scraper.server."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any

import pytest

from ohm_scraper.config import Config
from ohm_scraper.endpoints import DUMP_ENDPOINTS
from ohm_scraper.server import create_server
from tests.fakes import FakeClient, FakeResponse

KWH_DATA = {"success": True, "body": {"others": {"pdl": "12345678901234"}}}
HOURLY_DATA = {
    "success": True,
    "body": {
        "consumptions": {
            "data": [500],
            "dataString": ["0,5"],
            "time": ["00:00"],
            "heuresCreuseColors": ["bleu"],
        }
    },
}


class ReloginFakeClient(FakeClient):
    """Client factice qui renvoie 401 une fois pour tester la reconnexion."""

    def __init__(self) -> None:
        super().__init__()
        self.first_call = True

    def get(self, path: str) -> FakeResponse:
        self.calls.append(("GET", path, None))
        if self.first_call:
            self.first_call = False
            return FakeResponse(401, {"meta": {"status": 401, "message": "token expired"}})
        return FakeResponse(200, {"success": True, "body": {"invoices": []}})


def run_test_server(config: Config, client: FakeClient):
    server = create_server(host="127.0.0.1", port=0, config=config, client=client)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    return server, base_url


def http_get(url: str, headers: dict[str, str] | None = None) -> tuple[int, Any, dict[str, str]]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            body = resp.read()
            resp_headers = dict(resp.headers)
            content_type = resp_headers.get("Content-Type", "")
            if "application/json" in content_type:
                payload = json.loads(body.decode("utf-8"))
            else:
                payload = body.decode("utf-8")
            return status, payload, resp_headers
    except urllib.error.HTTPError as exc:
        body = exc.read()
        resp_headers = dict(exc.headers)
        content_type = resp_headers.get("Content-Type", "")
        if "application/json" in content_type:
            payload = json.loads(body.decode("utf-8"))
        else:
            payload = body.decode("utf-8")
        return exc.code, payload, resp_headers


def http_request(url: str, method: str) -> int:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


@pytest.fixture
def test_env():
    cfg = Config(
        login="test@example.com",
        password="password",
        customer_number="CM-TEST",
        api_base="https://bo-api.ohm-energie.com",
        ct="CT-TEST",
        service_host="127.0.0.1",
        service_port=0,
        api_token=None,
        cache_ttl=900,
    )
    client = FakeClient(get_payload=KWH_DATA, post_payload=HOURLY_DATA)
    server, base_url = run_test_server(cfg, client)
    try:
        yield client, base_url
    finally:
        server.shutdown()
        server.server_close()


def test_health_without_upstream(test_env) -> None:
    client, base_url = test_env
    status, payload, _ = http_get(f"{base_url}/health")
    assert status == 200
    assert payload == {"status": "ok"}
    # Aucun appel amont ni login effectué pour /health
    assert getattr(client, "login_count", 0) == 0
    assert len(client.calls) == 0


def test_endpoints_catalogue(test_env) -> None:
    client, base_url = test_env
    status, payload, _ = http_get(f"{base_url}/endpoints")
    assert status == 200
    assert "endpoints" in payload
    endpoints = payload["endpoints"]
    assert any(e["name"] == "invoices" for e in endpoints)
    assert any(e["name"] == "consumption_six_months" for e in endpoints)


def test_data_list(test_env) -> None:
    client, base_url = test_env
    status, payload, _ = http_get(f"{base_url}/data")
    assert status == 200
    assert "names" in payload
    assert len(payload["names"]) == len(DUMP_ENDPOINTS)
    assert "invoices" in payload["names"]


def test_data_caching_and_refresh_rate_limit(test_env) -> None:
    client, base_url = test_env

    # 1er appel : appelle l'amont
    status, payload, _ = http_get(f"{base_url}/data/invoices")
    assert status == 200
    initial_calls = len(client.calls)
    assert initial_calls > 0

    # 2e appel : cache hit, aucun appel supplémentaire
    status, payload, _ = http_get(f"{base_url}/data/invoices")
    assert status == 200
    assert len(client.calls) == initial_calls

    # Appel avec refresh=1 : bypass du cache
    status, payload, _ = http_get(f"{base_url}/data/invoices?refresh=1")
    assert status == 200
    assert len(client.calls) == initial_calls + 1

    # Appel avec refresh=1 immédiatement après : 429 Too Many Requests
    status, payload, _ = http_get(f"{base_url}/data/invoices?refresh=1")
    assert status == 429
    assert "60 secondes" in payload["error"]


def test_data_unknown_endpoint(test_env) -> None:
    client, base_url = test_env
    status, payload, _ = http_get(f"{base_url}/data/endpoint_inconnu")
    assert status == 404
    assert "Endpoint inconnu" in payload["error"]


def test_consumption_validation(test_env) -> None:
    client, base_url = test_env

    # Plage inversée
    status, payload, _ = http_get(f"{base_url}/consumption?granularity=hourly&from=25/10/2026&to=20/10/2026")
    assert status == 400
    assert "invalide" in payload["error"]

    # Format inconnu
    status, payload, _ = http_get(f"{base_url}/consumption?format=xml")
    assert status == 400
    assert "Format invalide" in payload["error"]

    # Granularité inconnue
    status, payload, _ = http_get(f"{base_url}/consumption?granularity=century")
    assert status == 400
    assert "Granularité invalide" in payload["error"]

    # Plage horaire trop large (> 31 jours)
    status, payload, _ = http_get(
        f"{base_url}/consumption?granularity=hourly&from=01/01/2026&to=15/02/2026"
    )
    assert status == 400
    assert "plafond dur de 31 jours" in payload["error"]


def test_consumption_success_json_and_csv(test_env) -> None:
    client, base_url = test_env

    # JSON
    status, payload, headers = http_get(
        f"{base_url}/consumption?granularity=hourly&from=23/10/2026&to=23/10/2026&format=json"
    )
    assert status == 200
    assert payload["granularity"] == "hourly"
    assert "rows" in payload

    # CSV
    status, payload, headers = http_get(
        f"{base_url}/consumption?granularity=hourly&from=23/10/2026&to=23/10/2026&format=csv"
    )
    assert status == 200
    assert "text/csv" in headers["Content-Type"]
    assert "date,time,wh,kwh" in payload


def test_authentication_with_token() -> None:
    cfg = Config(
        login="test@example.com",
        password="password",
        customer_number="CM-TEST",
        api_base="https://bo-api.ohm-energie.com",
        ct="CT-TEST",
        service_host="127.0.0.1",
        service_port=0,
        api_token="my_secret_token_123",
        cache_ttl=900,
    )
    client = FakeClient()
    server, base_url = run_test_server(cfg, client)
    try:
        # /health sans jeton -> 200
        status, payload, _ = http_get(f"{base_url}/health")
        assert status == 200

        # /endpoints sans jeton -> 401
        status, payload, _ = http_get(f"{base_url}/endpoints")
        assert status == 401
        assert "Authentification requise" in payload["error"]

        # /endpoints avec mauvais jeton -> 401
        status, payload, _ = http_get(
            f"{base_url}/endpoints",
            headers={"Authorization": "Bearer mauvais_jeton"},
        )
        assert status == 401
        assert "invalide" in payload["error"]

        # /endpoints avec bon jeton -> 200
        status, payload, _ = http_get(
            f"{base_url}/endpoints",
            headers={"Authorization": "Bearer my_secret_token_123"},
        )
        assert status == 200

        # /data avec bon jeton -> 200
        status, payload, _ = http_get(
            f"{base_url}/data",
            headers={"Authorization": "Bearer my_secret_token_123"},
        )
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_non_get_methods(test_env) -> None:
    client, base_url = test_env
    assert http_request(f"{base_url}/health", "POST") == 405
    assert http_request(f"{base_url}/data/invoices", "DELETE") == 405
    assert http_request(f"{base_url}/consumption", "PUT") == 405


def test_relogin_on_401() -> None:
    cfg = Config(
        login="test@example.com",
        password="password",
        customer_number="CM-TEST",
        api_base="https://bo-api.ohm-energie.com",
        ct="CT-TEST",
        service_host="127.0.0.1",
        service_port=0,
        api_token=None,
        cache_ttl=900,
    )
    client = ReloginFakeClient()
    server, base_url = run_test_server(cfg, client)
    try:
        status, payload, _ = http_get(f"{base_url}/data/invoices")
        assert status == 200
        # Vérifie qu'il y a eu 2 appels GET (le premier en 401, le second en 200 après login)
        assert len(client.calls) == 2
    finally:
        server.shutdown()
        server.server_close()
