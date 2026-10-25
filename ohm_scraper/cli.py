"""Interface en ligne de commande : ``python -m ohm_scraper``.

Sous-commandes :

* ``dump``        : connexion unique puis écriture JSON de chaque endpoint de lecture ;
* ``consumption`` : série de consommation horaire, journalière ou mensuelle ;
* ``discover``    : inventaire de la forme des réponses (docs/inventory.md).

Aucun jeton, mot de passe, identifiant ou réponse brute n'est affiché en console.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ohm_scraper import consumption
from ohm_scraper.endpoints import (
    DUMP_ENDPOINTS,
    ENDPOINTS_BY_NAME,
    Endpoint,
    EndpointError,
    render_endpoint_list,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------- helpers


def _safe_server_message(message: str | None) -> str:
    """Message serveur court et non identifiant (jamais de chiffre ni d'arobase)."""
    text = (message or "").strip()
    if len(text) > 80 or any(char.isdigit() for char in text) or "@" in text:
        return ""
    return text


def _connect() -> Any | None:
    """Charge la configuration et se connecte une seule fois. ``None`` si échec."""
    import requests

    from ohm_scraper.client import OhmApiError, OhmClient, OhmLoginError
    from ohm_scraper.config import load_config

    try:
        config = load_config()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return None

    client = OhmClient(config)
    try:
        client.login()
    except OhmLoginError as exc:
        detail = _safe_server_message(exc.message)
        suffix = f" Message : {detail}" if detail else ""
        print(
            f"Connexion refusée (HTTP {exc.status_code}).{suffix}\n"
            "Vérifiez OHM_LOGIN et OHM_PASSWORD dans .env (voir la section Dépannage du README).",
            file=sys.stderr,
        )
        return None
    except (OhmApiError, requests.RequestException) as exc:
        print(f"Connexion impossible : {type(exc).__name__}.", file=sys.stderr)
        return None
    return client


def _parse_names(raw: str) -> list[str]:
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise EndpointError("--only ne contient aucun nom d'endpoint")
    names = list(dict.fromkeys(names))
    for name in names:
        if name not in {endpoint.name for endpoint in DUMP_ENDPOINTS}:
            available = ", ".join(endpoint.name for endpoint in DUMP_ENDPOINTS)
            raise EndpointError(f"endpoint inconnu pour dump : {name!r}. Disponibles : {available}")
    return names


def _extract_json(response: Any) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError("réponse non JSON") from exc


def _request_json(client: Any, endpoint: Endpoint, body: dict[str, Any] | None = None) -> Any:
    import requests

    from ohm_scraper.client import OhmApiError

    try:
        path = endpoint.path(client.customer_number, client.ct)
    except EndpointError as exc:
        raise RuntimeError(f"{endpoint.name} : {exc}") from exc
    try:
        if body is None:
            response = client.get(path)
        else:
            response = client.post(path, json=body)
    except requests.RequestException as exc:
        raise RuntimeError(f"{endpoint.name} : erreur réseau ({type(exc).__name__})") from exc
    except OhmApiError as exc:
        raise RuntimeError(f"{endpoint.name} : {exc}") from exc
    if response.status_code != 200:
        raise RuntimeError(f"{endpoint.name} : HTTP {response.status_code}")
    try:
        return _extract_json(response)
    except ValueError as exc:
        raise RuntimeError(f"{endpoint.name} : réponse non JSON") from exc


# ---------------------------------------------------------------------- dump


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_dump(args: argparse.Namespace) -> int:
    try:
        selected = _parse_names(args.only) if args.only else [e.name for e in DUMP_ENDPOINTS]
    except EndpointError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    client = _connect()
    if client is None:
        return 1

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = PROJECT_ROOT / "data" / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for name in selected:
        endpoint = ENDPOINTS_BY_NAME[name]
        try:
            payload = _request_json(client, endpoint)
        except RuntimeError as exc:
            failures += 1
            print(f"{name} : échec ({exc})", file=sys.stderr)
            continue
        _write_json(output_dir / f"{name}.json", payload)
        print(f"{name} : HTTP 200")

    print(
        f"{len(selected) - failures}/{len(selected)} réponse(s) écrite(s) dans {output_dir}",
        file=sys.stderr,
    )
    return 0 if failures == 0 else 1


# --------------------------------------------------------------- consumption


def _consumption_endpoint(granularity: str) -> Endpoint:
    mapping = {
        "power-days": "consumption_power_days",
        "power-months": "consumption_power_months",
    }
    return ENDPOINTS_BY_NAME[mapping[granularity]]


def run_consumption(args: argparse.Namespace) -> int:
    try:
        start, end = consumption.resolve_range(
            args.granularity, args.date_from, args.date_to
        )
    except consumption.ConsumptionError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    client = _connect()
    if client is None:
        return 1

    requests_to_make: list[tuple[str, Endpoint, dict[str, Any]]] = []
    if args.granularity in consumption.PER_DAY_GRANULARITIES:
        try:
            data_endpoint = ENDPOINTS_BY_NAME["consumption_kwh_data"]
            payload = _request_json(client, data_endpoint)
        except RuntimeError as exc:
            print(f"PDL indisponible ({exc}).", file=sys.stderr)
            return 1
        pdl = consumption.extract_pdl(payload)
        if not pdl:
            print(
                "PDL introuvable dans body.others.pdl : la courbe horaire est indisponible "
                "pour ce compte.",
                file=sys.stderr,
            )
            return 1
        endpoint = ENDPOINTS_BY_NAME["consumption_hourly"]
        for day in consumption.iter_days(start, end):
            requests_to_make.append(
                (day.isoformat(), endpoint, consumption.hourly_body(day, pdl))
            )
    else:
        endpoint = _consumption_endpoint(args.granularity)
        label = f"{start.isoformat()}..{end.isoformat()}"
        requests_to_make.append((label, endpoint, consumption.range_body(start, end)))

    responses: list[tuple[str, Any]] = []
    total = len(requests_to_make)
    for index, (label, endpoint, body) in enumerate(requests_to_make, start=1):
        try:
            payload = _request_json(client, endpoint, body)
        except RuntimeError as exc:
            print(f"[{index}/{total}] {endpoint.name} : {exc}", file=sys.stderr)
            print("Série incomplète : aucun fichier écrit.", file=sys.stderr)
            return 1
        print(f"[{index}/{total}] {endpoint.name} : HTTP 200", file=sys.stderr)
        responses.append((label, payload))

    rows = consumption.flatten(args.granularity, responses)
    text = consumption.render_output(
        args.granularity, start, end, rows, responses, args.output_format
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(f"{len(rows)} ligne(s) écrite(s) dans {output_path}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


# ------------------------------------------------------------------ discover


def run_discover(args: argparse.Namespace) -> int:
    try:
        import discover  # module historique à la racine du projet
    except ImportError:
        print(
            "Commande discover indisponible : lancez-la depuis la racine du dépôt "
            "(python -m ohm_scraper discover).",
            file=sys.stderr,
        )
        return 1
    return discover.main()


# --------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ohm_scraper",
        description=(
            "Accès en lecture seule à l'espace client Ohm Énergie "
            "(API non officielle, usage personnel)."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    dump = subparsers.add_parser(
        "dump",
        help="écrit les réponses JSON des endpoints de lecture dans data/<horodatage>/",
        description=(
            "Une seule connexion, puis les endpoints de lecture allowlistés. "
            "Les réponses sont écrites dans data/<horodatage>/<nom>.json."
        ),
    )
    dump.add_argument(
        "--only",
        metavar="NOM[,NOM]",
        help="ne récupérer que ces endpoints (noms courts, séparés par des virgules)",
    )
    dump.add_argument(
        "--list",
        action="store_true",
        help="afficher les noms d'endpoints disponibles et quitter (aucun accès réseau)",
    )
    dump.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="dossier de sortie (défaut : data/<horodatage>)",
    )

    conso = subparsers.add_parser(
        "consumption",
        help="récupérer une série de consommation (horaire, journalière en kWh ou puissance)",
        description=(
            "Séries hourly et daily (kWh, calculée depuis la courbe de charge) : une requête "
            "par jour, plafond 31 jours. Séries power-days et power-months (puissance "
            "maximale en kVA) : une requête sur la plage demandée."
        ),
    )
    conso.add_argument(
        "--granularity",
        choices=consumption.GRANULARITIES,
        default="daily",
        help="granularité de la série (défaut : daily)",
    )
    conso.add_argument(
        "--from",
        dest="date_from",
        metavar="DATE",
        help="début de la plage (jj/mm/aaaa ou aaaa-mm-jj ; défaut selon la granularité)",
    )
    conso.add_argument(
        "--to",
        dest="date_to",
        metavar="DATE",
        help="fin de la plage (jj/mm/aaaa ou aaaa-mm-jj ; défaut : hier)",
    )
    conso.add_argument(
        "--format",
        dest="output_format",
        choices=("json", "csv"),
        default="json",
        help="format de sortie (défaut : json)",
    )
    conso.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="FICHIER",
        help="fichier de sortie (défaut : sortie standard)",
    )

    subparsers.add_parser(
        "discover",
        help="régénérer docs/inventory.md (forme des réponses, valeurs masquées)",
    )
    serve = subparsers.add_parser(
        "serve",
        help="démarrer l'API HTTP locale (accès en lecture seule)",
        description=(
            "Démarre un service HTTP local exposant les données de l'espace client "
            "Ohm Énergie (/health, /endpoints, /data, /consumption)."
        ),
    )
    serve.add_argument(
        "--host",
        metavar="HÔTE",
        help="adresse d'écoute (défaut : SERVICE_HOST ou 127.0.0.1)",
    )
    serve.add_argument(
        "--port",
        type=int,
        metavar="PORT",
        help="port d'écoute (défaut : SERVICE_PORT ou 8080)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "dump":
        if args.list:
            print(render_endpoint_list())
            return 0
        return run_dump(args)
    if args.command == "consumption":
        return run_consumption(args)
    if args.command == "discover":
        return run_discover(args)
    if args.command == "serve":
        from ohm_scraper.server import run_server
        return run_server(host=args.host, port=args.port)
    parser.error("sous-commande inconnue")
    return 2
