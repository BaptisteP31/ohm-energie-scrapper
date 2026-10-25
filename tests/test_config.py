"""Tests de configuration pour les nouvelles clés du service HTTP."""

from __future__ import annotations

from pathlib import Path
import pytest
from ohm_scraper import config


def test_config_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OHM_LOGIN=test@example.com\nOHM_PASSWORD=secret\n", encoding="utf-8")

    for key in (
        "SERVICE_HOST",
        "SERVICE_PORT",
        "OHM_PUBLISH_ADDRESS",
        "OHM_API_TOKEN",
        "OHM_CACHE_TTL",
        "OHM_CUSTOMER_NUMBER",
        "OHM_CT",
    ):
        monkeypatch.delenv(key, raising=False)

    cfg = config.load_config(env_file=env_file)
    assert cfg.login == "test@example.com"
    assert cfg.password == "secret"
    assert cfg.service_host == "127.0.0.1"
    assert cfg.service_port == 8080
    assert cfg.publish_address == "127.0.0.1"
    assert cfg.api_token is None
    assert cfg.cache_ttl == 900


def test_config_custom_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_text = "\n".join([
        "OHM_LOGIN=test@example.com",
        "OHM_PASSWORD=secret",
        "SERVICE_HOST=0.0.0.0",
        "SERVICE_PORT=9090",
        "OHM_PUBLISH_ADDRESS=192.168.1.10",
        "OHM_API_TOKEN=supersecrettoken123",
        "OHM_CACHE_TTL=1800",
    ]) + "\n"
    env_file.write_text(env_text, encoding="utf-8")

    for key in (
        "SERVICE_HOST",
        "SERVICE_PORT",
        "OHM_PUBLISH_ADDRESS",
        "OHM_API_TOKEN",
        "OHM_CACHE_TTL",
    ):
        monkeypatch.delenv(key, raising=False)

    cfg = config.load_config(env_file=env_file)
    assert cfg.service_host == "0.0.0.0"
    assert cfg.service_port == 9090
    assert cfg.publish_address == "192.168.1.10"
    assert cfg.api_token == "supersecrettoken123"
    assert cfg.cache_ttl == 1800


def test_config_invalid_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OHM_LOGIN=test@example.com\nOHM_PASSWORD=secret\nSERVICE_PORT=invalid\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SERVICE_PORT", raising=False)
    with pytest.raises(ValueError, match="SERVICE_PORT doit être un entier"):
        config.load_config(env_file=env_file)
