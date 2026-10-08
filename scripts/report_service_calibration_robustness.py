from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.service_calibration import (
    canonical_hash,
    enumerate_conditions,
    file_sha256,
    load_config,
    validate_config,
)
from robust_inventory_reconfiguration.service_calibration_reporting import (
    RESULT_FIELDS,
    write_reports,
)


CONFIG = ROOT / "experiments/configs/formal/service_calibration_robustness_formal.yaml"


def load_current_results(config: dict) -> tuple[list[dict], list[dict]]:
    result_root = ROOT / config["output_directory"] / "physical_results"
    config_hash = canonical_hash(config)
    results = []
    manifest = []
    for condition in enumerate_conditions():
        run_root = result_root / condition.condition_id
        result_path = run_root / "result.json"
        solution_path = run_root / "first_stage_solution.json"
        scenarios_path = run_root / "service_scenarios.json"
        provenance_path = run_root / "provenance.json"
        if not all(path.is_file() for path in (result_path, solution_path, scenarios_path, provenance_path)):
            raise FileNotFoundError(f"incomplete current-version physical result: {condition.condition_id}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        checks = {
            "condition": result["condition_id"] == condition.condition_id,
            "case": result["case_id"] == condition.case_id,
            "run_type": result["run_type"] == condition.run_type,
            "parameters": result["SL"] == condition.service_level and result["phi_multiplier"] == condition.phi_multiplier,
            "config": result["config_hash"] == config_hash,
            "model_identity": result["code_identity_hash"] == config["code_identity"]["current_model_identity_sha256"],
            "fixed_parameters": result["Gamma"] == 2 and result["beta"] == 1.0 and result["lambda_R"] == 0.05,
            "not_reused": result["reused"] is False and result["reuse_source_run"] is None,
            "result_hash": provenance["result_sha256"] == file_sha256(result_path),
            "solution_hash": provenance["first_stage_solution_sha256"] == file_sha256(solution_path),
            "service_hash": provenance["service_scenarios_sha256"] == file_sha256(scenarios_path),
            "commit": provenance["git_commit"] == result["code_commit"],
            "certification": result["solver_status"] == "OPTIMAL" and result["optimality_certification"] == "CERTIFIED_PRB_EXACT",
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise RuntimeError(f"current result identity failure {condition.condition_id}: {','.join(failed)}")
        results.append(result)
        manifest.append({
            "experiment_id": result["experiment_id"],
            "condition_id": result["condition_id"],
            "case_id": result["case_id"],
            "run_type": result["run_type"],
            "SL": result["SL"],
            "phi_multiplier": result["phi_multiplier"],
            "Gamma": result["Gamma"],
            "beta": result["beta"],
            "lambda_R": result["lambda_R"],
            "config_hash": result["config_hash"],
            "instance_hash": result["instance_hash"],
            "data_hash": result["data_hash"],
            "code_commit": result["code_commit"],
            "code_identity_hash": result["code_identity_hash"],
            "phi_vector_hash": result["phi_vector_hash"],
            "solver_status": result["solver_status"],
            "optimality_certification": result["optimality_certification"],
            "result_sha256": provenance["result_sha256"],
            "first_stage_solution_sha256": provenance["first_stage_solution_sha256"],
            "service_scenarios_sha256": provenance["service_scenarios_sha256"],
        })
    return results, manifest


def historical_e4_sanity(config: dict, current_results: list[dict]) -> dict:
    historical = config["historical_baseline_diagnostic"]
    current = {row["case_id"]: row for row in current_results if row["run_type"] == "baseline"}
    comparisons = []
    errors = []
    for case in config["case_ids"]:
        path = ROOT / historical["result_root"] / historical["run_pattern"].replace("<case>", case) / "result.json"
        if not path.is_file():
            continue
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            new = current[case]
            comparisons.append({
                "case_id": case,
                "objective_delta": new["objective"] - old["objective"],
                "RI_delta": new["RI"] - old["RI"],
                "RS_delta": new["RS"] - old["RS"],
                "active_depot_count_delta": new["active_depot_count"] - old["active_depots"],
                "fill_rate_delta": new["aggregate_fill_rate"] - old["average_fill_rate"],
                "shortage_delta": new["total_shortage"] - old["worst_recourse_total_shortage"],
            })
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
            errors.append({"case_id": case, "error": type(error).__name__})
    return {
        "status": "AVAILABLE" if comparisons and not errors else "PARTIAL" if comparisons else "UNAVAILABLE",
        "blocking": False,
        "used_for_formal_identity": False,
        "case_count": len(comparisons),
        "comparisons": comparisons,
        "errors": errors,
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
    physical_results, execution_manifest = load_current_results(config)
    historical = historical_e4_sanity(config, physical_results)
    write_reports(
        physical_results,
        execution_manifest,
        ROOT / config["output_directory"],
        historical_diagnostic=historical,
    )


if __name__ == "__main__":
    main()
