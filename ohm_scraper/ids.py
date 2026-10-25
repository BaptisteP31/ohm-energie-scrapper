"""Identifiants opaques de l'API v1.

``meterId`` et ``contractId`` sont les 12 premiers caractères hexadécimaux du
SHA-256 du PDL ou du numéro de contrat. Le PDL et le numéro de contrat ne
sortent jamais dans une URL.
"""

from __future__ import annotations

import hashlib
import re

OPAQUE_ID_RE = re.compile(r"[0-9a-f]{12}")


def opaque_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def is_opaque_id(value: str) -> bool:
    return OPAQUE_ID_RE.fullmatch(value) is not None
