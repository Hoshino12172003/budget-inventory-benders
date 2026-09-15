from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import experiments.run_e1b_pure_benders_local as runner
from robust_inventory_reconfiguration.renault_empirical import sha256_file


ROOT = Path(__file__).resolve().parents[1]
CASES = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(runner.AUTHORIZATION.read_text(encoding="utf-8"))


def test_pure_grid_is_frozen_but_not_authorized(manifest) -> None:
    assert set(manifest["authorized_pure_run_ids"]) == {f"E1B-{case}-PURE" for case in CASES}
    assert manifest["case_ids"] == list(CASES)
    assert manifest["formal_run_authorized"] is False
    assert manifest["parameters"] == {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05}
    assert manifest["controlled_scaling_authorized"] is False
    assert manifest["e1a_rerun_authorized"] is False
    assert manifest["structured_e1b_modification_authorized"] is False
    assert manifest["e2_e7_modification_authorized"] is False


def test_runner_fails_closed_before_solver_call(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        runner,
        "solve_pure_benders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("optimizer invoked")),
    )
    with pytest.raises(PermissionError, match="NOT_AUTHORIZED"):
        runner.validate_execution_gate("210129", tmp_path)


def test_case_identities_match_paper_final_table(manifest) -> None:
    assert sha256_file(runner.IDENTITY_TABLE) == manifest["identity_table_sha256"]
    for case in CASES:
        identity = runner._identity(case)
        assert manifest["case_identities"][case] == {
            key: identity[key] for key in ("instance_hash", "x0_hash", "calibration_hash")
        }


def test_result_root_is_isolated_and_narrowly_ignored() -> None:
    assert runner.DEFAULT_OUTPUT_ROOT.name == "e1b_pure_benders_v1"
    assert runner.DEFAULT_OUTPUT_ROOT.name != "e1b_standard_vs_prb_v1"
    assert subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e1b_pure_benders_v1/probe/result.json"],
        cwd=ROOT,
    ).returncode == 0
    assert subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e1b-pure-not-in-scope/probe/result.json"],
        cwd=ROOT,
    ).returncode != 0


def test_runner_has_timeout_checkpoint_and_no_structured_or_prb_call() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "solve_pure_benders" in source
    assert "PureBendersTimeout" in source
    assert ".timeout" in source
    assert "solve_standard_benders" not in source
    assert "solve_prb_benders" not in source
    assert "compose_risk_budget" not in source
    assert "ProductRiskSubproblem" not in source
    assert "refusing to overwrite or resume" in source


def test_result_schema_preserves_core_timing_contract() -> None:
    schema = json.loads(
        (ROOT / "experiments/schemas/e1b_pure_benders_result.schema.json").read_text(encoding="utf-8")
    )
    required = set(schema["required"])
    assert {"core_runtime_seconds", "post_evaluation_runtime_seconds"} <= required
