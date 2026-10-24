"""Doubles HTTP minimalistes : aucun réseau, aucune vraie donnée."""

from __future__ import annotations

from typing import Any

from requests.cookies import RequestsCookieJar


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {"Content-Type": "application/json"}
        self.content = b""

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Rejoue des réponses dans l'ordre, quel que soit le verbe HTTP."""

    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, Any]] = []
        self.cookies = RequestsCookieJar()
        self.headers: dict[str, str] = {}

    def _next(self, method: str, url: str, json: Any) -> FakeResponse:
        self.calls.append((method, url, json))
        if not self.responses:
            raise AssertionError(f"réponse non prévue pour {method} {url}")
        return self.responses.pop(0)

    def request(self, method: str, url: str, json: Any = None, timeout: float | None = None) -> FakeResponse:
        return self._next(method, url, json)

    def get(self, url: str, timeout: float | None = None, **kwargs: Any) -> FakeResponse:
        return self._next("GET", url, None)

    def post(self, url: str, json: Any = None, timeout: float | None = None, **kwargs: Any) -> FakeResponse:
        return self._next("POST", url, json)

    @property
    def verbs(self) -> list[str]:
        return [method for method, _, _ in self.calls]


class FakeClient:
    """Client factice pour la CLI (mêmes attributs publics que OhmClient)."""

    def __init__(self, get_payload: Any = None, post_payload: Any = None, fail: bool = False) -> None:
        self.customer_number = "CM-TEST"
        self.ct = "CT-TEST"
        self.get_payload = get_payload if get_payload is not None else {"success": True, "body": []}
        self.post_payload = post_payload if post_payload is not None else {"success": True, "body": {}}
        self.fail = fail
        self.calls: list[tuple[str, str, Any]] = []

    def get(self, path: str) -> FakeResponse:
        self.calls.append(("GET", path, None))
        if self.fail:
            return FakeResponse(500, {"success": False, "meta": {"status": 500, "message": "erreur"}})
        return FakeResponse(200, self.get_payload)

    def post(self, path: str, json: Any = None) -> FakeResponse:
        self.calls.append(("POST", path, json))
        if self.fail:
            return FakeResponse(500, {"success": False, "meta": {"status": 500, "message": "erreur"}})
        return FakeResponse(200, self.post_payload)
