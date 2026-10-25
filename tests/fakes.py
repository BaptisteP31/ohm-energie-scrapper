"""Doubles HTTP minimalistes : aucun réseau, aucune vraie donnée."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

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


SYNTH_CUSTOMER = "CM-SYNTH"
SYNTH_CT = "CT-SYNTH-0001"
SYNTH_PDL = "12345678901234"
SYNTH_SECOND_CT = "CT-SYNTH-0002"
SYNTH_SECOND_PDL = "43210987654321"


def hourly_payload(values: list[float | None], colors: list[str] | None = None) -> dict[str, Any]:
    """Réponse ``consumption/kwh/{ct}/hours`` synthétique (Wh par demi-heure)."""
    colors = colors if colors is not None else ["bleu" if i < 16 or i >= 44 else "blanc" for i in range(len(values))]
    return {
        "success": True,
        "meta": {"status": 200, "message": ""},
        "body": {
            "consumptions": {
                "data": values,
                "dataString": [str(v) for v in values],
                "time": [f"{i // 2:02d}:{(i % 2) * 30:02d}" for i in range(len(values))],
                "heuresCreuseColors": colors,
            }
        },
    }


def synthetic_day_wh(day: date, index: int) -> int:
    """Profil déterministe : nuit basse (Wh), pointe du soir, variation par jour."""
    base = 150 if index < 10 else 260
    evening = 400 if 36 <= index < 42 else 0
    jitter = (day.day % 5) * 15 + (index % 4) * 5
    return base + evening + jitter


def synthetic_day_values(day: date) -> list[float]:
    return [float(synthetic_day_wh(day, index)) for index in range(48)]


class RoutedClient:
    """Client amont factice pour l'API v1 : une réponse par endpoint de ``ENDPOINTS_BY_NAME``.

    ``hourly`` reçoit le corps du POST horaire ``{date, pdl}`` et renvoie la charge utile.
    Aucun réseau, aucune vraie donnée. Les appels sont journalisés dans ``calls``.
    """

    def __init__(
        self,
        responses: dict[str, Any],
        hourly: Callable[[dict[str, Any]], Any] | None = None,
        ct: str = SYNTH_CT,
    ) -> None:
        from ohm_scraper.endpoints import ENDPOINTS_BY_NAME

        self.customer_number = SYNTH_CUSTOMER
        self.ct = ct
        self.responses = responses
        self.hourly = hourly
        self.calls: list[tuple[str, str, Any]] = []
        self.login_count = 0
        self.fail_login = False
        self.fail_network = False
        self._names = {
            endpoint.path(self.customer_number, self.ct): name
            for name, endpoint in ENDPOINTS_BY_NAME.items()
        }

    def login(self) -> dict[str, Any]:
        from ohm_scraper.client import OhmLoginError

        self.login_count += 1
        if self.fail_login:
            raise OhmLoginError(401, "identifiants refusés (synthétique)")
        return {"customer_nbr": self.customer_number, "currentContract": self.ct}

    def _resolve(self, path: str) -> str:
        if path not in self._names:
            raise AssertionError(f"chemin amont inattendu : {path}")
        return self._names[path]

    def get(self, path: str) -> FakeResponse:
        self.calls.append(("GET", path, None))
        if self.fail_network:
            import requests

            raise requests.ConnectionError("réseau indisponible (synthétique)")
        name = self._resolve(path)
        if name not in self.responses:
            return FakeResponse(404, {"success": False, "meta": {"status": 404, "message": "absent"}})
        return FakeResponse(200, self.responses[name])

    def post(self, path: str, json: Any = None) -> FakeResponse:
        self.calls.append(("POST", path, json))
        if self.fail_network:
            import requests

            raise requests.ConnectionError("réseau indisponible (synthétique)")
        name = self._resolve(path)
        if name == "consumption_hourly" and self.hourly is not None:
            return FakeResponse(200, self.hourly(json or {}))
        if name not in self.responses:
            return FakeResponse(404, {"success": False, "meta": {"status": 404, "message": "absent"}})
        return FakeResponse(200, self.responses[name])

    def hourly_calls(self) -> list[dict[str, Any]]:
        return [body for method, path, body in self.calls if method == "POST"]


class FakeClient:
    """Client factice pour la CLI (mêmes attributs publics que OhmClient)."""

    def __init__(self, get_payload: Any = None, post_payload: Any = None, fail: bool = False) -> None:
        self.customer_number = "CM-TEST"
        self.ct = "CT-TEST"
        self.get_payload = get_payload if get_payload is not None else {"success": True, "body": []}
        self.post_payload = post_payload if post_payload is not None else {"success": True, "body": {}}
        self.fail = fail
        self.calls: list[tuple[str, str, Any]] = []

    def login(self) -> dict[str, Any]:
        self.login_count = getattr(self, "login_count", 0) + 1
        return {"customer_nbr": self.customer_number, "currentContract": self.ct}

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
