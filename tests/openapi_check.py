"""Vérificateur minimal des réponses contre les schémas de docs/openapi.yaml.

Sans dépendance : type, required, properties, items, enum, const, pattern,
minimum, maximum, additionalProperties: false, formats date et date-time,
et références locales (#/...). Les autres mots-clés sont ignorés.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

SPEC_PATH = Path(__file__).resolve().parent.parent / "docs" / "openapi.yaml"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_spec() -> dict[str, Any]:
    with SPEC_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    while isinstance(schema, dict) and "$ref" in schema:
        node: Any = spec
        for token in schema["$ref"][2:].split("/"):
            node = node[token.replace("~1", "/").replace("~0", "~")]
        schema = node
    return schema


def _is_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _is_format(value: str, fmt: str) -> bool:
    if fmt == "date":
        if not DATE_RE.match(value):
            return False
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return True
    if fmt == "date-time":
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return False
        return True
    return True


def validate(spec: dict[str, Any], schema: dict[str, Any], value: Any, where: str = "$") -> list[str]:
    schema = resolve(spec, schema)
    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{where}: attendu {schema['const']!r}, reçu {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: valeur {value!r} hors enum {schema['enum']}")
    declared = schema.get("type")
    if declared is not None:
        allowed = declared if isinstance(declared, list) else [declared]
        if not any(_is_type(value, kind) for kind in allowed):
            errors.append(f"{where}: type {allowed} attendu, reçu {type(value).__name__}")
            return errors
    if value is None:
        return errors
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: propriété requise absente : {key}")
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in value:
                errors.extend(validate(spec, subschema, value[key], f"{where}.{key}"))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{where}: propriété inattendue : {key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors.extend(validate(spec, schema["items"], item, f"{where}[{index}]"))
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{where}: ne respecte pas le motif {schema['pattern']}")
        if "format" in schema and not _is_format(value, schema["format"]):
            errors.append(f"{where}: format {schema['format']} invalide : {value!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{where}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{where}: {value} > maximum {schema['maximum']}")
    return errors


def operation_schema(spec: dict[str, Any], path: str, status: str) -> dict[str, Any] | None:
    """Schéma JSON de la réponse ``status`` d'une opération (None si absent)."""
    operation = spec["paths"][path]["get"]
    response = resolve(spec, operation["responses"][status])
    content = response.get("content", {})
    media = content.get("application/json") or content.get("application/problem+json")
    return media["schema"] if media else None
