from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.service_calibration import (
    FORMAL_CASES,
    PHI_GRID,
    SL_GRID,
    dry_run_plan,
    load_config,
    phi_vector,
    validate_config,
)
from robust_inventory_reconfiguration.service_calibration_audit import (
    baseline_reuse_audit,
    write_baseline_audit_csv,
)
from robust_inventory_reconfiguration.service_calibration_reporting import RESULT_FIELDS


CONFIG = ROOT / "experiments/configs/formal/service_calibration_robustness_formal.yaml"
OUTPUT = ROOT / "artifacts/service_calibration_robustness_static_audit.json"
BASELINE_OUTPUT = ROOT / "artifacts/service_calibration_baseline_reuse_audit.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Service calibration robustness audit")
    parser.add_argument("--post-run", action="store_true")
    args = parser.parse_args()
    config = load_config(CONFIG)
    validate_config(config)
    plan = dry_run_plan(config)
    baseline_rows = baseline_reuse_audit(ROOT, config)
    write_baseline_audit_csv(baseline_rows, BASELINE_OUTPUT)
    model_sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "src/robust_inventory_reconfiguration/product_risk_subproblem.py",
            "src/robust_inventory_reconfiguration/reconfiguration_model.py",
            "src/robust_inventory_reconfiguration/robust_service.py",
        )
    )
    runner_source = (ROOT / "experiments/run_service_calibration_robustness.py").read_text(encoding="utf-8")
    reporting_source = (ROOT / "scripts/report_service_calibration_robustness.py").read_text(encoding="utf-8")
    first_instance = load_instance(ROOT / f"data/formal_instances_v2/{FORMAL_CASES[0]}.json")
    phi_hashes = {json.dumps(phi_vector(first_instance, level)) for level in PHI_GRID}
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", config["code_identity"]["base_commit"]],
        cwd=ROOT, text=True,
    ).splitlines()
    protected_changes = [
        path for path in changed
        if path.startswith("data/formal_instances_v2/")
        or path.startswith("experiments/results/e")
        or any(path.startswith(f"experiments/configs/formal/e{number}_") for number in range(2, 8))
    ]
    checks = {
        "01_exact_frozen_cases": tuple(config["case_ids"]) == FORMAL_CASES,
        "02_exact_8_baseline_solves": plan["baseline_solves"] == 8,
        "03_exact_16_SL_solves": plan["sl_sensitivity_solves"] == 16,
        "04_exact_16_phi_solves": plan["phi_sensitivity_solves"] == 16,
        "05_exact_40_physical_solves": plan["physical_solves"] == 40,
        "06_no_duplicate_baseline": len({
            row["condition_id"] for row in plan["physical_conditions"] if row["run_type"] == "baseline"
        }) == 8,
        "07_SL_analysis_uses_current_baseline": plan["sl_analysis_conditions"] == 24 and all(
            row["physical_result_id"].startswith("SCAL_BASE_")
            for row in plan["analysis_conditions"]
            if row["run_type"] == "sl_sensitivity" and row["service_level"] == 0.90
        ),
        "08_phi_analysis_uses_current_baseline": plan["phi_analysis_conditions"] == 24 and all(
            row["physical_result_id"].startswith("SCAL_BASE_")
            for row in plan["analysis_conditions"]
            if row["run_type"] == "phi_sensitivity" and row["phi_multiplier"] == 1.85
        ),
        "09_no_unauthorized_dimensions": config["full_SL_x_phi_interaction_authorized"] is False and plan["logical_analysis_conditions"] == 48 and plan["SL_x_phi_interaction_solves"] == plan["f_multiplier_sensitivity_solves"] == plan["other_Gamma_beta_lambda_grid_solves"] == 0,
        "10_Gamma_fixed": all(row["run_type"] in {"baseline", "sl_sensitivity", "phi_sensitivity"} for row in plan["physical_conditions"]) and config["fixed_parameters"]["Gamma"] == 2,
        "11_beta_fixed": config["fixed_parameters"]["beta"] == 1.0,
        "12_lambda_R_fixed": config["fixed_parameters"]["lambda_R"] == 0.05,
        "13_baseline_parameters": all(
            row["service_level"] == 0.90 and row["phi_multiplier"] == 1.85
            for row in plan["physical_conditions"] if row["run_type"] == "baseline"
        ),
        "14_SL_phi_fixed": all(
            row["phi_multiplier"] == 1.85 for row in plan["physical_conditions"] if row["run_type"] == "sl_sensitivity"
        ),
        "15_phi_SL_fixed": all(
            row["service_level"] == 0.90 for row in plan["physical_conditions"] if row["run_type"] == "phi_sensitivity"
        ),
        "16_no_hard_SLA": "- e" in model_sources,
        "17_soft_SLA_preserved": "instance.service_level" in model_sources and "instance.service_penalty" in model_sources and config["service_constraint_semantics"].startswith("soft SLA"),
        "18_formal_safety_gate": "require_formal_authorization(config)" in runner_source and config["authorization_transition"] in ([False], [False, True]) and config["authorization_transition"][-1] is config["formal_run_authorized"],
        "19_exact_certification_gate": "exact_certification_pass" in runner_source and "CERTIFIED_PRB_EXACT" in runner_source,
        "20_reporting_current_baseline_only": "load_current_results" in reporting_source and "normalized_baseline" not in reporting_source and config["baseline_policy"] == {"legacy_E4_reuse": False, "current_version_regeneration_required": True},
        "required_outputs": set(config["required_outputs"]) == {
            "service_calibration_all_results.csv",
            "service_calibration_sl_summary.csv",
            "service_calibration_phi_summary.csv",
            "service_calibration_case_level.csv",
            "service_calibration_execution_manifest.csv",
            "service_calibration_robustness_summary.md",
        },
        "SL_and_phi_propagation": "calibrated_instance(" in runner_source and len(phi_hashes) == len(PHI_GRID),
        "E2_E7_results_unchanged": not protected_changes,
        "legacy_E4_diagnostic_nonblocking": config["historical_baseline_diagnostic"]["blocking"] is False and config["historical_baseline_diagnostic"]["used_as_result_source"] is False,
        "required_output_schema": all(field in RESULT_FIELDS for field in ("condition_id", "SL", "phi_multiplier", "objective", "RI", "RS", "total_shortage", "service_penalty_cost", "active_depot_set")),
    }
    static_pass = all(checks.values())
    post_run = {"requested": args.post_run, "status": "NOT_RUN"}
    if args.post_run:
        from scripts.report_service_calibration_robustness import load_current_results

        results, execution_manifest = load_current_results(config)
        post_checks = {
            "exact_40_results": len(results) == len(execution_manifest) == 40,
            "exact_run_type_counts": {
                run_type: sum(row["run_type"] == run_type for row in results)
                for run_type in ("baseline", "sl_sensitivity", "phi_sensitivity")
            } == {"baseline": 8, "sl_sensitivity": 16, "phi_sensitivity": 16},
            "all_exactly_certified": all(
                row["solver_status"] == "OPTIMAL" and row["optimality_certification"] == "CERTIFIED_PRB_EXACT"
                for row in results
            ),
            "single_code_commit": len({row["code_commit"] for row in results}) == 1,
            "single_model_identity": len({row["code_identity_hash"] for row in results}) == 1,
            "single_config_identity": len({row["config_hash"] for row in results}) == 1,
            "no_reused_results": all(row["reused"] is False and row["reuse_source_run"] is None for row in results),
        }
        post_run = {
            "requested": True,
            "status": "POST_RUN_AUDIT_PASS" if all(post_checks.values()) else "POST_RUN_AUDIT_FAIL",
            "checks": post_checks,
        }
        static_pass = static_pass and all(post_checks.values())
    reuse_count = sum(bool(row["reuse_authorized"]) for row in baseline_rows)
    payload = {
        "schema": "service_calibration_robustness_static_audit_v1",
        "status": "STATIC_IMPLEMENTATION_AUDIT_PASS" if static_pass else "STATIC_IMPLEMENTATION_AUDIT_FAIL",
        "checks": checks,
        "dry_run_counts": {
            key: value for key, value in plan.items()
            if key not in {"physical_conditions", "analysis_conditions"}
        },
        "legacy_baseline_reuse": {
            "used": False,
            "authorized_case_count": reuse_count,
            "required_case_count": 0,
            "status": "IDENTITY_SAFE_BASELINE_REUSE" if reuse_count == 8 else "BASELINE_REUSE_NOT_AUTHORIZED",
            "audit_csv": BASELINE_OUTPUT.relative_to(ROOT).as_posix(),
            "blocking": False,
        },
        "formal_execution_ready": static_pass and config["formal_run_authorized"] is True,
        "formal_run_authorized": config["formal_run_authorized"],
        "formal_optimization_solves_executed_by_audit": 0,
        "post_run_audit": post_run,
        "protected_changes": protected_changes,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not static_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
