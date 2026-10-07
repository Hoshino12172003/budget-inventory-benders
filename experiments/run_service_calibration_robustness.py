from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.e4_reporting import evaluate_e4_service
from robust_inventory_reconfiguration.e5_reporting import canonical_adjustment
from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.service_calibration import (
    GAMMA,
    LAMBDA_R,
    calibrated_instance,
    canonical_hash,
    dry_run_plan,
    enumerate_conditions,
    file_sha256,
    load_config,
    require_formal_authorization,
    validate_config,
)
from robust_inventory_reconfiguration.service_calibration_audit import load_identity_table, source_model_identity
from robust_inventory_reconfiguration.service_calibration_reporting import RESULT_FIELDS


CONFIG = ROOT / "experiments/configs/formal/service_calibration_robustness_formal.yaml"


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _cost_components(instance, solution, lambda_r: float) -> tuple[float, float, float]:
    fixed = sum(instance.fixed_depot_cost[i] * solution.y[i] for i in range(instance.num_depots))
    inventory = sum(instance.inventory_cost[i][j] * solution.x[i][j] for i in range(instance.num_depots) for j in range(instance.num_products))
    reconfiguration = lambda_r * sum(
        instance.inventory_cost[i][j] * (solution.a_plus[i][j] + solution.a_minus[i][j])
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    return fixed, inventory, reconfiguration


def _condition_map():
    return {condition.condition_id: condition for condition in enumerate_conditions()}


def validate_execution_gate(config: dict) -> None:
    validate_config(config)
    require_formal_authorization(config)
    if source_model_identity(ROOT, config["code_identity"]["model_files"]) != config["code_identity"]["current_model_identity_sha256"]:
        raise RuntimeError("SERVICE_CALIBRATION_MODEL_IDENTITY_MISMATCH")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("formal service-calibration execution requires a clean committed worktree")


def solve_condition(condition, config: dict) -> tuple[dict, dict, list[dict]]:
    base_instance_path = ROOT / f"data/formal_instances_v2/{condition.case_id}.json"
    base_instance = load_instance(base_instance_path)
    instance = calibrated_instance(
        base_instance,
        service_level=condition.service_level,
        phi_multiplier=condition.phi_multiplier,
    )
    x0_artifact = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case_id}.json").read_text(encoding="utf-8"))
    x0, y0 = x0_artifact["x0"], x0_artifact["y0"]
    budget = config["B_ref_by_case"][condition.case_id]
    solved = solve_prb_benders(
        instance,
        x0,
        budget,
        GAMMA,
        LAMBDA_R,
        relative_gap_tolerance=config["solver_tolerances"]["relative_gap"],
        cut_tolerance=config["solver_tolerances"]["cut_violation"],
        max_iterations=config["algorithm"]["max_iterations"],
    )
    if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
        raise RuntimeError("service-calibration solve is not exactly certified")
    service, reporting_diagnostic = evaluate_e4_service(
        instance, solved.solution.x, GAMMA,
        optimality_tolerance=config["solver_tolerances"]["cut_violation"],
    )
    fixed, inventory, reconfiguration = _cost_components(instance, solved.solution, LAMBDA_R)
    budget_used = fixed + inventory + reconfiguration
    if budget_used - budget > config["solver_tolerances"]["budget_feasibility"]:
        raise RuntimeError("service-calibration financial budget violation")
    adjustment = canonical_adjustment(
        solved.solution.x, x0,
        material_tolerance=config["material_reconfiguration_threshold"],
    )
    identities = load_identity_table(ROOT, config["identity_table"])
    identity = identities[condition.case_id]
    phi_hash = canonical_hash(instance.service_penalty)
    active_set = [instance.depot_ids[i] for i, active in enumerate(solved.solution.y) if active]
    config_hash = canonical_hash(config)
    code_hash = source_model_identity(ROOT, config["code_identity"]["model_files"])
    worst = service.worst_recourse_scenario
    result = {
        "experiment_id": config["experiment_id"],
        "case_id": condition.case_id,
        "condition_id": condition.physical_result_id,
        "run_type": condition.run_type,
        "config_hash": config_hash,
        "instance_hash": identity["instance_hash"],
        "data_hash": file_sha256(base_instance_path),
        "canonical_instance_identity": base_instance.provenance.get("raw_source_identity"),
        "code_commit": git_commit(),
        "code_identity_hash": code_hash,
        "Gamma": GAMMA,
        "beta": config["fixed_parameters"]["beta"],
        "lambda_R": LAMBDA_R,
        "SL": condition.service_level,
        "phi_multiplier": condition.phi_multiplier,
        "phi_vector_hash": phi_hash,
        "phi_min": min(instance.service_penalty),
        "phi_max": max(instance.service_penalty),
        "phi_mean": mean(instance.service_penalty),
        "solver_status": solved.status,
        "optimality_certification": "CERTIFIED_PRB_EXACT",
        "objective": budget_used + service.robust_recourse_cost,
        "lower_bound": solved.final_lower_bound,
        "upper_bound": solved.final_upper_bound,
        "optimality_gap": solved.final_relative_gap,
        "benders_iterations": len(solved.iterations),
        "number_of_cuts": solved.unique_product_cuts,
        "core_solve_time": solved.total_runtime,
        "master_time": solved.master_runtime,
        "oracle_subproblem_time": solved.separation_runtime,
        "certification_time": solved.certification_runtime,
        "RI": adjustment.reconfiguration_index,
        "RS": reconfiguration / budget,
        "material_reconfiguration": adjustment.reconfiguration_index > config["material_reconfiguration_threshold"],
        "total_upward_adjustment": adjustment.total_a_plus,
        "total_downward_adjustment": adjustment.total_a_minus,
        "budget": budget,
        "reconfiguration_spending": reconfiguration,
        "budget_utilization": budget_used / budget,
        "budget_binding": abs(budget - budget_used) <= config["budget_binding_threshold"],
        "total_shortage": worst.total_shortage,
        "shortage_cost": worst.shortage_cost,
        "service_violation_amount": None,
        "service_violation_metric_status": "UNAVAILABLE_IN_FROZEN_EVALUATION_CONTRACT; penalty cost preserved",
        "service_penalty_cost": worst.service_penalty_cost,
        "aggregate_fill_rate": service.worst_service_scenario.average_fill_rate,
        "minimum_fill_rate": service.worst_service_scenario.minimum_fill_rate,
        "worst_region": service.worst_service_scenario.worst_region_id,
        "worst_product": None,
        "active_depot_count": len(active_set),
        "active_depot_set": json.dumps(active_set),
        "activated_depots_vs_baseline": None,
        "deactivated_depots_vs_baseline": None,
        "reused": False,
        "reuse_source_run": None,
        "fixed_cost": fixed,
        "inventory_cost": inventory,
        "robust_recourse_cost": service.robust_recourse_cost,
        "budget_used": budget_used,
        "reporting_tiebreak_diagnostic": reporting_diagnostic,
        "initial_active_depots": [instance.depot_ids[i] for i, active in enumerate(y0) if active],
    }
    missing = [field for field in RESULT_FIELDS if field not in result]
    if missing:
        raise RuntimeError(f"internal result schema omission: {','.join(missing)}")
    artifact = build_first_stage_solution_artifact(
        instance, x0, solved.solution,
        case_id=condition.case_id,
        mode="SERVICE_CALIBRATION_PRB",
        identity={"config_hash": config_hash, "data_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"], "git_commit": git_commit()},
        solver_profile=config["solver_profile"],
    )
    scenarios = [
        {
            "shock_set": scenario.shock_set,
            "recourse_cost": scenario.recourse_cost,
            "transportation_cost": scenario.transportation_cost,
            "shortage_cost": scenario.shortage_cost,
            "service_penalty_cost": scenario.service_penalty_cost,
            "total_shortage": scenario.total_shortage,
            "minimum_fill_rate": scenario.minimum_fill_rate,
            "average_fill_rate": scenario.average_fill_rate,
            "worst_region_id": scenario.worst_region_id,
        }
        for scenario in service.scenarios
    ]
    return result, artifact, scenarios


