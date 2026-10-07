from __future__ import annotations

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
        "02_exact_SL_grid": tuple(config["sl_grid"]) == SL_GRID,
        "03_exact_phi_grid": tuple(config["phi_multiplier_grid"]) == PHI_GRID,
        "04_SL_OFAT_fixed_parameters": all(
            row["phi_multiplier"] == 1.85 for row in plan["conditions"] if row["run_type"] == "sl_sensitivity"
        ),
        "05_phi_OFAT_fixed_parameters": all(
            row["service_level"] == 0.90 for row in plan["conditions"] if row["run_type"] == "phi_sensitivity"
        ),
        "06_no_interaction_conditions": plan["reported_OFAT_conditions"] == 48 and config["full_SL_x_phi_interaction_authorized"] is False,
        "07_baseline_reuse_identity_gate": "BASELINE_REUSE_NOT_AUTHORIZED" in runner_source and all("reuse_authorized" in row for row in baseline_rows),
        "08_exact_32_new_solves": plan["new_formal_optimization_solves_if_baseline_reuse_authorized"] == 32,
        "09_exact_certification_gate": "exact_certification_pass" in runner_source and "CERTIFIED_PRB_EXACT" in runner_source,
        "10_case_and_aggregate_outputs": set(config["required_outputs"]) == {
            "service_calibration_all_results.csv",
            "service_calibration_sl_summary.csv",
            "service_calibration_phi_summary.csv",
            "service_calibration_case_level.csv",
            "service_calibration_baseline_reuse_audit.csv",
            "service_calibration_robustness_summary.md",
        },
        "11_SL_enters_optimization_model": "instance.service_level" in model_sources and "calibrated_instance(" in runner_source,
        "12_phi_multiplier_changes_vector": len(phi_hashes) == len(PHI_GRID) and "instance.service_penalty" in model_sources,
        "13_soft_SLA_preserved": "- e" in model_sources and "service_penalty" in model_sources and config["service_constraint_semantics"].startswith("soft SLA"),
        "14_E2_E7_results_unchanged": not protected_changes,
        "15_explicit_authorization_gate_false": config["formal_run_authorized"] is False and config["authorization_transition"] == [False],
        "required_output_schema": all(field in RESULT_FIELDS for field in ("condition_id", "SL", "phi_multiplier", "objective", "RI", "RS", "total_shortage", "service_penalty_cost", "active_depot_set")),
    }
    static_pass = all(checks.values())
    reuse_count = sum(bool(row["reuse_authorized"]) for row in baseline_rows)
    payload = {
        "schema": "service_calibration_robustness_static_audit_v1",
        "status": "STATIC_IMPLEMENTATION_AUDIT_PASS" if static_pass else "STATIC_IMPLEMENTATION_AUDIT_FAIL",
        "checks": checks,
        "dry_run_counts": {key: value for key, value in plan.items() if key != "conditions"},
        "baseline_reuse": {
            "authorized_case_count": reuse_count,
            "required_case_count": 8,
            "status": "IDENTITY_SAFE_BASELINE_REUSE" if reuse_count == 8 else "BASELINE_REUSE_NOT_AUTHORIZED",
            "audit_csv": BASELINE_OUTPUT.relative_to(ROOT).as_posix(),
        },
        "formal_execution_ready": static_pass and reuse_count == 8 and config["formal_run_authorized"] is True,
        "formal_run_authorized": config["formal_run_authorized"],
        "formal_optimization_solves_executed_by_audit": 0,
        "protected_changes": protected_changes,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not static_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
