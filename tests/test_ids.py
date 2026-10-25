"""Identifiants opaques : dérivation et format (données synthétiques)."""

from __future__ import annotations

import hashlib

import pytest

from ohm_scraper.ids import is_opaque_id, opaque_id


def test_opaque_id_is_twelve_first_hex_chars_of_sha256() -> None:
    value = "00000000000000"
    expected = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    assert opaque_id(value) == expected
    assert is_opaque_id(expected)


def test_opaque_id_is_deterministic_and_distinct() -> None:
    assert opaque_id("CT-SYNTH-0001") == opaque_id("CT-SYNTH-0001")
    assert opaque_id("CT-SYNTH-0001") != opaque_id("CT-SYNTH-0002")


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("3f9a1c0b7e2d", True),
        ("3F9A1C0B7E2D", False),
        ("3f9a1c0b7e2", False),
        ("3f9a1c0b7e2d0", False),
        ("3f9a1c0b7e2g", False),
        ("3f9a1c0b7e2d\n", False),
        ("", False),
    ],
)
def test_is_opaque_id_requires_exactly_twelve_lowercase_hex(value: str, valid: bool) -> None:
    assert is_opaque_id(value) is valid
