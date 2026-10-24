import logging
import re
import time
from typing import Any

import requests

from ohm_scraper.config import Config

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15  # secondes, appliqué à chaque requête
REQUEST_INTERVAL = 1.0  # secondes minimum entre deux requêtes
ESPACE_CLIENT_API = "https://espace-client.ohm-energie.com/api"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class OhmApiError(RuntimeError):
    """Erreur de l'API. Le message ne contient jamais de donnée personnelle."""


class OhmLoginError(OhmApiError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"connexion refusée (HTTP {status_code}) : {message}")
        self.status_code = status_code
        self.message = message


def _meta(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    meta = payload.get("meta") if isinstance(payload, dict) else None
    return meta if isinstance(meta, dict) else {}


def _first_contract(contracts: Any) -> str | None:
    if not isinstance(contracts, list) or not contracts:
        return None
    first = contracts[0]
    if isinstance(first, dict):
        first = first.get("contract_nbr")
    return str(first) if first else None


class OhmClient:
    """Client de l'espace client Ohm Énergie.

    L'authentification repose sur le cookie `_token` posé par /api/login, conservé
    par requests.Session. Aucune donnée d'identification n'est journalisée.
    """

    def __init__(self, config: Config) -> None:
        self._login = config.login.lower() if EMAIL_RE.match(config.login) else config.login
        self._password = config.password
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._last_request = 0.0
        self.request_count = 0
        self.customer_number: str | None = config.customer_number
        self.ct: str | None = config.ct
        self.user: dict[str, Any] = {}

    # ------------------------------------------------------------------ HTTP

    def _throttle(self) -> None:
        wait = REQUEST_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
        self.request_count += 1

    def _request(self, method: str, path: str, json: Any = None, retry: bool = True) -> requests.Response:
        self._throttle()
        url = f"{ESPACE_CLIENT_API}/{path.lstrip('/')}"
        response = self._session.request(method, url, json=json, timeout=REQUEST_TIMEOUT)
        if retry and response.status_code == 401 and _meta(response).get("message") == "token expired":
            logger.info("Jeton expiré : rafraîchissement puis nouvel essai unique")
            self._refresh()
            return self._request(method, path, json=json, retry=False)
        return response

    def _refresh(self) -> None:
        self._throttle()
        response = self._session.get(f"{ESPACE_CLIENT_API}/refresh", timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            raise OhmApiError(f"rafraîchissement du jeton échoué (HTTP {response.status_code})")

    def get(self, path: str) -> requests.Response:
        """GET relatif à espace-client.../api, ex. 'user/{number}/dashboard/{ct}'."""
        return self._request("GET", path)

    def post(self, path: str, json: Any = None) -> requests.Response:
        """POST relatif à espace-client.../api."""
        return self._request("POST", path, json=json)

    # ----------------------------------------------------------------- login

    def login(self) -> dict[str, Any]:
        """Connexion unique (POST /api/login). Renseigne customer_number et ct si absents du .env."""
        self._throttle()
        response = self._session.post(
            f"{ESPACE_CLIENT_API}/login",
            json={"email": self._login, "password": self._password},
            timeout=REQUEST_TIMEOUT,
        )
        meta = _meta(response)
        status = meta.get("status", response.status_code)
        if response.status_code != 200 or status != 200:
            raise OhmLoginError(response.status_code, str(meta.get("message", "")))

        try:
            payload = response.json()
        except ValueError as exc:
            raise OhmApiError("réponse de login non JSON") from exc
        body = payload.get("body") or {}
        if body.get("reauthenticate"):
            raise OhmApiError("compte nécessitant une réauthentification (multi-comptes) : non géré")
        user = body.get("user")
        if not isinstance(user, dict):
            raise OhmApiError("réponse de login sans body.user")
        self.user = user

        account_nbr = user.get("customer_nbr")
        if not self.customer_number:
            self.customer_number = str(account_nbr) if account_nbr else None
        elif account_nbr and str(account_nbr) != self.customer_number:
            logger.warning("OHM_CUSTOMER_NUMBER de .env diffère de la réponse de login (valeurs non affichées)")

        if not self.ct:
            contract = user.get("currentContract") or _first_contract(user.get("elec_contracts")) \
                or _first_contract(user.get("gaz_contracts"))
            self.ct = str(contract) if contract else None

        logger.info(
            "Connexion OK (cookie _token %s)",
            "présent" if self._session.cookies.get("_token") else "absent",
        )
        return user

    # ----------------------------------------------------------- consumption

    def get_consumption_six_months(self) -> Any:
        return self._get_consumption("consumption/six-months")

    def get_consumption_last_month(self) -> Any:
        return self._get_consumption("consumption/last-month")

    def _get_consumption(self, route: str) -> Any:
        if not self.customer_number or not self.ct:
            raise RuntimeError("Numéro client ou contrat (ct) inconnu : appeler login() ou renseigner .env.")
        response = self.get(f"user/{self.customer_number}/{route}/{self.ct}")
        response.raise_for_status()
        return response.json()
