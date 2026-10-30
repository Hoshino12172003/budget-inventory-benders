from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from experiments import run_e6_budget_risk_5x5_local as runner
from scripts import summarize_e6_budget_risk_5x5_results as summary


def test_grid_and_reuse_partition_are_complete_and_disjoint() -> None:
    all_ids = {condition.run_id for condition in runner.enumerate_conditions()}
    reuse_ids = {condition.run_id for condition in runner.planned_reuse_conditions()}
    new_ids = {condition.run_id for condition in runner.planned_new_solve_conditions()}
    assert len(runner.BETA_BY_TOKEN) * len(runner.GAMMA_BY_TOKEN) == 25
    assert len(all_ids) == 200
    assert len(reuse_ids) == 104
    assert len(new_ids) == 96
    assert reuse_ids.isdisjoint(new_ids)
    assert reuse_ids | new_ids == all_ids


def test_reuse_selection_is_deterministic() -> None:
    old = runner.Condition("210202", "B080", "G0")
    e3 = runner.Condition("210202", "B090", "G2")
    e4 = runner.Condition("210202", "B100", "G1")
    missing = runner.Condition("210202", "B090", "G1")
    assert runner.selected_source(old)[0:2] == ("E6", "E6-210202-B080-G0")
    assert runner.selected_source(e3)[0:2] == ("E3", "E3-210202-B090")
    assert runner.selected_source(e4)[0:2] == ("E4", "E4-210202-G1")
    assert runner.selected_source(missing) is None


def test_authorization_false_blocks_before_source_or_solver(monkeypatch) -> None:
    manifest = runner.load_manifest()
    assert manifest["formal_run_authorized"] is False
    monkeypatch.setattr(runner, "validate_source", lambda *_: pytest.fail("source audit reached"))
    with pytest.raises(PermissionError, match="NOT_AUTHORIZED"):
        runner.validate_execution_gate(manifest)


def test_partial_checkpoint_is_rejected(tmp_path: Path) -> None:
    condition = runner.Condition("210202", "B090", "G1")
    (tmp_path / "result.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="PARTIAL_CHECKPOINT"):
        runner.validate_checkpoint(condition, tmp_path, runner.load_manifest())


def test_aggregator_rejects_incomplete_grid(tmp_path: Path) -> None:
    run = tmp_path / "E6-5X5-210202-B100-G2"
    run.mkdir()
    (run / "result.json").write_text(
        json.dumps({"run_id": run.name, "status": "OPTIMAL", "certification_status": "CERTIFIED_PRB_EXACT"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="incomplete"):
        summary.load_complete_results(tmp_path)


def test_complete_grid_produces_two_discrete_5x5_matrices() -> None:
    results = {}
    for condition in runner.enumerate_conditions():
        results[condition.run_id] = {
            "objective": 100.0 + 10.0 * float(condition.beta) + condition.gamma,
            "RI": float(condition.beta) / 10.0 + condition.gamma / 100.0,
        }
    objective, ri = summary.matrices(results)
    assert len(objective) == len(ri) == 5
    assert all(list(row) == ["beta_token", "beta", "G0", "G1", "G2", "G3", "G4"] for row in objective)
    assert all(list(row) == ["beta_token", "beta", "G0", "G1", "G2", "G3", "G4"] for row in ri)
    assert objective[2]["G2"] == pytest.approx(1.0)


def test_manifest_preserves_scientific_contract_and_separate_namespace() -> None:
    manifest = runner.load_manifest()
    runner.validate_manifest(manifest)
    assert manifest["lambda_R"] == 0.05
    assert manifest["interpolation_allowed"] is False
    assert manifest["result_root"] != "experiments/results/e6_budget_risk_interaction_v1"
    assert manifest["formal_run_authorized"] is False


def test_frozen_model_dataset_and_solver_contract() -> None:
    manifest = runner.load_manifest()
    assert runner.e6_v1.source_model_identity() == manifest["model_identity_sha256"]
    assert runner.sha256(runner.e6_v1.PRB_FILE) == manifest["prb_identity_sha256"]
    assert {
        case: runner.sha256(runner.ROOT / f"data/formal_instances_v2/{case}.json")
        for case in runner.CASES
    } == manifest["instance_hashes"]
    assert manifest["solver_profile"] == "gurobi-balanced-1e-8-v1"
    assert manifest["budget_feasibility_tolerance"] == 1e-6
    assert manifest["budget_binding_tolerance"] == 1e-6
    assert manifest["objective_certification_tolerance"] == 1e-4
    assert manifest["reporting_tolerance"] == 1e-6
    assert manifest["materiality_tolerance"] == 1e-6


def test_atomic_write_provenance_no_overwrite_and_resume(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "RESULT_ROOT", tmp_path)
    condition = runner.Condition("210202", "B090", "G1")
    source_solution = tmp_path / "source_solution.json"
    source_solution.write_text("{}\n", encoding="utf-8")
    result = {
        "run_id": condition.run_id,
        "reused": False,
        "reuse_source_run": None,
        "reuse_source_result_sha256": None,
        "status": "OPTIMAL",
        "certification_status": "CERTIFIED_PRB_EXACT",
    }
    manifest = runner.load_manifest()
    runner.write_run(result, source_solution, manifest)
    target = tmp_path / condition.run_id
    provenance = json.loads((target / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["result_sha256"] == hashlib.sha256(
        (target / "result.json").read_bytes()
    ).hexdigest()
    assert provenance["first_stage_solution_sha256"] == hashlib.sha256(
        (target / "first_stage_solution.json").read_bytes()
    ).hexdigest()
    assert not list(tmp_path.glob(f".{condition.run_id}.*.tmp"))
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner.write_run(result, source_solution, manifest)
    monkeypatch.setattr(runner, "solve_new_result", lambda *_: pytest.fail("solver reached"))
    assert runner.run_condition(condition, manifest) == "CHECKPOINT_VALID_SKIP"


def test_audit_only_does_not_mutate_historical_sources() -> None:
    roots = (runner.E3_ROOT, runner.E4_ROOT, runner.E6_ROOT)
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for root in roots
        for path in root.rglob("*.json")
    }
    audit = runner.audit_only()
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
    assert audit["verified_reuse_cells"] == 104
    assert before == after


def test_missing_cell_manifest_is_exact_and_never_absorbs_failed_reuse() -> None:
    manifest = runner.load_manifest()
    missing = json.loads((runner.ROOT / manifest["missing_cells"]).read_text(encoding="utf-8"))
    expected = {condition.run_id for condition in runner.planned_new_solve_conditions()}
    reuse = {condition.run_id for condition in runner.planned_reuse_conditions()}
    assert {row["run_id"] for row in missing["cells"]} == expected
    assert len(expected) == 96
    assert len(reuse) == 104
    assert expected.isdisjoint(reuse)
