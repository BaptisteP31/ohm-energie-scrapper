"""Inventaire en lecture seule de l'espace client Ohm Énergie.

Lancement :
    python -m ohm_scraper discover
    # ou, directement :
    .venv/bin/python discover.py

Une seule connexion, puis uniquement les endpoints de lecture du catalogue
(voir ohm_scraper/endpoints.py).
Seule la forme des réponses est écrite dans docs/inventory.md : aucune valeur
personnelle, aucun jeton, aucune réponse brute n'est enregistré sur disque.
"""

import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Mode -I : le dossier du script n'est plus ajouté au sys.path, on l'ajoute explicitement.
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402

from ohm_scraper.client import OhmApiError, OhmClient, OhmLoginError  # noqa: E402
from ohm_scraper.config import load_config  # noqa: E402
from ohm_scraper.endpoints import (  # noqa: E402
    DUMP_ENDPOINTS,
    EXCLUDED_ENDPOINTS,
    HOURLY_ENDPOINT,
    EndpointError,
)

INVENTORY_PATH = PROJECT_ROOT / "docs" / "inventory.md"
MAX_REQUESTS = 60  # login et rafraîchissement compris
MAX_DEPTH = 6
MAX_KEYS = 80

# Allowlist et exclusions : voir ohm_scraper/endpoints.py (source unique).
#
# Seul POST autorisé pour l'inventaire : la courbe horaire
# user/{number}/consumption/kwh/{ct}/hours, corps {date, pdl}, date jj/mm/aaaa.
# Le pdl vient de body.others.pdl de GET consumption/kwh/{ct}/data.

# ----------------------------------------------------------------- schéma


ID_KEY = re.compile(r"^(CM-\w+|\d{5,}|(?=.*\d)[A-Za-z0-9_-]{16,})$")
SENSITIVE_KEY = re.compile(
    r"mail|phone|tel|iban|bic|naiss|birth|nom|name|prenom|firstname|lastname|adresse|address|"
    r"street|rue|zip|postal|city|ville|token|password|pdl|prm|customer|contract|linky|sponsor|"
    r"parrain|number|nbr|numero|ref|co_|additional|siret|cocontract|invoice|payment",
    re.IGNORECASE,
)
CONSO_KEY = re.compile(r"kwh|conso|consumption|co2|puissance|power|kva", re.IGNORECASE)
# Clés qui ne figurent pas dans SENSITIVE_KEY mais portent un identifiant.
EXTRA_SENSITIVE_KEY = re.compile(r"^ct$|login|cookie|passwd", re.IGNORECASE)


def to_iso(text: str) -> str | None:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:$|[T ])", text)
    if match:
        return f"{match[1]}-{match[2]}-{match[3]}"
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        return f"{match[3]}-{match[2]}-{match[1]}"
    return None


def normalise_key(raw: Any) -> str:
    key = str(raw)
    if to_iso(key):
        return "<date>"
    if "@" in key or ID_KEY.match(key):
        return "<redacted:id>"
    return key


class Node:
    def __init__(self) -> None:
        self.types: set[str] = set()
        self.children: dict[str, "Node"] = {}
        self.item: "Node | None" = None
        self.instances = 0  # nombre d'objets fusionnés dans ce nœud
        self.present = 0  # nombre de fois où ce nœud (clé) est apparu dans son parent
        self.lengths: list[int] = []
        self.dates: list[str] = []
        self.nums: list[float] = []


def merge(node: Node, value: Any, key_name: str = "") -> None:
    sensitive = bool(SENSITIVE_KEY.search(key_name))
    if isinstance(value, dict):
        node.types.add("objet")
        node.instances += 1
        for raw_key, child_value in value.items():
            child = node.children.setdefault(normalise_key(raw_key), Node())
            child.present += 1
            merge(child, child_value, str(raw_key))
    elif isinstance(value, list):
        node.types.add("tableau")
        node.lengths.append(len(value))
        if node.item is None:
            node.item = Node()
        for element in value:
            merge(node.item, element, key_name)
    elif value is None:
        node.types.add("null")
    elif isinstance(value, bool):
        node.types.add("booléen")
    elif isinstance(value, (int, float)):
        node.types.add("nombre")
        if CONSO_KEY.search(key_name):
            node.nums.append(float(value))
    elif isinstance(value, str):
        iso = to_iso(value)
        if iso:
            node.types.add("date")
            if not sensitive:
                node.dates.append(iso)
        else:
            node.types.add("chaîne")


def _identifying_key(key_name: str) -> bool:
    return bool(SENSITIVE_KEY.search(key_name) or EXTRA_SENSITIVE_KEY.search(key_name))


