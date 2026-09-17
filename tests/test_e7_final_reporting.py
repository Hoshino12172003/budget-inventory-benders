from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def read_csv(name: str) -> list[dict]:
    with (ARTIFACTS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def audit() -> dict:
    return json.loads((ARTIFACTS / "e7_final_result_audit.json").read_text(encoding="utf-8"))


def test_final_audit_passes_all_correctness_checks() -> None:
    value = audit()
    assert value["status"] == "E7_FINAL_AUDIT_PASS"
    assert all(value["checks"].values())
    assert (value["expected_runs"], value["observed_runs"], value["reused"], value["new_formal_results"]) == (72, 72, 40, 32)


def test_all_case_rows_are_unique_and_exactly_certified() -> None:
    rows = read_csv("e7_table_risk_friction_case_level.csv")
    assert len(rows) == len({(row["case"], row["Gamma"], row["lambda_R"]) for row in rows}) == 72
    assert all(row["status"] == "OPTIMAL" for row in rows)
    assert all(row["certification_status"] == "CERTIFIED_PRB_EXACT" and row["exact_certification_pass"] == "True" for row in rows)
    assert all(row["artifact_validation_pass"] == "True" for row in rows)


def test_global_coupling_exception_is_numerical_only() -> None:
    value = json.loads((ARTIFACTS / "e7_210330_g4_l0025_global_coupling_audit.json").read_text(encoding="utf-8"))
    assert value["classification"] == "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH"
    assert value["persisted_master_closure_residual"] == pytest.approx(1.6399426385760307e-6)
    assert value["fresh_vs_stored_recourse_difference"] == 0.0
    assert value["objective_reconstruction_difference"] == 0.0
    assert value["Gamma_feasible"] is True
    assert value["risk_budget_allocation_sum"] == 4
    assert value["first_stage_reoptimized"] is False


def test_reuse_schema_missing_diagnostics_are_source_referenced() -> None:
    rows = read_csv("e7_table_risk_friction_case_level.csv")
    missing = [row for row in rows if row["global_coupling_diagnostic_status"] == "MISSING_BY_REUSE_SCHEMA_SOURCE_REFERENCED"]
    assert len(missing) == 8
    assert all(row["reused"] == "True" and row["Gamma"] == "2" and row["lambda_R"] == "0.05" for row in missing)
    assert all(row["global_coupling_diagnostic_source_status"] in {"PASS", "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH"} for row in missing)


def test_extensive_trigger_is_invariant_over_tested_lambda_grid() -> None:
    rows = read_csv("e7_table_interaction_contrasts.csv")
    assert len(rows) == 8
    assert all(row["extensive_trigger_invariant_across_lambda"] == "True" for row in rows)
    expected = {"210202": "2", "210129": "2", "210310": "4", "210330": "2", "210323": "2", "210628": "none_through_4", "210428": "none_through_4", "210611": "none_through_4"}
    for row in rows:
        assert {row["first_material_gamma_L0025"], row["first_material_gamma_L0500"], row["first_material_gamma_L2000"]} == {expected[row["case"]]}


def test_G4_intensive_response_declines_and_concentrates_with_friction() -> None:
    rows = {float(row["lambda_R"]): row for row in read_csv("e7_table_risk_friction_aggregate.csv") if row["Gamma"] == "4"}
    assert float(rows[0.0025]["mean_RI"]) > float(rows[0.05]["mean_RI"]) > float(rows[0.2]["mean_RI"])
    assert float(rows[0.0025]["mean_changed_pairs_conditional_on_material"]) > float(rows[0.05]["mean_changed_pairs_conditional_on_material"]) > float(rows[0.2]["mean_changed_pairs_conditional_on_material"])
    assert float(rows[0.0025]["mean_top_adjustment_share_conditional_on_material"]) < float(rows[0.05]["mean_top_adjustment_share_conditional_on_material"]) < float(rows[0.2]["mean_top_adjustment_share_conditional_on_material"])


def test_network_changes_are_limited_to_two_low_friction_G4_cells() -> None:
    assert audit()["network_change_observations"] == ["E7-210310-G4-L0025", "E7-210323-G4-L0025"]


def test_timing_is_complete_and_G4_post_evaluation_dominates() -> None:
    value = audit()["timing"]
    assert value["full_instrumentation_new_count"] == 32
    assert value["reuse_materialization_timing_count"] == 40
    assert value["post_evaluation_dominates_G4_new"] is True
    assert value["G4_new_mean_post_evaluation_seconds"] > 200 * value["G4_new_mean_core_prb_seconds"]


def test_publication_tables_and_figures_exist() -> None:
    tables = ("e7_table_risk_friction_case_level.csv", "e7_table_risk_friction_aggregate.csv", "e7_table_interaction_contrasts.csv", "e7_table_adjustment_composition.csv", "e7_runtime_breakdown.csv")
    figures = ("fig_e7_ri_interaction", "fig_e7_normalized_objective_interaction", "fig_e7_rs_interaction", "fig_e7_adjustment_concentration_interaction")
    assert all((ARTIFACTS / name).is_file() for name in tables)
    assert all((ARTIFACTS / f"{stem}.{suffix}").is_file() for stem in figures for suffix in ("png", "pdf"))


def test_audit_did_not_run_first_stage_or_overwrite_primary_results() -> None:
    value = audit()
    assert value["new_first_stage_optimization_solves"] == 0
    assert value["primary_results_overwritten"] is False
    assert value["E1_E6_overwritten"] is False
    assert value["frozen_scientific_settings_changed"] is False
