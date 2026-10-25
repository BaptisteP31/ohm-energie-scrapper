"""Service HTTP REST en lecture seule pour Ohm Énergie.

Routes legacy (inchangées, dépréciées) :
- /health : vérification d'état (sans authentification ni appel amont)
- /endpoints : catalogue des endpoints documentés
- /data : liste des endpoints de données disponibles
- /data/{name} : données de l'endpoint demandé (avec cache TTL)
- /consumption : séries de consommation (hourly, daily, power-days, power-months)

Routes /v1 (contrat docs/openapi.yaml) : déléguées à ``ohm_scraper.api_v1``.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
import urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import requests

from ohm_scraper import api_v1, consumption
from ohm_scraper.analytics import TZ
from ohm_scraper.client import OhmApiError, OhmClient, OhmLoginError
from ohm_scraper.config import Config, load_config
from ohm_scraper.endpoints import (
    ALL_ENDPOINTS,
    DUMP_ENDPOINTS,
    ENDPOINTS_BY_NAME,
    Endpoint,
    EndpointError,
)
from ohm_scraper.problems import ApiProblem, unavailable, upstream_error

logger = logging.getLogger("ohm_scraper.server")
CONNECTION_DOWN = "Connexion à Ohm Énergie impossible. Réessayez plus tard."


class UpstreamNetworkError(RuntimeError):
    """Échec réseau vers Ohm Énergie (le message ne contient aucune donnée personnelle)."""


class UpstreamHTTPError(RuntimeError):
    """Réponse HTTP non 200 de Ohm Énergie."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"Erreur amont Ohm Énergie (HTTP {status_code})")
        self.status_code = status_code


