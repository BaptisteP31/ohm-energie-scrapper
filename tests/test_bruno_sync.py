"""Synchronisation de la collection Bruno avec le contrat docs/openapi.yaml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from scripts import gen_bruno

REPO_ROOT = Path(__file__).resolve().parents[1]
BRUNO_DIR = REPO_ROOT / "bruno"


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return gen_bruno.load_spec()


@pytest.fixture(scope="module")
def expected() -> dict[str, str]:
    return gen_bruno.build_collection(gen_bruno.load_spec())


def _request_files() -> list[Path]:
    return sorted(p for p in BRUNO_DIR.rglob("*.bru") if p.name != "folder.bru" and p.parent != BRUNO_DIR / "environments")


def test_bruno_collection_matches_contract(expected: dict[str, str]) -> None:
    """Chaque fichier attendu existe avec le bon contenu, sans fichier obsolète."""
    problems = gen_bruno.diff_collection(BRUNO_DIR, expected)
    assert not problems, "collection Bruno désynchronisée (lancer python scripts/gen_bruno.py) : " + ", ".join(problems)


def test_every_operation_has_a_request_file(spec: dict[str, Any]) -> None:
    filenames = [p.stem for p in _request_files()]
    for _, _, operation, _ in gen_bruno.iter_operations(spec):
        op_id = operation["operationId"]
        matches = [name for name in filenames if name == op_id or name.startswith(f"{op_id}_")]
        assert matches, f"aucune requête Bruno pour {op_id}"


def test_request_files_are_get_and_authenticated_except_health(expected: dict[str, str]) -> None:
    for rel, content in expected.items():
        if not rel.endswith(".bru") or rel.endswith("folder.bru") or rel.startswith("environments/"):
            continue
        assert re.search(r"^get \{$", content, re.MULTILINE), f"méthode GET attendue : {rel}"
        assert "assert {" in content and "res.status: eq 200" in content, f"assertion de statut manquante : {rel}"
        assert "docs {" in content, f"documentation manquante : {rel}"
        if rel == "system/getHealth.bru":
            assert "auth: none" in content
        else:
            assert "auth: bearer" in content and "token: {{token}}" in content, f"auth manquante : {rel}"


def test_seq_is_unique_per_folder_and_captures_run_first(expected: dict[str, str]) -> None:
    by_folder: dict[str, list[tuple[int, str]]] = {}
    for rel, content in expected.items():
        if not rel.endswith(".bru") or rel.endswith("folder.bru") or rel.startswith("environments/"):
            continue
        folder = rel.split("/")[0]
        seq = int(re.search(r"^  seq: (\d+)$", content, re.MULTILINE).group(1))  # type: ignore[union-attr]
        by_folder.setdefault(folder, []).append((seq, rel))
    for folder, entries in by_folder.items():
        seqs = [seq for seq, _ in entries]
        assert len(seqs) == len(set(seqs)), f"seq en double dans {folder}"
    capture_files = {"meters/listMeters.bru", "contracts/listContracts.bru"}
    for rel in capture_files:
        seq = next(s for s, r in by_folder[rel.split("/")[0]] if r == rel)
        assert seq == 1, f"la requête de capture doit être en tête de dossier : {rel}"
        assert "vars:post-response {" in expected[rel]


def test_generation_is_idempotent(tmp_path: Path, expected: dict[str, str]) -> None:
    gen_bruno.write_collection(tmp_path, expected)
    assert gen_bruno.write_collection(tmp_path, expected) == (0, 0, 0)
    assert gen_bruno.diff_collection(tmp_path, expected) == []


def test_stale_request_files_are_deleted(tmp_path: Path, expected: dict[str, str]) -> None:
    gen_bruno.write_collection(tmp_path, expected)
    stale = tmp_path / "data" / "old_endpoint.bru"
    stale.parent.mkdir()
    stale.write_text("meta {\n  name: ancien\n}\n", encoding="utf-8")

    assert gen_bruno.diff_collection(tmp_path, expected) == ["fichier obsolète : data/old_endpoint.bru"]
    assert gen_bruno.write_collection(tmp_path, expected) == (0, 0, 1)
    assert not stale.exists()
    assert not stale.parent.exists()
    assert gen_bruno.diff_collection(tmp_path, expected) == []
