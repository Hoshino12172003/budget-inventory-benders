from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service_detailed
from robust_inventory_reconfiguration.service_calibration import (
    GAMMA,
    LAMBDA_R,
    calibrated_instance,
    canonical_hash,
    enumerate_conditions,
    load_config,
)


CONFIG = ROOT / "experiments/configs/formal/service_calibration_robustness_formal.yaml"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one service-calibration condition and audit fixed-recourse infeasibility."
    )
    parser.add_argument("--condition-id", required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    conditions = {row.physical_result_id: row for row in enumerate_conditions()}
    if args.condition_id not in conditions:
        raise ValueError("condition-id is not a formal OFAT physical condition")
    condition = conditions[args.condition_id]
    output_dir = args.output_dir or (
        ROOT / "artifacts/service_calibration_diagnostics" / condition.physical_result_id
    )
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite diagnostic directory: {output_dir}")
    output_dir.mkdir(parents=True)

    config = load_config(CONFIG)
    base_instance = load_instance(
        ROOT / f"data/formal_instances_v2/{condition.case_id}.json"
    )
    instance = calibrated_instance(
        base_instance,
        service_level=condition.service_level,
        phi_multiplier=condition.phi_multiplier,
    )
    x0_payload = json.loads(
        (ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case_id}.json").read_text(
            encoding="utf-8"
        )
    )
    x0 = x0_payload["x0"]
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
        raise RuntimeError("diagnostic primary optimization is not exactly certified")

    x = solved.solution.x
    fixed_cost = sum(
        instance.fixed_depot_cost[i] * solved.solution.y[i]
        for i in range(instance.num_depots)
    )
    inventory_cost = sum(
        instance.inventory_cost[i][j] * x[i][j]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    budget_used = fixed_cost + inventory_cost + solved.solution.reconfiguration_cost
    negative_entries = [
        {
            "depot_index": i,
            "depot_id": instance.depot_ids[i],
            "product_index": j,
            "product_id": instance.product_ids[j],
            "value": x[i][j],
        }
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
        if x[i][j] < 0
    ]
    capacity_residuals = [
        sum(instance.product_volume[j] * x[i][j] for j in range(instance.num_products))
        - instance.capacity[i] * solved.solution.y[i]
        for i in range(instance.num_depots)
    ]
    upper_bound_residuals = [
        x[i][j] - instance.inventory_upper_bound[i][j] * solved.solution.y[i]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    ]
    primary = {
        "condition_id": condition.physical_result_id,
        "case_id": condition.case_id,
        "run_type": condition.run_type,
        "Gamma": GAMMA,
        "beta": config["fixed_parameters"]["beta"],
        "lambda_R": LAMBDA_R,
        "SL_runner": condition.service_level,
        "SL_optimizer": instance.service_level,
        "SL_evaluator": instance.service_level,
        "phi_multiplier_runner": condition.phi_multiplier,
        "phi_vector_optimizer": instance.service_penalty,
        "phi_vector_evaluator": instance.service_penalty,
        "phi_vector_hash_optimizer": canonical_hash(instance.service_penalty),
        "phi_vector_hash_evaluator": canonical_hash(instance.service_penalty),
        "primary_status": solved.status,
        "exact_certification_pass": solved.exact_certification_pass,
        "objective": solved.solution.objective,
        "lower_bound": solved.final_lower_bound,
        "upper_bound": solved.final_upper_bound,
        "relative_gap": solved.final_relative_gap,
        "iterations": len(solved.iterations),
        "cuts": solved.unique_product_cuts,
        "first_stage_solution_generated": True,
        "minimum_x": min(map(min, x)),
        "negative_inventory_entries": negative_entries,
        "maximum_capacity_residual": max(capacity_residuals),
        "maximum_upper_bound_residual": max(upper_bound_residuals),
        "budget": budget,
        "budget_used": budget_used,
        "budget_residual": budget_used - budget,
        "classification_marker": "PRIMARY_OPTIMIZATION_SUCCESS_POST_EVALUATION_FAILURE",
    }
    _write_json(output_dir / "primary_diagnostic.json", primary)
    _write_json(
        output_dir / "fixed_inventory.json",
        {
            "depot_ids": instance.depot_ids,
            "product_ids": instance.product_ids,
            "x": x,
        },
    )

    iis_path = output_dir / "service_calibration_fixed_recourse_iis.ilp"
    raw_status = "OPTIMAL"
    try:
        evaluate_robust_service_detailed(
            instance,
            x,
            GAMMA,
            optimality_tolerance=config["solver_tolerances"]["cut_violation"],
            infeasibility_iis_path=iis_path,
            preserve_solver_noise_for_diagnostic=True,
        )
    except RuntimeError as error:
        raw_status = str(error)
        if raw_status != "Fixed-inventory recourse evaluation failed: 3":
            raise
    if raw_status == "OPTIMAL":
        raise RuntimeError("diagnostic did not reproduce fixed-recourse infeasibility")

    repaired = evaluate_robust_service_detailed(
        instance,
        x,
        GAMMA,
        optimality_tolerance=config["solver_tolerances"]["cut_violation"],
    )
    _write_json(
        output_dir / "fixed_recourse_diagnostic.json",
        {
            "raw_fixed_inventory_status": raw_status,
            "iis_path": str(iis_path) if iis_path.exists() else None,
            "canonicalized_fixed_inventory_status": "OPTIMAL",
            "scenario_count": repaired.scenario_count,
            "robust_recourse_cost": repaired.robust_recourse_cost,
            "worst_service_scenario": {
                "shock_set": repaired.worst_service_scenario.shock_set,
                "minimum_fill_rate": repaired.worst_service_scenario.minimum_fill_rate,
                "average_fill_rate": repaired.worst_service_scenario.average_fill_rate,
                "worst_region_id": repaired.worst_service_scenario.worst_region_id,
            },
        },
    )
    print(json.dumps({"primary": primary, "raw_evaluator_status": raw_status,
                      "fixed_evaluator_status": "OPTIMAL", "output_dir": str(output_dir)}, indent=2))


if __name__ == "__main__":
    main()
