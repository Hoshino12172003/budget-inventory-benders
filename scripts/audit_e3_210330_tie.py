from __future__ import annotations

import json
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from robust_inventory_reconfiguration.first_stage_solution import (
    load_first_stage_solution_artifact,
    matrix_from_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service_detailed


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "experiments/results/e3_budget_sensitivity_v1"
OUTPUT = ROOT / "artifacts/e3_210330_b110_b120_tie_audit.json"
CASE = "210330"
TOLERANCE = 1e-6


def matrix_comparison(left, right, instance) -> dict:
    differences = [
        (abs(left[i][j] - right[i][j]), instance.depot_ids[i], instance.product_ids[j], left[i][j], right[i][j])
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    ]
    differences.sort(reverse=True)
    largest = differences[0]
    return {
        "max_absolute_difference": largest[0],
        "l1_difference": sum(value[0] for value in differences),
        "coordinates_differing_above_1e-6": sum(value[0] > TOLERANCE for value in differences),
        "largest_difference_coordinate": {
            "depot": largest[1], "product": largest[2], "B110": largest[3], "B120": largest[4],
        },
    }


def scenario_payload(scenario, instance) -> dict:
    allocation = {product: 0 for product in instance.product_ids}
    for _, product in scenario.shock_set:
        allocation[product] += 1
    return {
        "shock_set": [list(item) for item in scenario.shock_set],
        "product_gamma_allocation": allocation,
        "recourse_cost": scenario.recourse_cost,
        "transport_cost": scenario.transportation_cost,
        "shortage_cost": scenario.shortage_cost,
        "service_penalty_cost": scenario.service_penalty_cost,
        "total_shortage": scenario.total_shortage,
        "minimum_fill_rate": scenario.minimum_fill_rate,
        "average_fill_rate": scenario.average_fill_rate,
        "worst_region": scenario.worst_region_id,
    }


def selected_reporting_scenario(result: dict, tied: list) -> dict:
    matches = [
        scenario for scenario in tied
        if abs(scenario.shortage_cost - result["worst_recourse_shortage_cost"]) <= TOLERANCE
        and abs(scenario.service_penalty_cost - result["worst_recourse_service_penalty_cost"]) <= TOLERANCE
        and abs(scenario.total_shortage - result["worst_recourse_total_shortage"]) <= TOLERANCE
    ]
    if len(matches) != 1:
        raise RuntimeError("unable to identify stored E3 reporting scenario")
    return matches[0]


def main() -> None:
    instance = load_instance(ROOT / f"data/formal_instances_v2/{CASE}.json")
    results = {}
    artifacts = {}
    matrices = {}
    evaluations = {}
    tied = {}
    selected = {}
    for code in ("B110", "B120"):
        directory = RESULT_ROOT / f"E3-{CASE}-{code}"
        results[code] = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        artifacts[code] = load_first_stage_solution_artifact(directory / "first_stage_solution.json", instance)
        matrices[code] = {
            field: matrix_from_artifact(artifacts[code], instance, field)
            for field in ("x", "a_plus", "a_minus")
        }
        evaluations[code] = evaluate_robust_service_detailed(instance, matrices[code]["x"], 2)
        maximum = evaluations[code].robust_recourse_cost
        tied[code] = [scenario for scenario in evaluations[code].scenarios if abs(scenario.recourse_cost - maximum) <= TOLERANCE]
        selected[code] = selected_reporting_scenario(results[code], tied[code])

    comparisons = {
        field: matrix_comparison(matrices["B110"][field], matrices["B120"][field], instance)
        for field in ("x", "a_plus", "a_minus")
    }
    y110 = [entry["value"] for entry in artifacts["B110"]["y"]]
    y120 = [entry["value"] for entry in artifacts["B120"]["y"]]
    component_differences = {
        key: results["B120"][key] - results["B110"][key]
        for key in ("objective", "fixed_cost", "inventory_cost", "reconfiguration_cost", "robust_recourse_cost", "budget_used")
    }
    first_stage_same = y110 == y120 and all(
        comparison["max_absolute_difference"] <= TOLERANCE for comparison in comparisons.values()
    )
    reporting_scenarios_differ = selected["B110"].shock_set != selected["B120"].shock_set
    multiple_worst_scenarios = all(len(tied[code]) > 1 for code in ("B110", "B120"))
    recourse_same = abs(evaluations["B110"].robust_recourse_cost - evaluations["B120"].robust_recourse_cost) <= TOLERANCE
    if first_stage_same and reporting_scenarios_differ and multiple_worst_scenarios and recourse_same:
        classification = "REPORTING_SCENARIO_SELECTION_TIE"
    else:
        classification = "TRUE_E3_RESULT_INCONSISTENCY"
    payload = {
        "status": "PASS" if classification != "TRUE_E3_RESULT_INCONSISTENCY" else "BLOCK_E3_RESULT_CORRECTNESS",
        "classification": classification,
        "tolerance": TOLERANCE,
        "first_stage": {
            "y_identical": y110 == y120,
            "x": comparisons["x"], "a_plus": comparisons["a_plus"], "a_minus": comparisons["a_minus"],
            "artifact_byte_identical": (RESULT_ROOT / f"E3-{CASE}-B110/first_stage_solution.json").read_bytes()
            == (RESULT_ROOT / f"E3-{CASE}-B120/first_stage_solution.json").read_bytes(),
        },
        "component_differences_B120_minus_B110": component_differences,
        "fixed_first_stage_recomputation": {
            code: {
                "exact_robust_recourse": evaluations[code].robust_recourse_cost,
                "tied_worst_recourse_scenario_count": len(tied[code]),
                "tied_worst_recourse_scenarios": [scenario_payload(value, instance) for value in tied[code]],
                "stored_reporting_scenario": scenario_payload(selected[code], instance),
            }
            for code in ("B110", "B120")
        },
        "objective_validity_affected": False,
        "feasibility_affected": False,
        "budget_conclusion_affected": False,
        "paper_interpretation_constraint": "Do not interpret the stored total-shortage difference between B110 and B120 as service deterioration; it is a reporting choice between economically tied worst-recourse scenarios.",
        "new_first_stage_optimization_solves": 0,
        "fixed_first_stage_reporting_recomputations": 2,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(classification)
    if classification == "TRUE_E3_RESULT_INCONSISTENCY":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