class OhmService:
    """Gestionnaire de session amont Ohm Énergie avec cache TTL et verrouillage."""

    def __init__(self, config: Config, client: OhmClient | None = None) -> None:
        self.config = config
        self.client = client or OhmClient(config)
        self._lock = threading.Lock()
        self._logged_in = False
        self._login_state = "unknown"  # unknown, logged_in, logged_out
        self._last_success: datetime | None = None
        # cache : key -> (timestamp, data, content_type)
        self._cache: dict[str, tuple[float, Any, str]] = {}
        # last_refresh : endpoint_name -> timestamp
        self._last_refresh: dict[str, float] = {}

    def today(self) -> date:
        """Date locale (Europe/Paris) : référence des périodes relatives de l'API v1."""
        return datetime.now(TZ).date()

    @property
    def login_state(self) -> str:
        return self._login_state

    @property
    def last_successful_call_at(self) -> datetime | None:
        return self._last_success

    def _login(self) -> None:
        try:
            self.client.login()
        except OhmLoginError:
            self._login_state = "logged_out"
            self._logged_in = False
            raise
        self._logged_in = True
        self._login_state = "logged_in"

    def _ensure_login(self) -> None:
        """Connexion paresseuse (lazy login). Doit être appelé sous self._lock."""
        if not self._logged_in:
            logger.info("Connexion initiale à l'espace client Ohm Énergie...")
            self._login()

    def _request_with_relogin(
        self, method: str, path: str, json_body: Any = None
    ) -> Any:
        """Effectue un appel amont sous verrou avec re-connexion unique sur 401."""
        self._ensure_login()
        try:
            if method == "GET":
                response = self.client.get(path)
            else:
                response = self.client.post(path, json=json_body)
        except (OhmLoginError, OhmApiError):
            raise
        except requests.RequestException as exc:
            raise UpstreamNetworkError(f"Erreur réseau amont ({type(exc).__name__})") from exc

        # Si le jeton est expiré et n'a pas pu être rafraîchi (401 persistant), re-login unique
        if response.status_code == 401:
            logger.info("Statut 401 reçu, tentative de reconnexion unique...")
            self._login()
            if method == "GET":
                response = self.client.get(path)
            else:
                response = self.client.post(path, json=json_body)

        if response.status_code != 200:
            raise UpstreamHTTPError(response.status_code)

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Réponse amont non JSON") from exc
        self._last_success = datetime.now(TZ)
        return payload

    def fetch_json(self, cache_key: str, endpoint: Endpoint, body: Any = None) -> Any:
        """Appel amont de lecture (GET, ou POST de lecture) avec cache TTL, pour l'API v1.

        Les erreurs sont converties en :class:`ApiProblem` (503 : connexion ou réseau,
        502 : réponse invalide ou erreur amont, 429 : limitation amont).
        """
        cached = self._cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self.config.cache_ttl:
            return cached[1]

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < self.config.cache_ttl:
                return cached[1]
            try:
                self._ensure_login()
                path = endpoint.path(self.client.customer_number, self.client.ct)
                payload = self._request_with_relogin(endpoint.method, path, body)
            except OhmLoginError as exc:
                logger.warning("Connexion à Ohm Énergie refusée (HTTP %s)", exc.status_code)
                raise unavailable(CONNECTION_DOWN) from exc
            except (EndpointError, requests.RequestException, UpstreamNetworkError) as exc:
                logger.warning("Connexion à Ohm Énergie impossible (%s)", type(exc).__name__)
                raise unavailable(CONNECTION_DOWN) from exc
            except UpstreamHTTPError as exc:
                if exc.status_code == 429:
                    raise ApiProblem(
                        429, "rate-limited", "Trop de requêtes",
                        "Ohm Énergie limite le débit. Réessayez après le délai indiqué.",
                        {"Retry-After": "60"},
                    ) from exc
                raise upstream_error(f"Erreur amont Ohm Énergie (HTTP {exc.status_code}).") from exc
            except (OhmApiError, RuntimeError) as exc:
                logger.warning("Réponse amont invalide (%s)", type(exc).__name__)
                raise upstream_error("Réponse amont invalide.") from exc
            self._cache[cache_key] = (time.monotonic(), payload, "application/json")
            return payload

    def get_data(self, endpoint: Endpoint, refresh: bool = False) -> tuple[int, Any]:
        """Récupère les données d'un endpoint de lecture avec cache TTL et limite de refresh."""
        cache_key = f"endpoint:{endpoint.name}"
        now = time.monotonic()

        if refresh:
            last = self._last_refresh.get(endpoint.name, 0.0)
            if now - last < 60.0:
                return 429, {
                    "error": "Rafraîchissement limité à une fois toutes les 60 secondes par endpoint."
                }
        else:
            cached = self._cache.get(cache_key)
            if cached:
                ts, data, _ = cached
                if now - ts < self.config.cache_ttl:
                    return 200, data

        with self._lock:
            if not refresh:
                cached = self._cache.get(cache_key)
                if cached:
                    ts, data, _ = cached
                    if time.monotonic() - ts < self.config.cache_ttl:
                        return 200, data

            self._ensure_login()
            try:
                path = endpoint.path(self.client.customer_number, self.client.ct)
            except EndpointError as exc:
                return 500, {"error": str(exc)}

            try:
                data = self._request_with_relogin("GET", path)
            except (OhmLoginError, OhmApiError, RuntimeError) as exc:
                return 502, {"error": str(exc)}

            self._cache[cache_key] = (time.monotonic(), data, "application/json")
            if refresh:
                self._last_refresh[endpoint.name] = time.monotonic()

        return 200, data

    def get_consumption(
        self,
        granularity: str,
        date_from: str | None,
        date_to: str | None,
        output_format: str,
        refresh: bool = False,
    ) -> tuple[int, Any, str]:
        """Calcule et récupère les séries de consommation."""
        if granularity not in consumption.GRANULARITIES:
            return (
                400,
                {
                    "error": (
                        f"Granularité invalide : {granularity!r}. "
                        f"Choix possibles : {', '.join(consumption.GRANULARITIES)}"
                    )
                },
                "application/json",
            )

        if output_format not in ("json", "csv"):
            return (
                400,
                {"error": f"Format invalide : {output_format!r}. Choix possibles : json, csv"},
                "application/json",
            )

        try:
            start, end = consumption.resolve_range(granularity, date_from, date_to)
        except consumption.ConsumptionError as exc:
            return 400, {"error": str(exc)}, "application/json"

        refresh_key = f"consumption:{granularity}"
        cache_key = (
            f"consumption:{granularity}:{start.isoformat()}:{end.isoformat()}:{output_format}"
        )
        now = time.monotonic()

        if refresh:
            last = self._last_refresh.get(refresh_key, 0.0)
            if now - last < 60.0:
                return (
                    429,
                    {
                        "error": "Rafraîchissement limité à une fois toutes les 60 secondes par endpoint."
                    },
                    "application/json",
                )
        else:
            cached = self._cache.get(cache_key)
            if cached:
                ts, data, ctype = cached
                if now - ts < self.config.cache_ttl:
                    return 200, data, ctype

        with self._lock:
            if not refresh:
                cached = self._cache.get(cache_key)
                if cached:
                    ts, data, ctype = cached
                    if time.monotonic() - ts < self.config.cache_ttl:
                        return 200, data, ctype

            self._ensure_login()
            responses: list[tuple[str, Any]] = []

            try:
                if granularity in consumption.PER_DAY_GRANULARITIES:
                    data_endpoint = ENDPOINTS_BY_NAME["consumption_kwh_data"]
                    data_path = data_endpoint.path(
                        self.client.customer_number, self.client.ct
                    )
                    kwh_payload = self._request_with_relogin("GET", data_path)
                    pdl = consumption.extract_pdl(kwh_payload)
                    if not pdl:
                        return (
                            502,
                            {
                                "error": "PDL introuvable dans body.others.pdl : la courbe horaire est indisponible pour ce compte."
                            },
                            "application/json",
                        )

                    hourly_endpoint = ENDPOINTS_BY_NAME["consumption_hourly"]
                    hourly_path = hourly_endpoint.path(
                        self.client.customer_number, self.client.ct
                    )
                    for day in consumption.iter_days(start, end):
                        body = consumption.hourly_body(day, pdl)
                        payload = self._request_with_relogin("POST", hourly_path, body)
                        responses.append((day.isoformat(), payload))
                else:
                    mapping = {
                        "power-days": "consumption_power_days",
                        "power-months": "consumption_power_months",
                    }
                    endpoint = ENDPOINTS_BY_NAME[mapping[granularity]]
                    path = endpoint.path(self.client.customer_number, self.client.ct)
                    body = consumption.range_body(start, end)
                    payload = self._request_with_relogin("POST", path, body)
                    responses.append((f"{start.isoformat()}..{end.isoformat()}", payload))
            except (OhmLoginError, OhmApiError, RuntimeError, EndpointError) as exc:
                return 502, {"error": str(exc)}, "application/json"

            rows = consumption.flatten(granularity, responses)
            if output_format == "csv":
                rendered = consumption.rows_to_csv(rows)
                ctype = "text/csv; charset=utf-8"
            else:
                rendered = consumption.json_document(granularity, start, end, rows, responses)
                ctype = "application/json"

            self._cache[cache_key] = (time.monotonic(), rendered, ctype)
            if refresh:
                self._last_refresh[refresh_key] = time.monotonic()

        return 200, rendered, ctype