def collect_sensitive(value: Any, key_name: str, sink: set[str]) -> None:
    """Valeurs à ne jamais voir dans le rapport (sert au contrôle de fuite).

    Seules les valeurs réellement identifiantes sont retenues : adresses e-mail,
    identifiants (client, contrat, PDL, jeton…) et chaînes d'au moins 6 caractères
    sous une clé sensible. Les valeurs courtes inoffensives (« 2026 », « kWh »,
    un code d'énumération) sont ignorées : le contrôle ne doit pas bloquer pour elles.
    """
    if isinstance(value, dict):
        for raw_key, child in value.items():
            if "@" in str(raw_key) or ID_KEY.match(str(raw_key)):
                sink.add(str(raw_key))
            collect_sensitive(child, str(raw_key), sink)
    elif isinstance(value, list):
        for element in value:
            collect_sensitive(element, key_name, sink)
    elif isinstance(value, str):
        text = value.strip()
        if len(text) < 3 or to_iso(text):
            return  # les dates sont autorisées dans le rapport
        if "@" in text:
            sink.add(text)
        elif len(text) >= 6 and _identifying_key(key_name):
            sink.add(text)


def describe(node: Node) -> str:
    parts: list[str] = []
    for kind in sorted(node.types):
        if kind == "objet":
            parts.append(f"objet ({len(node.children)} clés)")
        elif kind == "tableau":
            low, high = min(node.lengths), max(node.lengths)
            parts.append(f"tableau (longueur {low})" if low == high else f"tableau (longueur {low} à {high})")
        elif kind == "date":
            if node.dates:
                parts.append(f"date (du {min(node.dates)} au {max(node.dates)})")
            else:
                parts.append("date")
        elif kind == "nombre" and node.nums:
            parts.append(f"nombre (min {min(node.nums):g}, max {max(node.nums):g})")
        else:
            parts.append(kind)
    return " ou ".join(parts) or "vide"


def render(node: Node, name: str, depth: int, out: list[str], parent_instances: int | None) -> None:
    indent = "  " * depth
    presence = ""
    if parent_instances and node.present < parent_instances:
        presence = f" (présent dans {node.present}/{parent_instances})"
    out.append(f"{indent}- `{name}` : {describe(node)}{presence}")
    if depth >= MAX_DEPTH:
        return
    children = list(node.children.items())
    for child_name, child in children[:MAX_KEYS]:
        render(child, child_name, depth + 1, out, node.instances)
    if len(children) > MAX_KEYS:
        out.append(f"{indent}  - … {len(children) - MAX_KEYS} clés supplémentaires")
    if node.item is not None:
        render(node.item, "[]", depth + 1, out, None)


def shape_lines(payload: Any) -> list[str]:
    root = Node()
    merge(root, payload)
    out: list[str] = []
    render(root, "(racine)", 0, out, None)
    return out


# ------------------------------------------------------------ exécution


@dataclass
class Outcome:
    category: str
    label: str
    method: str
    template: str
    status: int | None = None
    kind: str = ""  # "json", "vide", "binaire", "erreur"
    lines: list[str] = field(default_factory=list)
    note: str = ""
    payload: Any = None  # gardé en mémoire seulement, jamais écrit


def _meta_message(response: requests.Response) -> str:
    try:
        meta = response.json().get("meta") or {}
        message = str(meta.get("message", ""))
    except (ValueError, AttributeError):
        return ""
    return message if len(message) <= 80 and not re.search(r"\d|@", message) else ""


def _yesterday() -> str:
    return (date.today() - timedelta(days=1)).strftime("%d/%m/%Y")


def _extract_pdl(user: dict[str, Any]) -> str | None:
    value = user.get("pdl")
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("pdl") or value.get("prm") or value.get("number")
    return str(value) if value else None


def _pdl_from_consumption_data(payload: Any) -> str | None:
    """PDL utilisé par la SPA : body.others.pdl de GET consumption/kwh/{ct}/data."""
    if not isinstance(payload, dict):
        return None
    body = payload.get("body")
    if not isinstance(body, dict):
        return None
    others = body.get("others")
    if not isinstance(others, dict):
        return None
    value = others.get("pdl") or others.get("prm")
    return str(value) if value else None


