#!/usr/bin/env python3
"""Génère la collection Bruno à partir du contrat docs/openapi.yaml.

Une requête .bru par opération, plus une requête par variante (format, granularité,
période, regroupement) lorsque l'opération en expose plusieurs. Les dossiers suivent les
tags du contrat. La génération est déterministe : relancer le script ne modifie rien.

Usage :
    python scripts/gen_bruno.py            # génère et supprime les fichiers obsolètes
    python scripts/gen_bruno.py --check    # échoue si bruno/ diffère du contrat
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "docs" / "openapi.yaml"
BRUNO_DIR = REPO_ROOT / "bruno"

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

# Ordre des dossiers. Les requêtes qui capturent un identifiant (meters, contracts)
# passent avant celles qui en ont besoin.
FOLDERS = ("system", "meters", "contracts", "readings", "consumption", "billing", "legacy")

# Paramètres de chemin -> variables Bruno. `name` est le paramètre des routes legacy.
PATH_VARIABLES = {
    "meterId": "meterId",
    "contractId": "contractId",
    "invoiceId": "invoiceId",
    "name": "legacyName",
}

# Requêtes qui capturent le premier identifiant renvoyé dans une variable Bruno.
CAPTURES = {
    "listMeters": ("meterId", "res.body.items[0].id"),
    "listContracts": ("contractId", "res.body.items[0].contract_id"),
    "listContractInvoices": ("invoiceId", "res.body.items[0].invoice_id"),
}

# Valeurs de secours pour les paramètres de date sans exemple dans le contrat.
DATE_FALLBACK = {"from": "2026-10-18", "to": "2026-10-24"}


@dataclass(frozen=True)
class Variant:
    """Requête dérivée d'une opération : valeurs de paramètres ou type de média attendu."""

    suffix: str
    label: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    media: str = "application/json"


VARIANTS: dict[str, list[Variant]] = {
    "listMeterReadings": [
        Variant("json", "JSON", headers={"Accept": "application/json"}, media="application/json"),
        Variant("csv", "CSV", headers={"Accept": "text/csv"}, media="text/csv"),
    ],
    "getMeterConsumption": [
        Variant(g, f"granularité {g}", query={"granularity": g})
        for g in ("hour", "day", "week", "month")
    ],
    "getMeterConsumptionSummary": [
        Variant(p.replace("-", "_"), f"période {p}", query={"period": p})
        for p in ("yesterday", "last-7-days", "last-30-days", "last-month")
    ],
    "getMeterConsumptionComparison": [
        Variant(p, f"période {p}", query={"period": p}) for p in ("week", "month")
    ],
    "getMeterConsumptionProfile": [
        Variant(b.replace("-", "_"), f"par {b}", query={"by": b})
        for b in ("hour-of-day", "day-of-week")
    ],
    "getLegacyConsumption": [
        Variant(
            f"{g.replace('-', '_')}_{f}",
            f"granularité {g}, format {f.upper()}",
            query={"granularity": g, "format": f},
            media="text/csv" if f == "csv" else "application/json",
        )
        for g in ("hourly", "daily", "power-days", "power-months")
        for f in ("json", "csv")
    ],
}


# ---------------------------------------------------------------------------
# Lecture du contrat
# ---------------------------------------------------------------------------


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError(f"contrat invalide : {path}")
    return document


def resolve(spec: dict[str, Any], node: Any) -> Any:
    """Suit les `$ref` locales (#/...) jusqu'au nœud final."""
    while isinstance(node, dict) and "$ref" in node:
        target: Any = spec
        for token in node["$ref"][2:].split("/"):
            target = target[token.replace("~1", "/").replace("~0", "~")]
        node = target
    return node


def iter_operations(spec: dict[str, Any]):
    """Retourne (chemin, méthode, opération, paramètres de niveau chemin), dans l'ordre du contrat."""
    for path, item in spec.get("paths", {}).items():
        for key, operation in item.items():
            if key in HTTP_METHODS:
                yield path, key, operation, item.get("parameters", [])


# ---------------------------------------------------------------------------
# Rendu .bru
# ---------------------------------------------------------------------------


def scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return repr(value)
    return str(value)


def indent_docs(text: str) -> str:
    return "\n".join(f"  {line}" if line.strip() else "" for line in text.strip().splitlines())


