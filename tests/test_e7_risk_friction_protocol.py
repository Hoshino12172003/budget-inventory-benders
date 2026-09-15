from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

import experiments.run_e7_risk_friction_local as runner
from scripts.summarize_e7_risk_friction_results import (
    first_material_gamma,
    interaction_contrast_for_case,
    margin_summary,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def manifest() -> dict:
    value = runner.load_manifest()
    runner.validate_manifest(value)
    return value


@pytest.fixture(scope="module")
def plan(manifest: dict) -> list[dict]:
    return runner.build_reuse_plan(manifest)


def test_only_frozen_tokens_are_accepted() -> None:
    assert runner.parse_gamma_token("g4") == "G4"
    assert runner.parse_lambda_token("l0025") == "L0025"
    for token in ("G1", "4", "G04"):
        with pytest.raises(ValueError, match="Gamma token"):
            runner.parse_gamma_token(token)
    for token in ("L0000", "0.05", "L0100"):
        with pytest.raises(ValueError, match="lambda token"):
            runner.parse_lambda_token(token)


def test_grid_has_72_unique_conditions() -> None:
    conditions = runner.enumerate_conditions()
    assert len(conditions) == len({condition.run_id for condition in conditions}) == 72
    assert conditions[0].run_id == "E7-210202-G0-L0025"
    assert conditions[-1].run_id == "E7-210611-G4-L2000"


def test_manifest_freezes_beta_and_authorizes_only_e7(manifest: dict) -> None:
    assert manifest["beta"] == runner.BETA == 1.0
    assert manifest["formal_run_authorized"] is True
    assert manifest["authorization_transition"] == [False, True]
    assert manifest["authorization_scope"] == ["E7_RISK_FRICTION_INTERACTION_V1"]


def test_authorization_record_matches_all_frozen_identities(manifest: dict) -> None:
    record = runner.validate_authorization_record(manifest)
    assert record["authorization_state"] == "AUTHORIZED"
    assert record["formal_results_in_record"] is False
    assert record["runner_sha256"] == runner.sha256(Path(runner.__file__))
    assert record["manifest_sha256"] == runner.sha256(runner.MANIFEST)


def test_reuse_is_derived_as_40_and_new_as_32(plan: list[dict]) -> None:
    reused = [row for row in plan if row["classification"] == "REUSE"]
    new = [row for row in plan if row["classification"] == "NEW_SOLVE"]
    assert (len(reused), len(new)) == (40, 32)
    assert {(row["Gamma_token"], row["lambda_token"]) for row in new} == {
        ("G0", "L0025"), ("G0", "L2000"), ("G4", "L0025"), ("G4", "L2000")
    }


def test_e4_e5_overlap_is_corroborated_and_counted_once(plan: list[dict]) -> None:
    overlap = [row for row in plan if len(row["source_candidates"]) == 2]
    assert len(overlap) == 8
    assert all(row["Gamma_token"] == "G2" and row["lambda_token"] == "L0500" for row in overlap)
    assert all(row["selected_source_experiment"] == "E4" for row in overlap)
    assert all(all(row["overlap_identity_checks"].values()) for row in overlap)


def test_reuse_identity_mismatch_fails_closed(manifest: dict) -> None:
    changed = copy.deepcopy(manifest)
    changed["x0_hashes"]["210202"] = "0" * 64
    with pytest.raises(RuntimeError, match="BLOCK_E7_CASE_IDENTITY"):
        runner.build_reuse_plan(changed)


def test_dry_run_has_zero_optimizer_calls(monkeypatch) -> None:
    monkeypatch.setattr(runner, "solve_prb_benders", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("optimizer invoked")))
    result = runner.dry_run()
    assert result["status"] == "E7_AUTHORIZED_DRY_RUN_PASS"
    assert result["optimization_solver_invocations"] == 0
    assert (result["total_conditions"], result["reusable_conditions"], result["new_solve_conditions"]) == (72, 40, 32)
    assert result["G4_L2000_feasible_cases"] == 8


def test_authorization_identity_mismatch_fails_closed(manifest: dict, tmp_path: Path, monkeypatch) -> None:
    changed = json.loads(runner.AUTHORIZATION_RECORD.read_text(encoding="utf-8"))
    changed["runner_sha256"] = "0" * 64
    record = tmp_path / "authorization.json"
    record.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(runner, "AUTHORIZATION_RECORD", record)
    with pytest.raises(RuntimeError, match="BLOCK_E7_AUTHORIZATION_IDENTITY"):
        runner.validate_authorization_record(manifest)


def test_overwrite_prevention(tmp_path: Path) -> None:
    run_id = runner.enumerate_conditions()[0].run_id
    (tmp_path / run_id).mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner.check_output_target(run_id, tmp_path)


