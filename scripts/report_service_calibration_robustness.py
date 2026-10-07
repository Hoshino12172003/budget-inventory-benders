from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.service_calibration import (
    BASELINE_PHI_MULTIPLIER,
    BASELINE_SL,
    canonical_hash,
    file_sha256,
    load_config,
    phi_vector,
    validate_config,
)
from robust_inventory_reconfiguration.service_calibration_audit import (
    baseline_reuse_audit,
    load_identity_table,
    source_model_identity,
)
from robust_inventory_reconfiguration.service_calibration_reporting import (
    RESULT_FIELDS,
    write_reports,
)


CONFIG = ROOT / "experiments/configs/formal/service_calibration_robustness_formal.yaml"


def normalized_baseline(case: str, config: dict) -> dict:
    source_root = ROOT / config["baseline_source"]["result_root"] / config["baseline_source"]["run_pattern"].replace("<case>", case)
    source = json.loads((source_root / "result.json").read_text(encoding="utf-8"))
    solution = json.loads((source_root / "first_stage_solution.json").read_text(encoding="utf-8"))
    provenance = json.loads((source_root / "provenance.json").read_text(encoding="utf-8"))
    instance_path = ROOT / f"data/formal_instances_v2/{case}.json"
    instance = load_instance(instance_path)
    identities = load_identity_table(ROOT, config["identity_table"])
    phi = phi_vector(instance, BASELINE_PHI_MULTIPLIER)
    active_set = [row["depot_id"] for row in solution["y"] if row["value"]]
    return {
        "experiment_id": config["experiment_id"], "case_id": case,
        "condition_id": f"SC-{case}-BASELINE", "run_type": "sl_sensitivity",
        "config_hash": canonical_hash(config), "instance_hash": identities[case]["instance_hash"],
        "data_hash": file_sha256(instance_path), "canonical_instance_identity": instance.provenance.get("raw_source_identity"),
        "code_commit": provenance["git_commit"],
        "code_identity_hash": source_model_identity(ROOT, config["code_identity"]["model_files"]),
        "Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "SL": BASELINE_SL,
        "phi_multiplier": BASELINE_PHI_MULTIPLIER, "phi_vector_hash": canonical_hash(phi),
        "phi_min": min(phi), "phi_max": max(phi), "phi_mean": mean(phi),
        "solver_status": source["status"], "optimality_certification": source["certification_status"],
        "objective": source["objective"], "lower_bound": source["lower_bound"], "upper_bound": source["upper_bound"],
        "optimality_gap": source["relative_gap"], "benders_iterations": source["iterations"],
        "number_of_cuts": source["cuts_added"], "core_solve_time": source["runtime_seconds"],
        "master_time": source.get("master_runtime_seconds"), "oracle_subproblem_time": source.get("subproblem_runtime_seconds"),
        "certification_time": source.get("certification_runtime_seconds"), "RI": source["RI"], "RS": source["RS"],
        "material_reconfiguration": source["RI"] > config["material_reconfiguration_threshold"],
        "total_upward_adjustment": source["total_a_plus"], "total_downward_adjustment": source["total_a_minus"],
        "budget": source["B"], "reconfiguration_spending": source["reconfiguration_cost"],
        "budget_utilization": source["budget_utilization"],
        "budget_binding": abs(source["B"] - source["budget_used"]) <= config["budget_binding_threshold"],
        "total_shortage": source["worst_recourse_total_shortage"],
        "shortage_cost": source["worst_recourse_shortage_cost"],
        "service_violation_amount": None,
        "service_violation_metric_status": "UNAVAILABLE_IN_FROZEN_EVALUATION_CONTRACT; penalty cost preserved",
        "service_penalty_cost": source["worst_recourse_service_penalty_cost"],
        "aggregate_fill_rate": source["average_fill_rate"], "minimum_fill_rate": source["minimum_fill_rate"],
        "worst_region": source["worst_region"], "worst_product": source.get("worst_product"),
        "active_depot_count": len(active_set), "active_depot_set": json.dumps(active_set),
        "activated_depots_vs_baseline": json.dumps([]), "deactivated_depots_vs_baseline": json.dumps([]),
        "reused": True, "reuse_source_run": source["run_id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Service calibration robustness reporting")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    validate_config(config)
    if args.validate_only:
        print(json.dumps({"schema_fields": list(RESULT_FIELDS), "required_outputs": config["required_outputs"]}, indent=2))
        return
    audit_rows = baseline_reuse_audit(ROOT, config)
    if not all(row["reuse_authorized"] for row in audit_rows):
        raise PermissionError("BASELINE_REUSE_NOT_AUTHORIZED")
    result_root = ROOT / config["output_directory"]
    physical_results = [normalized_baseline(case, config) for case in config["case_ids"]]
    for path in sorted((result_root / "physical_results").glob("*/result.json")):
        physical_results.append(json.loads(path.read_text(encoding="utf-8")))
    write_reports(physical_results, audit_rows, result_root)


if __name__ == "__main__":
    main()