def render_request(
    *,
    name: str,
    seq: int,
    method: str,
    url: str,
    auth: bool,
    headers: dict[str, str],
    query: dict[str, str],
    post_vars: list[tuple[str, str]],
    asserts: list[str],
    docs: str,
) -> str:
    blocks: list[str] = [
        f"meta {{\n  name: {name}\n  type: http\n  seq: {seq}\n}}",
        (
            f"{method} {{\n  url: {url}\n  body: none\n"
            f"  auth: {'bearer' if auth else 'none'}\n}}"
        ),
    ]
    if headers:
        body = "\n".join(f"  {k}: {v}" for k, v in headers.items())
        blocks.append(f"headers {{\n{body}\n}}")
    if query:
        body = "\n".join(f"  {k}: {v}" for k, v in query.items())
        blocks.append(f"params:query {{\n{body}\n}}")
    if auth:
        blocks.append("auth:bearer {\n  token: {{token}}\n}")
    if post_vars:
        body = "\n".join(f"  {k}: {v}" for k, v in post_vars)
        blocks.append(f"vars:post-response {{\n{body}\n}}")
    body = "\n".join(f"  {line}" for line in asserts)
    blocks.append(f"assert {{\n{body}\n}}")
    blocks.append(f"docs {{\n{indent_docs(docs)}\n}}")
    return "\n\n".join(blocks) + "\n"


def render_folder(name: str, seq: int) -> str:
    return f"meta {{\n  name: {name}\n  seq: {seq}\n}}\n"


def render_environment(values: dict[str, str]) -> str:
    lines = "\n".join(f"  {k}: {v}" for k, v in values.items())
    return f"vars {{\n{lines}\n}}\nvars:secret [\n  token\n]\n"


# ---------------------------------------------------------------------------
# Construction de la collection
# ---------------------------------------------------------------------------


def _query_value(param: dict[str, Any], overrides: dict[str, str]) -> str | None:
    """Valeur d'un paramètre de requête, ou None pour l'omettre (paramètre optionnel sans valeur)."""
    schema = param.get("schema", {})
    name = param["name"]
    if name in overrides:
        return overrides[name]
    if "example" in param:
        return scalar(param["example"])
    if "example" in schema:
        return scalar(schema["example"])
    if "default" in schema:
        return scalar(schema["default"])
    if schema.get("format") == "date" and name in DATE_FALLBACK:
        return DATE_FALLBACK[name]
    enum = schema.get("enum", [])
    if param.get("required") and len(enum) == 1:
        return scalar(enum[0])
    if param.get("required"):
        raise ValueError(f"paramètre requis sans valeur d'exemple : {name}")
    return None


def _assertions(spec: dict[str, Any], response: dict[str, Any], media: str) -> list[str]:
    lines = ["res.status: eq 200"]
    if media == "text/csv":
        lines.append("res.body: isString")
        return lines
    content = response.get("content", {}).get(media)
    if not content:
        return lines
    schema = resolve(spec, content.get("schema", {}))
    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        lines.append(f"res.body.{name}: isDefined")
        if resolve(spec, properties.get(name, {})).get("type") == "array":
            lines.append(f"res.body.{name}: isArray")
    return lines