def _run(
    client: OhmClient,
    outcome: Outcome,
    path: str,
    body: dict[str, Any] | None,
    keep_payload: bool = False,
) -> None:
    if client.request_count >= MAX_REQUESTS:
        outcome.kind = "erreur"
        outcome.note = "non appelé : plafond de requêtes atteint"
        return
    try:
        if body is None:
            response = client.get(path)
        else:
            response = client.post(path, json=body)
    except requests.RequestException as exc:
        outcome.kind = "erreur"
        outcome.note = f"erreur réseau ({type(exc).__name__})"
        return
    except OhmApiError as exc:
        outcome.kind = "erreur"
        outcome.note = str(exc)
        return

    outcome.status = response.status_code
    content_type = response.headers.get("Content-Type", "")
    if "json" not in content_type:
        outcome.kind = "binaire" if response.content else "vide"
        outcome.note = f"type {content_type or 'inconnu'}, {len(response.content)} octets"
        return
    try:
        payload = response.json()
    except ValueError:
        outcome.kind = "erreur"
        outcome.note = "réponse non JSON"
        return
    if response.status_code != 200:
        outcome.kind = "erreur"
        message = _meta_message(response)
        outcome.note = f"HTTP {response.status_code}" + (f" — {message}" if message else "")
        return
    if payload in (None, [], {}, ""):
        outcome.kind = "vide"
        return
    outcome.kind = "json"
    if keep_payload:
        outcome.payload = payload  # uniquement pour le PDL de la courbe horaire
    outcome.lines = shape_lines(payload)
    SENSITIVE_VALUES.update(_sensitive_for(payload))


SENSITIVE_VALUES: set[str] = set()


def _sensitive_for(payload: Any) -> set[str]:
    sink: set[str] = set()
    collect_sensitive(payload, "", sink)
    return sink


def _leak_check(report: str, sensitive: set[str]) -> list[str]:
    lowered = report.lower()
    return [value for value in sensitive if len(value) >= 3 and value.lower() in lowered]


def _render_report(
    started: str,
    login_lines: list[str],
    login_status: str,
    outcomes: list[Outcome],
    skipped: list[tuple[str, str, str]],
    request_count: int,
) -> str:
    ok = [o for o in outcomes if o.kind in ("json", "vide", "binaire")]
    failed = [o for o in outcomes if o.kind == "erreur"]
    useful = [o for o in outcomes if o.kind == "json"]
    lines: list[str] = []
    add = lines.append

    add("# Inventaire des données accessibles : espace client Ohm Énergie")
    add("")
    add(f"Généré le {started} par `discover.py` (lecture seule). Ce document ne contient que la forme des réponses.")
    add("")
    add("## Garde-fous appliqués")
    add("")
    add("- Une seule connexion (`POST /api/login`), sans nouvelle tentative.")
    add("- Uniquement des `GET` de lecture et le `POST` de lecture horaire (`{date, pdl}`), listés en allowlist.")
    add("- Pause d'au moins 1 s entre deux requêtes, 60 requêtes au maximum (connexion et rafraîchissement compris).")
    add("- Valeurs masquées : `<redacted:id>` pour les identifiants en clé, `<date>` pour les dates en clé. "
        "Les chaînes ne sont jamais reproduites ; seules les plages de dates et les minimum/maximum de kWh le sont.")
    add("- Aucune réponse brute n'est enregistrée sur disque.")
    add("")
    add("## Connexion")
    add("")
    add(login_status)
    add("")
    add("Forme de la réponse de connexion :")
    add("")
    lines.extend(login_lines)
    add("")
    add("## Résumé")
    add("")
    add(f"- Requêtes HTTP envoyées : {request_count} (dont connexion).")
    add(f"- Endpoints réussis : {len(ok)} (dont {len(useful)} avec des données JSON non vides).")
    add(f"- Endpoints en échec : {len(failed)}.")
    add(f"- Endpoints ignorés : {len(skipped)} (voir la section dédiée).")
    add("")
    add("### Informations récupérables (réponses JSON non vides)")
    add("")
    by_category: dict[str, list[str]] = {}
    for outcome in useful:
        by_category.setdefault(outcome.category, []).append(outcome.label)
    for category, labels in by_category.items():
        add(f"- **{category}** : {', '.join(labels)}")
    add("")
    add("## Détail par endpoint")
    add("")
    for outcome in outcomes:
        add(f"### {outcome.label}")
        add("")
        verb = f"`{outcome.method} {outcome.template}`"
        if outcome.kind == "json":
            add(f"{verb} : statut {outcome.status}, réponse JSON.")
            add("")
            lines.extend(outcome.lines)
        elif outcome.kind == "vide":
            add(f"{verb} : statut {outcome.status}, réponse vide.")
        elif outcome.kind == "binaire":
            add(f"{verb} : statut {outcome.status}, {outcome.note}.")
        else:
            add(f"{verb} : échec, {outcome.note or 'statut ' + str(outcome.status)}.")
        add("")
    add("## Échecs")
    add("")
    if failed:
        for outcome in failed:
            add(f"- `{outcome.method} {outcome.template}` : {outcome.note}")
    else:
        add("Aucun.")
    add("")
    add("## Endpoints ignorés et raisons")
    add("")
    add("| Méthode | Chemin | Raison |")
    add("|---|---|---|")
    for method, path, reason in skipped:
        add(f"| {method} | `{path}` | {reason} |")
    add("")
    return "\n".join(lines)