def _write_completed_condition(root: Path, condition, manifest: dict) -> None:
    target = root / condition.run_id
    target.mkdir()
    timing = {field: 0.0 for field in manifest["timing_fields"]}
    result = {
        "run_id": condition.run_id, "case": condition.case, "Gamma": condition.gamma,
        "lambda_R": condition.lambda_r, "beta": 1.0, "status": "OPTIMAL",
        "certification_status": "CERTIFIED_PRB_EXACT", "exact_certification_pass": True,
        "timing": timing,
    }
    result_path = target / "result.json"
    solution_path = target / "first_stage_solution.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    solution_path.write_text("{}", encoding="utf-8")
    provenance = {
        "run_id": condition.run_id, "completion_status": "COMPLETED",
        "result_sha256": runner.sha256(result_path),
        "first_stage_solution_sha256": runner.sha256(solution_path),
        "authorization_record_sha256": runner.sha256(runner.AUTHORIZATION_RECORD),
    }
    (target / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")


def test_resume_states_distinguish_absent_completed_and_partial(tmp_path: Path, manifest: dict) -> None:
    absent = runner.Condition("210202", "G0", "L0025")
    complete = runner.Condition("210202", "G0", "L0500")
    partial = runner.Condition("210202", "G0", "L2000")
    _write_completed_condition(tmp_path, complete, manifest)
    (tmp_path / f".{partial.run_id}.interrupted.tmp").mkdir()
    assert runner.classify_output_state(absent, manifest, tmp_path)["state"] == "ABSENT"
    assert runner.classify_output_state(complete, manifest, tmp_path)["state"] == "COMPLETED"
    status = runner.classify_output_state(partial, manifest, tmp_path)
    assert status["state"] == "PARTIAL"
    assert partial.run_id == status["run_id"]


def test_result_namespace_is_narrowly_ignored() -> None:
    assert subprocess.run(["git", "check-ignore", "-q", "experiments/results/e7_risk_friction_interaction_v1/probe/result.json"], cwd=ROOT).returncode == 0
    assert subprocess.run(["git", "check-ignore", "-q", "experiments/results/e7-not-in-scope/probe/result.json"], cwd=ROOT).returncode != 0


def test_timing_schema_and_containment(manifest: dict) -> None:
    schema = json.loads((ROOT / manifest["result_schema"]).read_text(encoding="utf-8"))
    assert schema["properties"]["timing"]["required"] == manifest["timing_fields"]
    timing = {field: 1.0 for field in manifest["timing_fields"]}
    timing["t_total_runner_wallclock_seconds"] = 7.0
    assert runner.timing_containment_passes(timing)
    timing["t_total_runner_wallclock_seconds"] = 6.0
    assert not runner.timing_containment_passes(timing)


def test_launcher_is_restart_safe_and_never_deletes_results() -> None:
    text = (ROOT / "scripts/run_e7_formal.ps1").read_text(encoding="utf-8")
    assert "--status-only" in text
    assert 'state -eq "COMPLETED"' in text
    assert 'state -eq "ABSENT"' in text
    assert "partial/interrupted condition detected" in text
    assert "Remove-Item" not in text


def test_stage_level_progress_logging_is_present() -> None:
    text = Path(runner.__file__).read_text(encoding="utf-8")
    for stage in ("core_prb", "exact_certification", "post_evaluation", "artifact_write"):
        assert f"stage={stage}" in text


def synthetic_rows() -> list[dict]:
    return [
        {"case": "test", "Gamma": gamma, "lambda_R": value,
         "RI": gamma * (0.25 - value), "objective": 100 + gamma * (1 - value),
         "robust_recourse_cost": 50 + gamma * (0.5 - value), "RS": gamma * value,
         "changed_pair_count": gamma, "canonical_total_adjustment": 10 * gamma,
         "material_reconfiguration": gamma >= (4 if value == 0.2 else 2)}
        for gamma in (0, 2, 4) for value in (0.0025, 0.05, 0.2)
    ]


def test_interaction_and_did_math() -> None:
    out = interaction_contrast_for_case("test", synthetic_rows())
    assert out["delta_Gamma_RI_L0025"] == pytest.approx(0.99)
    assert out["delta_Gamma_RI_L2000"] == pytest.approx(0.2)
    assert out["DID_RI_low_vs_high_friction"] == pytest.approx(0.79)
    assert out["DID_objective_low_vs_high_friction"] == pytest.approx(0.79)


def test_extensive_and_intensive_margin_helpers() -> None:
    rows = synthetic_rows()
    assert first_material_gamma(rows, 0.2) == "4"
    summary = margin_summary(rows)
    assert summary["observation_count"] == 9
    assert summary["material_count"] == 5
    assert summary["mean_RI_conditional_on_material"] is not None


def test_reused_result_satisfies_frozen_schema(manifest: dict) -> None:
    condition = runner.Condition("210202", "G2", "L0500")
    source = next(item for item in runner.discover_source_candidates()[(condition.case, condition.gamma_token, condition.lambda_token)] if item["experiment"] == "E4")
    instance = runner.load_instance(ROOT / "data/formal_instances_v2/210202.json")
    x0 = json.loads((ROOT / "artifacts/renault_empirical_8case_v1/x0/210202.json").read_text(encoding="utf-8"))["x0"]
    result, solution = runner.build_reused_result(condition, manifest, runner.load_identities()["210202"], source, instance, x0)
    required = json.loads((ROOT / manifest["result_schema"]).read_text(encoding="utf-8"))["required"]
    assert set(required) - {"timing"} <= set(result)
    assert solution.name == "first_stage_solution.json"


def test_reporting_complexity_and_no_unproven_acceleration(manifest: dict) -> None:
    contract = manifest["reporting_evaluator_contract"]
    assert contract["Gamma4_product_risk_blocks"] == 6352
    assert contract["Gamma4_global_scenarios"] == 3469497
    assert contract["acceleration_status"] == "NOT_IMPLEMENTED"


def test_static_audit_passes_without_results_or_solves() -> None:
    audit = json.loads((ROOT / "artifacts/e7_static_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "E7_PROTOCOL_STATIC_AUDIT_PASS"
    assert audit["formal_first_stage_optimization_solves_executed"] == 0
    assert audit["checks"]["protected_E1_E6_hashes_preserved"] is True
    assert audit["existing_E7_outputs"] == []
    assert audit["formal_run_authorized"] is False


def test_authorized_reporting_paths_now_contain_final_outputs(manifest: dict) -> None:
    assert all((ROOT / path).is_file() for path in manifest["future_tables"])
    assert all((ROOT / f"{stem}.{suffix}").is_file() for stem in manifest["future_figures"] for suffix in ("png", "pdf"))
