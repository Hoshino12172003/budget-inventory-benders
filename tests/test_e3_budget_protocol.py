from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

import experiments.run_e3_budget_local as runner


ROOT = Path(__file__).resolve().parents[1]


def manifest() -> dict:
    return json.loads(runner.MANIFEST.read_text(encoding="utf-8"))


def test_beta_parser_budget_and_run_ids() -> None:
    assert runner.parse_beta("0.80") == Decimal("0.80")
    with pytest.raises(ValueError):
        runner.parse_beta("0.85")
    budget, exact = runner.calculate_budget(Decimal("0.80"), 106510.9559990062)
    assert exact == "85208.764799204960"
    assert budget == 85208.76479920496
    assert runner.make_run_id("210202", Decimal("0.80")) == "E3-210202-B080"


def test_manifest_has_exact_design_and_starts_fail_closed() -> None:
    value = manifest()
    runner.validate_manifest(value)
    assert value["authorization_transition"][0] is False
    assert value["authorization_transition"][-1] is value["formal_run_authorized"]
    assert len(value["authorized_run_ids"]) == len(set(value["authorized_run_ids"])) == 40


def test_manifest_rejects_wrong_gamma_and_lambda() -> None:
    for key, invalid in (("Gamma", 1), ("lambda_R", 0.1)):
        value = manifest()
        value[key] = invalid
        with pytest.raises(RuntimeError):
            runner.validate_manifest(value)


def test_unauthorized_execution_is_blocked(monkeypatch) -> None:
    value = manifest()
    value["formal_run_authorized"] = False
    value["authorization_transition"] = [False]
    monkeypatch.setattr(runner, "load_manifest", lambda: value)
    with pytest.raises(PermissionError, match="E3_FORMAL_RUN_NOT_AUTHORIZED"):
        runner.validate_gate("210202", Decimal("0.80"))


def test_clean_worktree_gate_and_overwrite(monkeypatch, tmp_path) -> None:
    value = manifest()
    value["formal_run_authorized"] = True
    value["authorization_transition"] = [False, True]
    monkeypatch.setattr(runner, "load_manifest", lambda: value)
    monkeypatch.setattr(runner, "source_model_identity", lambda revision=None: value["model_identity_sha256"])
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *args, **kwargs: b"dirty")
    with pytest.raises(RuntimeError, match="clean committed worktree"):
        runner.validate_gate("210202", Decimal("0.80"), tmp_path)

    monkeypatch.setattr(runner.subprocess, "check_output", lambda *args, **kwargs: b"")
    (tmp_path / "E3-210202-B080").mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner.validate_gate("210202", Decimal("0.80"), tmp_path)


def test_case_identity_rejects_wrong_instance_and_x0_hash() -> None:
    value = manifest()
    identity = runner.load_identities()["210202"]
    for key in ("instance_hashes", "x0_hashes"):
        modified = copy.deepcopy(value)
        modified[key]["210202"] = "0" * 64
        with pytest.raises(RuntimeError, match="BLOCK_E3_IDENTITY_MISMATCH"):
            runner.validate_case_identity("210202", modified, identity)


def test_B100_reuse_accepts_exact_identity_and_rejects_mismatch() -> None:
    value = manifest()
    identity = runner.load_identities()["210202"]
    checks = runner.validate_b100_reuse("210202", value, identity)["checks"]
    assert all(checks.values())
    modified = copy.deepcopy(value)
    modified["B_ref_by_case"]["210202"] += 1.0
    with pytest.raises(RuntimeError, match="BLOCK_E3_B100_REUSE_IDENTITY_MISMATCH"):
        runner.validate_b100_reuse("210202", modified, identity)


def test_result_schema_and_budget_residual_contract() -> None:
    schema = json.loads((ROOT / "experiments/schemas/e3_budget_result.schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    for field in ("objective", "RI", "RS", "budget_slack", "budget_feasibility_pass", "certification_status"):
        assert field in required
    assert runner.budget_audit(100.0000005, 100.0, 1e-6)["budget_feasibility_pass"] is True
    assert runner.budget_audit(100.000002, 100.0, 1e-6)["budget_feasibility_pass"] is False


def test_e3_result_root_is_narrowly_ignored() -> None:
    completed = runner.subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e3_budget_sensitivity_v1/probe/result.json"],
        cwd=ROOT,
        check=False,
    )
    assert completed.returncode == 0
    assert runner.subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/not_e3/probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode != 0
