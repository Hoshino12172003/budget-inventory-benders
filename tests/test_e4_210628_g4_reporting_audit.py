from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts/e4_210628_g4_reporting_tiebreak_audit.json"
RESULT = ROOT / "experiments/results/e4_gamma_sensitivity_v1/E4-210628-G4/result.json"


def test_210628_g4_audit_rejects_suboptimal_candidate_and_preserves_primary() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    diagnostic = audit["diagnostic"]

    assert audit["status"] == "PASS"
    assert audit["classification"] == "AUXILIARY_NUMERICAL_SUBOPTIMAL"
    assert audit["primary_optimization_valid"] is True
    assert diagnostic["original_status"] == 13
    assert diagnostic["original_suboptimal_incumbent_preserved_primary_recourse"] is False
    assert diagnostic["fallback_status_name"] == "OPTIMAL"
    assert diagnostic["primary_economic_recourse_preserved"] is True
    assert diagnostic["Gamma_feasible"] is True
    assert diagnostic["selected_Gamma_allocation_count"] <= 4
    assert audit["primary_objective_changed_by_reporting"] is False
    assert audit["first_stage_solution_changed_by_reporting"] is False


def test_210628_g4_result_serializes_diagnostic_without_schema_regression() -> None:
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert result["status"] == "OPTIMAL"
    assert result["exact_certification_pass"] is True
    assert result["reporting_tiebreak_diagnostic"]["fallback_used"] is True
    assert "transport_cost" in result
    assert "transportation_cost" not in result


def test_fixed_state_recheck_reproduces_failure_and_controls_are_optimal() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    comparisons = audit["comparisons"]

    assert comparisons["failed_case_G4_fixed_state_recheck"]["diagnostic"]["original_status"] == 13
    assert comparisons["same_case_G3"]["diagnostic"]["original_status_name"] == "OPTIMAL"
    assert comparisons["other_case_G4"]["diagnostic"]["original_status_name"] == "OPTIMAL"
    assert comparisons["failed_case_G4_fixed_state_recheck"]["diagnostic"]["tied_Gamma_allocation_count"] == 1