def write_result(result: dict, artifact: dict, scenarios: list[dict], output_root: Path) -> None:
    target = output_root / "physical_results" / result["condition_id"]
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {result['condition_id']}")
    temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
    temporary.mkdir(parents=True)
    try:
        result_path = temporary / "result.json"
        solution_path = temporary / "first_stage_solution.json"
        service_path = temporary / "service_scenarios.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_first_stage_solution_artifact(solution_path, artifact)
        service_path.write_text(json.dumps(scenarios, indent=2) + "\n", encoding="utf-8")
        provenance = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit(),
            "result_sha256": file_sha256(result_path),
            "first_stage_solution_sha256": file_sha256(solution_path),
            "service_scenarios_sha256": file_sha256(service_path),
        }
        (temporary / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded service calibration robustness runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", metavar="CONDITION_ID")
    mode.add_argument("--execute-all", action="store_true")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    validate_config(config)
    if args.dry_run:
        print(json.dumps(dry_run_plan(config), indent=2))
        return
    validate_execution_gate(config)
    output_root = args.output_root or ROOT / config["output_directory"]
    conditions = enumerate_conditions()
    if args.execute:
        condition = _condition_map().get(args.execute)
        if condition is None:
            raise ValueError("--execute requires one of the 40 physical condition IDs")
        conditions = [condition]
    for condition in conditions:
        result, artifact, scenarios = solve_condition(condition, config)
        write_result(result, artifact, scenarios, output_root)


if __name__ == "__main__":
    main()
