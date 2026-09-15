from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import experiments.run_e1b_standard_benders_local as runner
from robust_inventory_reconfiguration.renault_empirical import sha256_file


ROOT = Path(__file__).resolve().parents[1]
CASES = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(runner.AUTHORIZATION.read_text(encoding="utf-8"))


def test_e1b_grid_is_exactly_eight_standard_runs_and_not_authorized(manifest) -> None:
    expected = {f"E1B-{case}-STANDARD" for case in CASES}
    assert set(manifest["authorized_standard_run_ids"]) == expected
    assert manifest["case_ids"] == list(CASES)
    assert manifest["formal_run_authorized"] is False
    assert manifest["controlled_scaling_authorized"] is False
    assert manifest["e2_e7_modification_authorized"] is False
    assert manifest["parameters"] == {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05}


def test_runner_fails_closed_before_any_solver_call(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        runner,
        "solve_standard_benders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("optimizer invoked")),
    )
    with pytest.raises(PermissionError, match="NOT_AUTHORIZED"):
        runner.validate_execution_gate("210129", tmp_path)


def test_protected_code_and_document_hashes_are_frozen(manifest) -> None:
    protected = manifest["protected_identity"]
    paths = {
        "standard_implementation_sha256": ROOT / "src/robust_inventory_reconfiguration/standard_benders.py",
        "runner_sha256": ROOT / "experiments/run_e1b_standard_benders_local.py",
        "result_schema_sha256": ROOT / "experiments/schemas/e1b_standard_result.schema.json",
        "protocol_sha256": ROOT / "docs/e1b_standard_benders_protocol.md",
        "baseline_audit_sha256": ROOT / "docs/e1b_standard_benders_baseline_audit.md",
    }
    assert {key: sha256_file(path) for key, path in paths.items()} == protected


def test_all_e1a_prb_references_are_immutable_and_timing_compatible(manifest) -> None:
    for case in CASES:
        reference = manifest["prb_e1a_references"][case]
        path = ROOT / reference["result_path"]
        assert sha256_file(path) == reference["result_sha256"]
        result = json.loads(path.read_text(encoding="utf-8"))
        assert result["status"] == "OPTIMAL"
        assert result["exact_certification_status"] == "CERTIFIED_PRB_EXACT"
        assert result["solver_version"] == manifest["solver_version"] == "13.0.2"
        for field in (
            "runtime_seconds",
            "master_runtime_seconds",
            "subproblem_runtime_seconds",
            "certification_runtime_seconds",
            "iteration_count",
            "cut_count",
        ):
            assert result[field] is not None
    assert manifest["prb_timing_rerun_required"] is False


def test_case_identities_match_paper_final_table(manifest) -> None:
    assert sha256_file(runner.IDENTITY_TABLE) == manifest["identity_table_sha256"]
    for case in CASES:
        identity = runner._identity(case)
        assert manifest["case_identities"][case] == {
            key: identity[key] for key in ("instance_hash", "x0_hash", "calibration_hash")
        }


def test_result_schema_contains_core_and_post_timing() -> None:
    schema = json.loads(
        (ROOT / "experiments/schemas/e1b_standard_result.schema.json").read_text(encoding="utf-8")
    )
    required = set(schema["required"])
    assert {
        "core_runtime_seconds",
        "post_evaluation_runtime_seconds",
        "master_runtime_seconds",
        "oracle_runtime_seconds",
        "cut_construction_runtime_seconds",
        "certification_runtime_seconds",
    } <= required


def test_result_root_is_narrowly_ignored() -> None:
    assert subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e1b_standard_vs_prb_v1/probe/result.json"],
        cwd=ROOT,
    ).returncode == 0
    assert subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e1b-not-in-scope/probe/result.json"],
        cwd=ROOT,
    ).returncode != 0


def test_runner_is_standard_only_and_preserves_no_overwrite_contract() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "solve_prb_benders" not in source
    assert "solve_standard_benders" in source
    assert "refusing to overwrite or resume" in source
    assert "shutil.move" in source
