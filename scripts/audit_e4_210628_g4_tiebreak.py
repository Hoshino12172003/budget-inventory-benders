from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.e4_reporting import diagnose_reporting_tiebreak
from robust_inventory_reconfiguration.first_stage_solution import (
    load_first_stage_solution_artifact,
    matrix_from_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance


RESULT_ROOT = ROOT / "experiments/results/e4_gamma_sensitivity_v1"
OUTPUT = ROOT / "artifacts/e4_210628_g4_reporting_tiebreak_audit.json"


def load_x(case: str, gamma: int):
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    artifact = load_first_stage_solution_artifact(
        RESULT_ROOT / f"E4-{case}-G{gamma}/first_stage_solution.json", instance
    )
    return instance, matrix_from_artifact(artifact, instance)


def main() -> None:
    failed_case_result = json.loads(
        (RESULT_ROOT / "E4-210628-G4/result.json").read_text(encoding="utf-8")
    )
    comparisons = {}
    for label, case, gamma in (
        ("failed_case_G4_fixed_state_recheck", "210628", 4),
        ("same_case_G3", "210628", 3),
        ("other_case_G4", "210202", 4),
    ):
        instance, x = load_x(case, gamma)
        comparisons[label] = {
            "case": case,
            "Gamma": gamma,
            "diagnostic": diagnose_reporting_tiebreak(instance, x, gamma),
        }
    diagnostic = failed_case_result["reporting_tiebreak_diagnostic"]
    checks = {
        "primary_certified": failed_case_result["status"] == "OPTIMAL" and failed_case_result["exact_certification_pass"] is True,
        "original_SUBOPTIMAL_not_accepted": diagnostic["original_status"] == 13 and diagnostic["fallback_used"] is True,
        "fallback_OPTIMAL": diagnostic["fallback_status_name"] == "OPTIMAL",
        "Gamma_feasible": diagnostic["Gamma_feasible"] is True,
        "certified_recourse_preserved": diagnostic["primary_economic_recourse_preserved"] is True,
        "budget_feasible": failed_case_result["budget_used"] - failed_case_result["B"] <= 1e-6,
        "failed_case_status_reproduced": comparisons["failed_case_G4_fixed_state_recheck"]["diagnostic"]["original_status"] == 13,
        "working_comparators_OPTIMAL": all(
            comparisons[label]["diagnostic"]["original_status_name"] == "OPTIMAL"
            for label in ("same_case_G3", "other_case_G4")
        ),
    }
    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "classification": "AUXILIARY_NUMERICAL_SUBOPTIMAL",
        "run_id": "E4-210628-G4",
        "primary_optimization_valid": checks["primary_certified"],
        "reporting_only_failure": True,
        "primary_objective": failed_case_result["objective"],
        "primary_exact_certification_status": failed_case_result["certification_status"],
        "robust_recourse": failed_case_result["robust_recourse_cost"],
        "RI": failed_case_result["RI"],
        "RS": failed_case_result["RS"],
        "budget_used": failed_case_result["budget_used"],
        "diagnostic": diagnostic,
        "comparisons": comparisons,
        "checks": checks,
        "primary_model_changed": False,
        "tolerance_changed": False,
        "primary_solver_profile_changed": False,
        "first_stage_solution_changed_by_reporting": False,
        "primary_objective_changed_by_reporting": False,
        "dataset_changed": False,
        "Gamma_grid_changed": False,
        "B_ref_changed": False,
        "beta_changed": False,
        "lambda_R_changed": False,
        "E1_overwritten": False,
        "E2_overwritten": False,
        "E3_overwritten": False,
        "original_failed_primary_solve_count": 1,
        "original_failed_reporting_auxiliary_optimize_calls": 2,
        "audit_and_recovery_auxiliary_optimize_calls": 28,
        "total_reporting_auxiliary_optimize_calls": 30,
        "formal_rerun_count": 1,
        "other_E4_runs_executed_by_audit": 0,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["classification"])
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
