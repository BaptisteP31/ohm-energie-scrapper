"""Contrôle de fuite : détecte les vraies valeurs identifiantes, ignore le bruit.

Exécution :
    .venv/bin/python -I -m pytest tests/test_leak_check.py
ou, sans pytest :
    .venv/bin/python -I tests/test_leak_check.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from discover import _leak_check, _sensitive_for  # noqa: E402

SYNTHETIC_PAYLOAD = {
    "email": "synthetic-user@example.test",
    "pdl": "12345678901234",
    "_token": "synthetic-token-0123456789",
    "customer_nbr": "CM-123456789",
    "contract_nbr": "987654321",
    "contract_type": "elec",
    "year": "2026",
    "unit": "kWh",
}

SYNTHETIC_REPORT = (
    "synthetic-user@example.test 12345678901234 synthetic-token-0123456789 "
    "CM-123456789 987654321"
)


def test_identifiers_are_detected():
    sensitive = _sensitive_for(SYNTHETIC_PAYLOAD)
    leaks = _leak_check(SYNTHETIC_REPORT, sensitive)
    assert "synthetic-user@example.test" in leaks
    assert "12345678901234" in leaks
    assert "synthetic-token-0123456789" in leaks
    assert "CM-123456789" in leaks
    assert "987654321" in leaks


def test_harmless_short_values_are_ignored():
    sensitive = _sensitive_for(SYNTHETIC_PAYLOAD)
    assert "2026" not in sensitive
    assert "kWh" not in sensitive
    assert "elec" not in sensitive
    assert _leak_check("rapport de forme : 2026, kWh, elec", sensitive) == []


def test_short_values_under_sensitive_keys_are_ignored():
    sensitive = _sensitive_for({"contract_status": "ok", "pdl": "1234"})
    assert _leak_check("ok 1234", sensitive) == []


def test_sensitive_value_seen_in_report_blocks():
    sensitive = _sensitive_for({"contract_nbr": "AB1234"})
    assert _leak_check("contrat AB1234", sensitive) == ["AB1234"]


if __name__ == "__main__":
    test_identifiers_are_detected()
    test_harmless_short_values_are_ignored()
    test_short_values_under_sensitive_keys_are_ignored()
    test_sensitive_value_seen_in_report_blocks()
    print("4 tests OK")
