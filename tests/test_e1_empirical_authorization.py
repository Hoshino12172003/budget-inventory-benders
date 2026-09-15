from __future__ import annotations

import json
from pathlib import Path

import pytest

import experiments.run_e1_empirical_local as runner


ROOT = Path(__file__).resolve().parents[1]


def _clean_git(*args, **kwargs) -> bytes:
    return b""


def test_exact_sixteen_run_authorization_and_exclusions() -> None:
    manifest = json.loads(runner.AUTHORIZATION.read_text(encoding="utf-8"))
    assert manifest["formal_run_authorized"] is True
    assert len(manifest["authorized_run_ids"]) == 16
    assert len(set(manifest["authorized_run_ids"])) == 16
    assert manifest["synthetic_execution_authorized"] is False
    assert manifest["e2_e7_authorization"] is False
    assert "experiments/results/e1_empirical_8case_v1/" in (
        ROOT / ".gitignore"
    ).read_text(encoding="utf-8")


def test_runner_accepts_one_frozen_run_without_solving(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner.subprocess, "check_output", _clean_git)
    manifest, identity = runner.validate_execution_gate("210202", "direct", tmp_path)
    assert manifest["formal_run_authorized"] is True
    assert identity["case"] == "210202"


def test_runner_blocks_wrong_identity_hash(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner.subprocess, "check_output", _clean_git)
    original = runner._identity("210202")
    monkeypatch.setattr(runner, "_identity", lambda case_id: {**original, "instance_hash": "wrong"})
    with pytest.raises(RuntimeError, match="instance_hash mismatch"):
        runner.validate_execution_gate("210202", "direct", tmp_path)


def test_runner_blocks_existing_output(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner.subprocess, "check_output", _clean_git)
    (tmp_path / "E1-210202-DIRECT").mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner.validate_execution_gate("210202", "direct", tmp_path)


def test_pair_comparison_passes_and_blocks_mismatch(tmp_path) -> None:
    for method, objective in (("DIRECT", 10.0), ("PRB", 10.00001)):
        path = tmp_path / f"E1-210202-{method}" / "result.json"
        runner._write_json(path, {
            "status": "OPTIMAL",
            "exact_certification_status": "CERTIFIED_EXACT",
            "objective": objective,
        })
    runner._compare_completed_pair(tmp_path, "210202", 1e-4)
    audit = json.loads((tmp_path / "E1-210202-PAIR-COMPARISON.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"

    prb = tmp_path / "E1-210202-PRB" / "result.json"
    runner._write_json(prb, {
        "status": "OPTIMAL",
        "exact_certification_status": "CERTIFIED_PRB_EXACT",
        "objective": 10.01,
    })
    with pytest.raises(RuntimeError, match="E1_BLOCKED_CORRECTNESS_210202"):
        runner._compare_completed_pair(tmp_path, "210202", 1e-4)
