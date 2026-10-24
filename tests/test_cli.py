"""CLI hors ligne : --list sans réseau, dump et consumption avec un faux client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ohm_scraper import cli
from ohm_scraper.endpoints import DUMP_ENDPOINTS
from tests.fakes import FakeClient

KWH_DATA = {"success": True, "body": {"others": {"pdl": "12345678901234"}}}
HOURLY = {
    "success": True,
    "body": {
        "consumptions": {
            "data": [500],
            "dataString": ["0,5"],
            "time": ["00:00"],
            "heuresCreuseColors": ["bleu"],
        }
    },
}


def test_dump_list_needs_no_network_and_no_env(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def forbidden() -> None:
        raise AssertionError("_connect ne doit pas être appelé pour --list")

    monkeypatch.setattr(cli, "_connect", forbidden)

    assert cli.main(["dump", "--list"]) == 0
    output = capsys.readouterr().out
    assert "consumption_six_months" in output
    assert "invoices" in output
    assert "balance" in output


def test_dump_writes_one_file_per_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(get_payload={"success": True, "body": []})
    monkeypatch.setattr(cli, "_connect", lambda: client)

    assert cli.main(["dump", "--output-dir", str(tmp_path)]) == 0

    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == len(DUMP_ENDPOINTS)
    payload = json.loads((tmp_path / "invoices.json").read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert len(client.calls) == len(DUMP_ENDPOINTS)
    assert all(method == "GET" for method, _, _ in client.calls)


def test_dump_only_and_unknown_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeClient()
    monkeypatch.setattr(cli, "_connect", lambda: client)

    assert cli.main(["dump", "--only", "balance,preferences", "--output-dir", str(tmp_path)]) == 0
    assert sorted(path.stem for path in tmp_path.glob("*.json")) == ["balance", "preferences"]

    assert cli.main(["dump", "--only", "nope", "--output-dir", str(tmp_path)]) == 2
    assert "endpoint inconnu" in capsys.readouterr().err


def test_dump_reports_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "_connect", lambda: FakeClient(fail=True))
    assert cli.main(["dump", "--only", "balance", "--output-dir", str(tmp_path)]) == 1
    assert list(tmp_path.glob("*.json")) == []


def test_consumption_hourly_writes_csv_without_leaking_pdl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = FakeClient(get_payload=KWH_DATA, post_payload=HOURLY)
    monkeypatch.setattr(cli, "_connect", lambda: client)
    output = tmp_path / "hourly.csv"

    code = cli.main(
        [
            "consumption",
            "--granularity",
            "hourly",
            "--from",
            "23/10/2026",
            "--to",
            "23/10/2026",
            "--format",
            "csv",
            "--output",
            str(output),
        ]
    )

    assert code == 0
    text = output.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "date,time,wh,kwh,kwh_text,color"
    assert "2026-10-23,00:00,500,0.5" in text
    assert "12345678901234" not in text
    posts = [call for call in client.calls if call[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][2]["date"] == "23/10/2026"
    assert posts[0][2]["pdl"] == "12345678901234"


def test_consumption_power_days_uses_one_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(post_payload={"body": {"labels": ["a", "b"], "data": [1, 2]}})
    monkeypatch.setattr(cli, "_connect", lambda: client)
    output = tmp_path / "daily.json"

    code = cli.main(
        [
            "consumption",
            "--granularity",
            "power-days",
            "--from",
            "01/10/2026",
            "--to",
            "03/10/2026",
            "--output",
            str(output),
        ]
    )

    assert code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["granularity"] == "power-days"
    assert document["from"] == "2026-10-01"
    assert document["to"] == "2026-10-03"
    assert document["rows"] == [{"labels": "a", "data": 1}, {"labels": "b", "data": 2}]
    assert len([call for call in client.calls if call[0] == "POST"]) == 1


def test_consumption_hourly_cap_is_enforced_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        raise AssertionError("_connect ne doit pas être appelé quand la plage est invalide")

    monkeypatch.setattr(cli, "_connect", forbidden)

    code = cli.main(
        ["consumption", "--granularity", "hourly", "--from", "01/09/2026", "--to", "31/10/2026"]
    )
    assert code == 2


def test_consumption_stops_when_pdl_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(get_payload={"body": {"others": {}}})
    monkeypatch.setattr(cli, "_connect", lambda: client)
    output = tmp_path / "none.csv"

    code = cli.main(
        [
            "consumption",
            "--granularity",
            "hourly",
            "--from",
            "23/10/2026",
            "--to",
            "23/10/2026",
            "--format",
            "csv",
            "--output",
            str(output),
        ]
    )

    assert code == 1
    assert not output.exists()
    assert not [call for call in client.calls if call[0] == "POST"]