def main() -> int:
    started = date.today().isoformat()
    config = load_config()
    client = OhmClient(config)

    try:
        user = client.login()
    except OhmLoginError as exc:
        print(f"Connexion refusée : HTTP {exc.status_code} ; message : {exc.message or '(aucun)'}")
        print("Aucune nouvelle tentative. Inventaire non généré.")
        return 1
    except (OhmApiError, requests.RequestException) as exc:
        print(f"Connexion impossible : {type(exc).__name__} {exc if isinstance(exc, OhmApiError) else ''}".rstrip())
        return 1

    SENSITIVE_VALUES.update({config.login, config.password})
    SENSITIVE_VALUES.update(_sensitive_for(user))
    if config.customer_number:
        SENSITIVE_VALUES.add(config.customer_number)
    cookie = client._session.cookies.get("_token")
    if cookie:
        SENSITIVE_VALUES.add(cookie)
    if client.ct:
        SENSITIVE_VALUES.add(client.ct)

    login_status = (
        f"- Statut HTTP : 200, statut `meta` : 200.\n"
        f"- Cookie `_token` : {'présent' if cookie else 'absent'}.\n"
        f"- Contrat et numéro client : {'renseignés' if client.ct and client.customer_number else 'incomplets'} "
        "(valeurs non reproduites)."
    )
    login_payload_lines = shape_lines(
        {"success": True, "meta": {"status": 200, "message": ""}, "body": {"user": user}}
    )
    print(f"Connexion OK. Cookie _token {'présent' if cookie else 'absent'}.")

    pdl = _extract_pdl(user)
    outcomes: list[Outcome] = []
    kwh_payload: Any = None
    for endpoint in DUMP_ENDPOINTS:
        outcome = Outcome(endpoint.category, endpoint.description, endpoint.method, endpoint.template)
        try:
            path = endpoint.path(client.customer_number, client.ct)
        except EndpointError as exc:
            outcome.kind = "erreur"
            outcome.note = str(exc)
        else:
            keep_payload = endpoint.name == "consumption_kwh_data"
            _run(client, outcome, path, None, keep_payload=keep_payload)
            if keep_payload:
                kwh_payload = outcome.payload
        outcomes.append(outcome)
        print(f"[{client.request_count}] {endpoint.method} {endpoint.template} -> {outcome.status or outcome.kind}")

    pdl_data = _pdl_from_consumption_data(kwh_payload)
    print(
        "PDL pour la courbe horaire : "
        f"kwh/data={'oui' if pdl_data else 'non'}, login={'oui' if pdl else 'non'}"
    )
    pdl = pdl_data or pdl
    endpoint = HOURLY_ENDPOINT
    outcome = Outcome(endpoint.category, endpoint.description, endpoint.method, endpoint.template)
    if pdl is None:
        outcome.kind = "erreur"
        outcome.note = "non appelé : PDL absent (ni body.others.pdl, ni body.user.pdl)"
    else:
        try:
            path = endpoint.path(client.customer_number, client.ct)
        except EndpointError as exc:
            outcome.kind = "erreur"
            outcome.note = str(exc)
        else:
            _run(client, outcome, path, {"date": _yesterday(), "pdl": pdl})
    outcomes.append(outcome)
    print(f"[{client.request_count}] {endpoint.method} {endpoint.template} -> {outcome.status or outcome.kind}")
    if outcome.kind == "erreur":
        print(f"Diagnostic POST : statut={outcome.status}, detail={outcome.note}")

    report = _render_report(
        started,
        login_payload_lines,
        login_status,
        outcomes,
        list(EXCLUDED_ENDPOINTS),
        client.request_count,
    )
    leaks = _leak_check(report, SENSITIVE_VALUES)
    if leaks:
        print(f"ARRÊT : {len(leaks)} valeur(s) sensible(s) détectée(s) dans le rapport. Fichier non écrit.")
        for value in leaks:  # aucune valeur affichée : longueur et classes de caractères seulement
            kinds = [n for n, ok in (("chiffres", any(c.isdigit() for c in value)),
                                     ("lettres", any(c.isalpha() for c in value)),
                                     ("@", "@" in value)) if ok]
            print(f"  - longueur={len(value)} contient={'/'.join(kinds)}")
        return 2

    INVENTORY_PATH.parent.mkdir(exist_ok=True)
    INVENTORY_PATH.write_text(report, encoding="utf-8")
    print(f"Inventaire écrit : {INVENTORY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
