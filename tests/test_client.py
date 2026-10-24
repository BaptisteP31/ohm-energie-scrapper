"""Connexion, rafraîchissement du jeton et absence de fuite dans les erreurs."""

from __future__ import annotations

import pytest

from ohm_scraper.client import OhmApiError, OhmClient, OhmLoginError
from ohm_scraper.config import Config
from tests.fakes import FakeResponse, FakeSession

LOGIN_OK = {
    "success": True,
    "meta": {"status": 200, "message": ""},
    "body": {
        "user": {
            "customer_nbr": "CM-TEST",
            "currentContract": "CT-TEST",
            "elec_contracts": ["CT-TEST"],
            "gaz_contracts": [],
        }
    },
}


def make_client(login: str = "synthetic-user@example.test", password: str = "synthetic-password") -> OhmClient:
    config = Config(
        login=login,
        password=password,
        customer_number=None,
        api_base="https://example.test",
        ct=None,
    )
    return OhmClient(config)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ohm_scraper.client.REQUEST_INTERVAL", 0.0)


def test_login_success_fills_account_and_contract() -> None:
    client = make_client(login="Synthetic-User@Example.Test")
    session = FakeSession(FakeResponse(200, LOGIN_OK))
    client._session = session

    user = client.login()

    assert user["customer_nbr"] == "CM-TEST"
    assert client.customer_number == "CM-TEST"
    assert client.ct == "CT-TEST"
    assert client._login == "synthetic-user@example.test"
    assert session.calls[0][0] == "POST"
    assert session.calls[0][1].endswith("/api/login")
    assert session.calls[0][2] == {
        "email": "synthetic-user@example.test",
        "password": "synthetic-password",
    }


def test_customer_reference_is_not_lowercased() -> None:
    client = make_client(login="CM-123456")
    client._session = FakeSession(FakeResponse(200, LOGIN_OK))
    client.login()
    assert client._login == "CM-123456"


def test_login_failure_raises_without_leaking_password() -> None:
    client = make_client(password="synthetic-password")
    client._session = FakeSession(
        FakeResponse(401, {"success": False, "meta": {"status": 401, "message": "check your credentials"}})
    )

    with pytest.raises(OhmLoginError) as excinfo:
        client.login()

    assert excinfo.value.status_code == 401
    assert "synthetic-password" not in str(excinfo.value)
    assert "check your credentials" in str(excinfo.value)


def test_login_requires_user_object() -> None:
    client = make_client()
    client._session = FakeSession(FakeResponse(200, {"success": True, "meta": {"status": 200}, "body": {}}))
    with pytest.raises(OhmApiError):
        client.login()


def test_token_refresh_then_single_retry() -> None:
    client = make_client()
    client._session = FakeSession(
        FakeResponse(401, {"meta": {"status": 401, "message": "token expired"}}),
        FakeResponse(200, {"success": True}),
        FakeResponse(200, {"success": True, "body": []}),
    )

    response = client.get("user/CM-TEST/dashboard/CT-TEST")

    assert response.status_code == 200
    assert client._session.verbs == ["GET", "GET", "GET"]
    assert client._session.calls[1][1].endswith("/api/refresh")
    assert client.request_count == 3


def test_token_refresh_is_attempted_only_once() -> None:
    client = make_client()
    client._session = FakeSession(
        FakeResponse(401, {"meta": {"message": "token expired"}}),
        FakeResponse(200, {"success": True}),
        FakeResponse(401, {"meta": {"message": "token expired"}}),
    )

    response = client.get("user/CM-TEST/dashboard/CT-TEST")

    assert response.status_code == 401
    assert len(client._session.calls) == 3


def test_refresh_failure_raises_api_error() -> None:
    client = make_client()
    client._session = FakeSession(
        FakeResponse(401, {"meta": {"message": "token expired"}}),
        FakeResponse(500, {"success": False}),
    )

    with pytest.raises(OhmApiError) as excinfo:
        client.get("user/CM-TEST/dashboard/CT-TEST")

    assert "rafraîchissement" in str(excinfo.value)