def _url(path: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return "{{" + PATH_VARIABLES[match.group(1)] + "}}"

    return "{{host}}:{{port}}" + re.sub(r"\{(\w+)\}", repl, path)


def _folder_files(spec: dict[str, Any]) -> dict[str, list[tuple[tuple[int, int], str, str]]]:
    """Retourne, par dossier, les (clé de tri, nom de fichier, contenu) des requêtes."""
    collected: dict[str, list[tuple[tuple[int, int], str, str]]] = {tag: [] for tag in FOLDERS}
    for index, (path, method, op, path_params) in enumerate(iter_operations(spec)):
        op_id = op["operationId"]
        tag = op["tags"][0]
        if tag not in collected:
            raise ValueError(f"tag non prévu par le générateur : {tag}")
        if method != "get":
            raise ValueError(f"méthode non GET dans le contrat : {method.upper()} {path}")

        parameters = [resolve(spec, p) for p in path_params + op.get("parameters", [])]
        query_params = [p for p in parameters if p["in"] == "query"]
        response = resolve(spec, op["responses"]["200"])
        auth = bool(op.get("security", spec.get("security", [])))
        capture = CAPTURES.get(op_id)
        sort_key = (0 if capture else 1, index)
        summary = op.get("summary", op_id)

        variants = VARIANTS.get(op_id, [None])
        for variant in variants:
            overrides = dict(variant.query) if variant else {}
            for key, value in overrides.items():
                enum = next((p["schema"]["enum"] for p in query_params if p["name"] == key), None)
                if enum is None or value not in enum:
                    raise ValueError(f"variante hors contrat : {op_id} {key}={value}")

            query: dict[str, str] = {}
            for param in query_params:
                value = _query_value(param, overrides)
                if value is not None:
                    query[param["name"]] = value

            media = variant.media if variant else "application/json"
            headers = dict(variant.headers) if variant else {}
            name = op_id
            filename = op_id
            docs = op["description"]
            if variant:
                name = f"{op_id} ({variant.label})"
                filename = f"{op_id}_{variant.suffix}"
                docs = f"{docs.strip()}\n\nVariante : {variant.label}."

            post_vars = [(capture[0], capture[1])] if capture else []
            text = render_request(
                name=f"{name} - {summary}",
                seq=0,  # renseigné après tri
                method=method,
                url=_url(path),
                auth=auth,
                headers=headers,
                query=query,
                post_vars=post_vars,
                asserts=_assertions(spec, response, media),
                docs=docs,
            )
            collected[tag].append((sort_key, filename, text))
    return collected


def build_collection(spec: dict[str, Any]) -> dict[str, str]:
    """Retourne les fichiers attendus, indexés par chemin relatif à bruno/ (séparateur /)."""
    files: dict[str, str] = {}
    files["bruno.json"] = (
        json.dumps(
            {
                "version": "1",
                "name": "Ohm Scraper",
                "type": "collection",
                "ignore": ["node_modules", ".git"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    env_values = {"host": "http://127.0.0.1", "port": "8080"}
    for param in _all_path_parameters(spec):
        var = PATH_VARIABLES.get(param["name"])
        if var:
            env_values[var] = scalar(param["schema"]["example"])
    files["environments/local.bru"] = render_environment(env_values)

    collected = _folder_files(spec)
    for folder_seq, folder in enumerate(FOLDERS, start=1):
        files[f"{folder}/folder.bru"] = render_folder(folder, folder_seq)
        entries = sorted(collected[folder], key=lambda entry: (entry[0], entry[1]))
        for seq, (_, filename, text) in enumerate(entries, start=1):
            text = text.replace("seq: 0\n", f"seq: {seq}\n", 1)
            files[f"{folder}/{filename}.bru"] = text
    return files


def _all_path_parameters(spec: dict[str, Any]):
    seen: set[str] = set()
    for _, _, _, path_params in iter_operations(spec):
        for raw in path_params:
            param = resolve(spec, raw)
            if param["in"] == "path" and param["name"] not in seen:
                seen.add(param["name"])
                yield param
    for _, _, op, _ in iter_operations(spec):
        for raw in op.get("parameters", []):
            param = resolve(spec, raw)
            if param["in"] == "path" and param["name"] not in seen:
                seen.add(param["name"])
                yield param


# ---------------------------------------------------------------------------
# Écriture, comparaison
# ---------------------------------------------------------------------------


def _managed_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.bru") if p.is_file())


def diff_collection(root: Path, files: dict[str, str]) -> list[str]:
    """Liste les écarts entre le dossier `root` et les fichiers attendus."""
    problems: list[str] = []
    for rel, content in files.items():
        target = root / rel
        if not target.exists():
            problems.append(f"fichier manquant : {rel}")
        elif target.read_text(encoding="utf-8") != content:
            problems.append(f"contenu désynchronisé : {rel}")
    for path in _managed_files(root):
        rel = path.relative_to(root).as_posix()
        if rel not in files:
            problems.append(f"fichier obsolète : {rel}")
    return problems


def write_collection(root: Path, files: dict[str, str]) -> tuple[int, int, int]:
    """Écrit les fichiers attendus, supprime les .bru obsolètes. Retourne (créés, mis à jour, supprimés)."""
    created = updated = deleted = 0
    for rel, content in files.items():
        target = root / rel
        if target.exists():
            if target.read_text(encoding="utf-8") != content:
                target.write_text(content, encoding="utf-8")
                updated += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            created += 1
    for path in _managed_files(root):
        if path.relative_to(root).as_posix() not in files:
            path.unlink()
            deleted += 1
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    return created, updated, deleted


def generate(root: Path = BRUNO_DIR, spec_path: Path = SPEC_PATH) -> int:
    files = build_collection(load_spec(spec_path))
    created, updated, deleted = write_collection(root, files)
    print(
        f"Collection Bruno générée depuis {spec_path.name} : {len(files)} fichiers "
        f"({created} créés, {updated} mis à jour, {deleted} supprimés)."
    )
    return 0


def check(root: Path = BRUNO_DIR, spec_path: Path = SPEC_PATH) -> int:
    problems = diff_collection(root, build_collection(load_spec(spec_path)))
    if problems:
        for problem in problems:
            print(f"ERREUR : {problem}", file=sys.stderr)
        return 1
    print("Collection Bruno à jour et synchronisée avec le contrat.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Génère la collection Bruno depuis docs/openapi.yaml")
    parser.add_argument("--check", action="store_true", help="vérifie la synchronisation sans écrire")
    args = parser.parse_args()
    return check() if args.check else generate()


if __name__ == "__main__":
    sys.exit(main())
