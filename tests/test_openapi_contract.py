"""Contrat OpenAPI : structure, identifiants uniques, références résolues, lecture seule."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

SPEC_PATH = Path(__file__).resolve().parent.parent / "docs" / "openapi.yaml"
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    with SPEC_PATH.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    assert isinstance(document, dict), "docs/openapi.yaml doit contenir un objet YAML"
    return document


def iter_operations(spec: dict[str, Any]):
    """Retourne (chemin, méthode, opération) pour chaque clé de méthode HTTP."""
    for path, item in spec.get("paths", {}).items():
        for key, operation in item.items():
            if key.startswith("x-") or key == "parameters":
                continue
            yield path, key, operation


def is_legacy(operation: dict[str, Any]) -> bool:
    return "legacy" in operation.get("tags", [])


def resolve_ref(spec: dict[str, Any], ref: str) -> Any:
    """Résout une référence JSON Pointer locale (#/...)."""
    node: Any = spec
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            raise KeyError(ref)
        node = node[token]
    return node


def iter_refs(node: Any):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_refs(item)


def test_spec_file_exists() -> None:
    assert SPEC_PATH.is_file(), f"fichier manquant : {SPEC_PATH}"


def test_openapi_version_is_3_1(spec: dict[str, Any]) -> None:
    assert str(spec.get("openapi", "")).startswith("3.1"), "la version doit commencer par 3.1"


def test_every_operation_has_id_tags_and_responses(spec: dict[str, Any]) -> None:
    operations = list(iter_operations(spec))
    assert operations, "aucune opération déclarée"
    for path, method, operation in operations:
        where = f"{method.upper()} {path}"
        assert operation.get("operationId"), f"operationId manquant : {where}"
        tags = operation.get("tags")
        assert isinstance(tags, list) and len(tags) == 1, f"exactement un tag attendu : {where}"
        assert operation.get("responses"), f"responses manquant : {where}"


def test_operation_ids_are_unique(spec: dict[str, Any]) -> None:
    ids = [operation["operationId"] for _, _, operation in iter_operations(spec)]
    duplicates = sorted({op_id for op_id in ids if ids.count(op_id) > 1})
    assert not duplicates, f"operationId en double : {duplicates}"


def test_every_ref_resolves(spec: dict[str, Any]) -> None:
    unresolved = []
    for ref in iter_refs(spec):
        if not ref.startswith("#/"):
            unresolved.append(ref)
            continue
        try:
            resolve_ref(spec, ref)
        except KeyError:
            unresolved.append(ref)
    assert not unresolved, f"références non résolues : {sorted(set(unresolved))}"


def test_non_legacy_paths_are_under_v1(spec: dict[str, Any]) -> None:
    offenders = []
    for path, _, operation in iter_operations(spec):
        if is_legacy(operation) or path == "/health":
            continue
        if not path.startswith("/v1/"):
            offenders.append(path)
    assert not offenders, f"chemins hors /v1 : {sorted(set(offenders))}"


def test_health_is_the_only_unversioned_non_legacy_route(spec: dict[str, Any]) -> None:
    health_paths = {path for path, _, operation in iter_operations(spec) if path == "/health"}
    assert health_paths == {"/health"}


def test_only_get_methods_exist(spec: dict[str, Any]) -> None:
    for path, item in spec.get("paths", {}).items():
        for key in item:
            if key.lower() in HTTP_METHODS:
                assert key == "get", f"méthode non GET exposée : {key.upper()} {path}"


def test_legacy_operations_are_deprecated(spec: dict[str, Any]) -> None:
    legacy = [(p, m, o) for p, m, o in iter_operations(spec) if is_legacy(o)]
    assert legacy, "les routes legacy doivent être déclarées"
    for path, method, operation in legacy:
        assert operation.get("deprecated") is True, f"route legacy non dépréciée : {path}"


def test_tags_used_are_declared(spec: dict[str, Any]) -> None:
    declared = {tag["name"] for tag in spec.get("tags", [])}
    used = {tag for _, _, operation in iter_operations(spec) for tag in operation["tags"]}
    assert used <= declared, f"tags non déclarés : {sorted(used - declared)}"