class OhmRequestHandler(BaseHTTPRequestHandler):
    """Handler HTTP REST gérant /health, /endpoints, /data et /consumption."""

    server: OhmServer

    def log_message(self, format: str, *args: Any) -> None:
        # Ne journalise jamais d'identifiants, de jetons ou d'en-têtes sensibles
        logger.info("%s - - %s", self.address_string(), format % args)

    def _send_json(self, status_code: int, data: Any) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_csv(self, status_code: int, csv_text: str) -> None:
        payload = csv_text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_reply(self, reply: api_v1.Reply) -> None:
        self.send_response(reply.status)
        self.send_header("Content-Type", reply.content_type)
        self.send_header("Content-Length", str(len(reply.body)))
        for name, value in reply.headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(reply.body)

    def _send_problem(self, problem: ApiProblem) -> None:
        payload = json.dumps(problem.body(), ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(problem.status)
        self.send_header("Content-Type", "application/problem+json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for name, value in problem.headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _auth_error(self) -> str | None:
        """Détail de l'erreur d'authentification, ou None si l'accès est autorisé."""
        api_token = self.server.service.config.api_token
        if not api_token:
            return None

        auth_header = self.headers.get("Authorization", "").strip()
        if not auth_header.startswith("Bearer "):
            return "Authentification requise : en-tête Authorization: Bearer <token> manquant ou invalide."

        token = auth_header[7:].strip()
        if not hmac.compare_digest(token.encode("utf-8"), api_token.encode("utf-8")):
            return "Jeton d'authentification Bearer invalide."
        return None

    def _check_auth(self) -> bool:
        error = self._auth_error()
        if error is not None:
            self._send_json(401, {"error": error})
            return False
        return True

    def _handle_v1(self, path: str, query: dict[str, list[str]]) -> None:
        error = self._auth_error()
        if error is not None:
            self._send_problem(
                ApiProblem(401, "unauthorized", "Authentification requise", error,
                           {"WWW-Authenticate": "Bearer"})
            )
            return
        try:
            reply = api_v1.handle(
                self.server.service, "GET", path, query, accept=self.headers.get("Accept", "")
            )
        except ApiProblem as problem:
            self._send_problem(problem)
            return
        except Exception:  # noqa: BLE001 - jamais de détail interne vers le client
            logger.exception("Erreur interne de l'API v1")
            self._send_problem(ApiProblem(500, "internal-error", "Erreur interne", "Erreur interne du service."))
            return
        self._send_reply(reply)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)

        # /health : accessible sans authentification et sans appel amont
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        # Routes /v1 : authentification et erreurs au format problem+json
        if path == "/v1" or path.startswith("/v1/"):
            self._handle_v1(path, urllib.parse.parse_qs(parsed.query, keep_blank_values=True))
            return

        # Toutes les autres routes requièrent l'authentification si OHM_API_TOKEN est configuré
        if not self._check_auth():
            return

        # /endpoints : catalogue des routes de lecture
        if path == "/endpoints":
            endpoints_list = [
                {
                    "name": e.name,
                    "method": e.method,
                    "template": e.template,
                    "path_template": e.template,
                    "category": e.category,
                    "description": e.description,
                }
                for e in ALL_ENDPOINTS
            ]
            self._send_json(200, {"endpoints": endpoints_list})
            return

        # /data : liste des endpoints de données disponibles
        if path == "/data":
            data_list = [
                {
                    "name": e.name,
                    "method": e.method,
                    "template": e.template,
                    "path_template": e.template,
                    "category": e.category,
                    "description": e.description,
                    "url": f"/data/{e.name}",
                }
                for e in DUMP_ENDPOINTS
            ]
            self._send_json(200, {"endpoints": data_list, "names": [e.name for e in DUMP_ENDPOINTS]})
            return

        # /data/{name} : données pour un endpoint spécifique
        if path.startswith("/data/"):
            name = path[len("/data/"):].strip("/")
            if name not in {e.name for e in DUMP_ENDPOINTS}:
                known = ", ".join(sorted(e.name for e in DUMP_ENDPOINTS))
                self._send_json(
                    404,
                    {"error": f"Endpoint inconnu : {name!r}. Endpoints disponibles : {known}"},
                )
                return

            endpoint = ENDPOINTS_BY_NAME[name]
            refresh = query.get("refresh", ["0"])[0] in ("1", "true", "yes")
            status, result = self.server.service.get_data(endpoint, refresh=refresh)
            self._send_json(status, result)
            return

        # /consumption : séries de consommation
        if path == "/consumption":
            granularity = query.get("granularity", ["daily"])[0]
            date_from = query.get("from", [None])[0]
            date_to = query.get("to", [None])[0]
            fmt = query.get("format", ["json"])[0]
            refresh = query.get("refresh", ["0"])[0] in ("1", "true", "yes")

            status, result, ctype = self.server.service.get_consumption(
                granularity, date_from, date_to, fmt, refresh=refresh
            )
            if status != 200 or ctype == "application/json":
                self._send_json(status, result)
            else:
                self._send_csv(status, result)
            return

        # Route non reconnue
        self._send_json(404, {"error": f"Route non trouvée : {path}"})

    def _method_not_allowed(self, method: str) -> None:
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        if path == "/v1" or path.startswith("/v1/"):
            self._send_problem(
                ApiProblem(
                    405, "method-not-allowed", "Méthode non autorisée",
                    f"Méthode {method} non autorisée. Seul GET est supporté.",
                    {"Allow": "GET"},
                )
            )
            return
        self._send_json(405, {"error": f"Méthode {method} non autorisée. Seul GET est supporté."})

    def do_POST(self) -> None:
        self._method_not_allowed("POST")

    def do_PUT(self) -> None:
        self._method_not_allowed("PUT")

    def do_DELETE(self) -> None:
        self._method_not_allowed("DELETE")

    def do_PATCH(self) -> None:
        self._method_not_allowed("PATCH")


class OhmServer(ThreadingHTTPServer):
    """Serveur HTTP multi-thread avec injection du service Ohm."""

    def __init__(self, server_address: tuple[str, int], service: OhmService) -> None:
        self.service = service
        super().__init__(server_address, OhmRequestHandler)


def create_server(
    host: str | None = None,
    port: int | None = None,
    config: Config | None = None,
    client: OhmClient | None = None,
) -> OhmServer:
    """Instancie le serveur HTTP sans le démarrer (utile pour tests et CLI)."""
    cfg = config or load_config()
    bind_host = host if host is not None else cfg.service_host
    bind_port = port if port is not None else cfg.service_port
    service = OhmService(cfg, client=client)
    server = OhmServer((bind_host, bind_port), service)
    server.daemon_threads = True
    return server


def run_server(
    host: str | None = None,
    port: int | None = None,
    config: Config | None = None,
) -> int:
    """Point d'entrée du serveur HTTP."""
    try:
        server = create_server(host=host, port=port, config=config)
    except RuntimeError as exc:
        logger.error("Impossible de démarrer le service : %s", exc)
        return 1

    bind_host, bind_port = server.server_address[:2]
    print(f"Service HTTP Ohm Scraper démarré sur http://{bind_host}:{bind_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du service HTTP demandé...")
    finally:
        server.server_close()
    return 0
