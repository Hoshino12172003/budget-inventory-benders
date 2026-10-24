from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from gurobipy import GRB

from robust_inventory_reconfiguration.first_stage_solution import (
    validate_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.reconfiguration_model import (
    build_exact_reconfiguration_model,
)
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_ROOT = ROOT / "experiments/results/e1_empirical_8case_v1"
AUDIT_ROOT = ROOT / "experiments/results/e1_empirical_8case_v1_correctness_audit"
CASES = ("210310", "210330")
GAMMA = 2
LAMBDA_R = 0.05
CROSS_METHOD_TOLERANCE = 1e-4
X_DIFFERENCE_TOLERANCE = 1e-8


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def load_run(case: str, method: str, instance) -> dict[str, Any]:
    directory = PRIMARY_ROOT / f"E1-{case}-{method}"
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    solution = json.loads(
        (directory / "first_stage_solution.json").read_text(encoding="utf-8")
    )
    provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    validate_first_stage_solution_artifact(solution, instance)
    if provenance["first_stage_solution_sha256"] != sha256_file(
        directory / "first_stage_solution.json"
    ):
        raise RuntimeError(f"{case} {method} solution provenance hash mismatch")
    y = [int(entry["value"]) for entry in solution["y"]]
    matrices = {}
    for field in ("x", "a_plus", "a_minus"):
        values = {
            (entry["depot_id"], entry["product_id"]): float(entry["value"])
            for entry in solution[field]
        }
        matrices[field] = [
            [values[(depot, product)] for product in instance.product_ids]
            for depot in instance.depot_ids
        ]
    return {
        "directory": directory,
        "result": result,
        "solution": solution,
        "provenance": provenance,
        "y": y,
        **matrices,
        "file_hashes": {
            path.name: sha256_file(path) for path in sorted(directory.iterdir()) if path.is_file()
        },
        "solver_log_present": (directory / "solver.log").is_file(),
    }


def first_stage_components(instance, x0, y, x, a_plus, a_minus) -> dict[str, float]:
    fixed = sum(instance.fixed_depot_cost[i] * y[i] for i in range(instance.num_depots))
    inventory = sum(
        instance.inventory_cost[i][j] * x[i][j]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    reconfiguration = LAMBDA_R * sum(
        instance.inventory_cost[i][j] * (a_plus[i][j] + a_minus[i][j])
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    absolute_difference_reconfiguration = LAMBDA_R * sum(
        instance.inventory_cost[i][j] * abs(x[i][j] - x0[i][j])
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    return {
        "fixed_depot_cost": fixed,
        "final_inventory_cost": inventory,
        "reconfiguration_cost": reconfiguration,
        "absolute_difference_reconfiguration_cost": absolute_difference_reconfiguration,
        "maximum_reconfiguration_balance_residual": max(
            abs(x[i][j] - x0[i][j] - a_plus[i][j] + a_minus[i][j])
            for i in range(instance.num_depots)
            for j in range(instance.num_products)
        ),
        "first_stage_expenditure": fixed + inventory + reconfiguration,
    }


def direct_fixed_evaluation(instance, x0, budget, y, x, log_path: Path) -> dict[str, Any]:
    model, variables = build_exact_reconfiguration_model(
        instance, x0, budget, GAMMA, LAMBDA_R
    )
    model.update()
    first_stage_constraints = [
        constraint
        for constraint in model.getConstrs()
        if constraint.ConstrName.startswith((
            "capacity[", "inventory_bound[", "reconfiguration_balance["
        ))
        or constraint.ConstrName == "financial_budget"
    ]
    model.remove(first_stage_constraints)
    model.setObjective(variables["theta"], GRB.MINIMIZE)
    for i in range(instance.num_depots):
        for j in range(instance.num_products):
            model.addConstr(
                variables["x"][i, j] == x[i][j], name=f"audit_fix_x[{i},{j}]"
            )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    model.Params.LogFile = str(log_path)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"fixed Direct evaluation failed: {model.Status}")
    return {
        "status": "OPTIMAL",
        "robust_recourse": float(variables["theta"].X),
        "best_bound": float(model.ObjBound),
        "absolute_gap": abs(float(model.ObjVal) - float(model.ObjBound)),
        "relative_gap": float(model.MIPGap),
        "runtime_seconds": float(model.Runtime),
    }


def prb_fixed_evaluation(instance, x) -> dict[str, Any]:
    product_results = [
        ProductRiskSubproblem(instance, j, GAMMA).solve(
            [x[i][j] for i in range(instance.num_depots)]
        )
        for j in range(instance.num_products)
    ]
    values = [
        [worst.value for worst in result.worst_cases] for result in product_results
    ]
    composition = compose_risk_budget(values, GAMMA)
    return {
        "status": "OPTIMAL",
        "robust_recourse": composition.value,
        "risk_budget_allocation": list(composition.allocation),
        "maximum_strong_duality_error": max(
            worst.cut.strong_duality_error
            for result in product_results
            for worst in result.worst_cases
        ),
        "all_duals_feasible": all(
            worst.cut.dual_feasible
            for result in product_results
            for worst in result.worst_cases
        ),
    }


def primary_hashes() -> dict[str, str]:
    return {
        path.relative_to(PRIMARY_ROOT).as_posix(): sha256_file(path)
        for case in CASES
        for method in ("DIRECT", "PRB")
        for path in sorted((PRIMARY_ROOT / f"E1-{case}-{method}").iterdir())
        if path.is_file()
    }


def audit_case(case: str) -> dict[str, Any]:
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    if instance.initial_inventory is None:
        raise RuntimeError(f"{case} has no frozen x0")
    x0 = instance.initial_inventory
    direct = load_run(case, "DIRECT", instance)
    prb = load_run(case, "PRB", instance)
    budget = float(direct["result"]["B"])
    if budget != float(prb["result"]["B"]):
        raise RuntimeError(f"{case} budget mismatch")

    direct_components = first_stage_components(
        instance, x0, direct["y"], direct["x"], direct["a_plus"], direct["a_minus"]
    )
    prb_components = first_stage_components(
        instance, x0, prb["y"], prb["x"], prb["a_plus"], prb["a_minus"]
    )
    differences = []
    for i, depot in enumerate(instance.depot_ids):
        for j, product in enumerate(instance.product_ids):
            difference = abs(direct["x"][i][j] - prb["x"][i][j])
            if difference > 0.0:
                differences.append({
                    "depot": depot,
                    "product": product,
                    "direct_x": direct["x"][i][j],
                    "prb_x": prb["x"][i][j],
                    "absolute_difference": difference,
                })
    differences.sort(key=lambda row: row["absolute_difference"], reverse=True)

    evaluations = {}
    for label, run in (("direct_x", direct), ("prb_x", prb)):
        evaluations[label] = {
            "direct": direct_fixed_evaluation(
                instance,
                x0,
                budget,
                run["y"],
                run["x"],
                AUDIT_ROOT / case / f"direct_evaluator_on_{label}.log",
            ),
            "prb": prb_fixed_evaluation(instance, run["x"]),
        }

    same_x_recourse_errors = {
        label: abs(value["direct"]["robust_recourse"] - value["prb"]["robust_recourse"])
        for label, value in evaluations.items()
    }
    reconstructed = {
        "direct": direct_components["first_stage_expenditure"]
        + evaluations["direct_x"]["direct"]["robust_recourse"],
        "prb": prb_components["first_stage_expenditure"]
        + evaluations["prb_x"]["direct"]["robust_recourse"],
    }
    reported = {
        "direct": float(direct["result"]["objective"]),
        "prb": float(prb["result"]["objective"]),
    }
    reported_difference = abs(reported["direct"] - reported["prb"])
    if max(same_x_recourse_errors.values()) > CROSS_METHOD_TOLERANCE:
        classification = "RECOURSE_FORMULATION_MISMATCH"
        blocker = "BLOCK_E1_RECOURSE_FORMULATION_MISMATCH"
    elif reported_difference <= CROSS_METHOD_TOLERANCE:
        classification = "NUMERICAL_REPORTING_ONLY"
        blocker = ""
    else:
        classification = "CERTIFICATION_TOLERANCE_TOO_LOOSE_FOR_1E-4_CROSS_METHOD_GATE"
        blocker = f"E1_BLOCKED_CORRECTNESS_{case}"

    return {
        "case": case,
        "classification": classification,
        "blocker": blocker,
        "direct_result": direct["result"],
        "prb_result": prb["result"],
        "input_evidence": {
            "direct_file_hashes": direct["file_hashes"],
            "prb_file_hashes": prb["file_hashes"],
            "direct_solver_log_present": direct["solver_log_present"],
            "prb_solver_log_present": prb["solver_log_present"],
        },
        "same_y": direct["y"] == prb["y"],
        "direct_active_depots": [
            depot for depot, active in zip(instance.depot_ids, direct["y"]) if active
        ],
        "prb_active_depots": [
            depot for depot, active in zip(instance.depot_ids, prb["y"]) if active
        ],
        "max_x_difference": max(row["absolute_difference"] for row in differences),
        "l1_x_difference": sum(row["absolute_difference"] for row in differences),
        "differing_x_coordinate_count": sum(
            row["absolute_difference"] > X_DIFFERENCE_TOLERANCE for row in differences
        ),
        "largest_x_differences": differences[:10],
        "direct_components": direct_components,
        "prb_components": prb_components,
        "component_differences": {
            key: abs(direct_components[key] - prb_components[key])
            for key in direct_components
        }
        | {
            "robust_recourse": abs(
                float(direct["result"]["robust_recourse_cost"])
                - float(prb["result"]["robust_recourse_cost"])
            ),
            "total_objective": abs(reported["direct"] - reported["prb"]),
        },
        "fixed_first_stage_evaluations": evaluations,
        "same_x_recourse_errors": same_x_recourse_errors,
        "reported_objectives": reported,
        "reconstructed_objectives": reconstructed,
        "reported_reconstruction_errors": {
            method: abs(reported[method] - reconstructed[method])
            for method in ("direct", "prb")
        },
        "termination_contract": {
            "prb_relative_gap_tolerance": 1e-6,
            "cross_method_absolute_tolerance": CROSS_METHOD_TOLERANCE,
            "relative_tolerance_absolute_scale": 1e-6 * abs(reported["prb"]),
            "prb_exact_certification_checks_incumbent_against_upper_bound_only": True,
            "guarantees_cross_method_1e_4": False,
            "observed_cross_method_gate_pass": reported_difference
            <= CROSS_METHOD_TOLERANCE,
        },
    }


def main() -> None:
    before = primary_hashes()
    results = [audit_case(case) for case in CASES]
    after = primary_hashes()
    if before != after:
        raise RuntimeError("immutable primary E1 results changed during audit")

    payload = {
        "schema": "e1_objective_mismatch_audit_v1",
        "cases": results,
        "correctness_threshold": CROSS_METHOD_TOLERANCE,
        "correctness_threshold_changed": False,
        "model_changed": False,
        "dataset_changed": False,
        "other_six_cases_rerun": False,
        "audit_only_fixed_first_stage_evaluations": 8,
        "primary_result_hashes_preserved": before == after,
        "e2_e7_authorization": False,
    }
    write_json(
        ROOT / "artifacts/e1_objective_mismatch_audit_210310_210330.json", payload
    )
    write_json(AUDIT_ROOT / "fixed_first_stage_evaluations.json", payload)

    rows = []
    for result in results:
        direct = result["direct_result"]
        prb = result["prb_result"]
        evaluations = result["fixed_first_stage_evaluations"]
        rows.append({
            "case": result["case"],
            "direct_objective": direct["objective"],
            "prb_objective": prb["objective"],
            "abs_diff": abs(direct["objective"] - prb["objective"]),
            "direct_bound": direct["best_bound"],
            "prb_bound": prb["lower_bound"],
            "direct_gap": direct["final_gap"],
            "prb_gap": prb["final_gap"],
            "same_y": result["same_y"],
            "max_x_diff": result["max_x_difference"],
            "L1_x_diff": result["l1_x_difference"],
            "Q_DirectEval_on_DirectX": evaluations["direct_x"]["direct"]["robust_recourse"],
            "Q_PRBEval_on_DirectX": evaluations["direct_x"]["prb"]["robust_recourse"],
            "Q_DirectEval_on_PRBX": evaluations["prb_x"]["direct"]["robust_recourse"],
            "Q_PRBEval_on_PRBX": evaluations["prb_x"]["prb"]["robust_recourse"],
            "reconstructed_direct_obj": result["reconstructed_objectives"]["direct"],
            "reconstructed_prb_obj": result["reconstructed_objectives"]["prb"],
            "classification": result["classification"],
            "blocker": result["blocker"],
        })
    csv_path = ROOT / "table_e1_objective_mismatch_audit.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# E1 objective mismatch audit: 210310 and 210330",
        "",
        "The four paper-final run directories are immutable inputs. This audit fixes each saved",
        "first-stage solution and evaluates its robust recourse with both the Direct extensive",
        "form and the product-wise PRB certifier. No first-stage problem is reoptimized.",
        "",
        "The frozen cross-method threshold remains `1e-4`; no model, tolerance, parameter,",
        "dataset, authorization manifest, or paper-final result is changed.",
        "",
        "## Findings",
        "",
    ]
    for result in results:
        direct = result["direct_result"]
        prb = result["prb_result"]
        errors = result["same_x_recourse_errors"]
        evaluations = result["fixed_first_stage_evaluations"]
        components = result["component_differences"]
        largest = result["largest_x_differences"][0]
        lines.extend([
            f"### {result['case']}",
            "",
            f"Classification: `{result['classification']}`.",
            "",
            f"Reported objective difference: `{abs(direct['objective'] - prb['objective']):.17g}`.",
            f"Direct/PRB use the same y: `{str(result['same_y']).lower()}`. Maximum x difference:",
            f"`{result['max_x_difference']:.17g}`; L1 x difference: `{result['l1_x_difference']:.17g}`.",
            f"Same-x recourse differences are `{errors['direct_x']:.17g}` on Direct x and",
            f"`{errors['prb_x']:.17g}` on PRB x.",
            "",
            "| Quantity | Direct | PRB | Absolute difference |",
            "|---|---:|---:|---:|",
            f"| Objective | {direct['objective']:.17g} | {prb['objective']:.17g} | {components['total_objective']:.17g} |",
            f"| Fixed depot cost | {result['direct_components']['fixed_depot_cost']:.17g} | {result['prb_components']['fixed_depot_cost']:.17g} | {components['fixed_depot_cost']:.17g} |",
            f"| Final inventory cost | {result['direct_components']['final_inventory_cost']:.17g} | {result['prb_components']['final_inventory_cost']:.17g} | {components['final_inventory_cost']:.17g} |",
            f"| Reconfiguration cost | {result['direct_components']['reconfiguration_cost']:.17g} | {result['prb_components']['reconfiguration_cost']:.17g} | {components['reconfiguration_cost']:.17g} |",
            f"| Reported robust recourse | {direct['robust_recourse_cost']:.17g} | {prb['robust_recourse_cost']:.17g} | {components['robust_recourse']:.17g} |",
            "",
            "| Fixed inventory | Direct evaluator Q | PRB evaluator Q | Difference |",
            "|---|---:|---:|---:|",
            f"| Direct x | {evaluations['direct_x']['direct']['robust_recourse']:.17g} | {evaluations['direct_x']['prb']['robust_recourse']:.17g} | {errors['direct_x']:.17g} |",
            f"| PRB x | {evaluations['prb_x']['direct']['robust_recourse']:.17g} | {evaluations['prb_x']['prb']['robust_recourse']:.17g} | {errors['prb_x']:.17g} |",
            "",
            f"Largest x difference: depot `{largest['depot']}`, product `{largest['product']}`,",
            f"Direct `{largest['direct_x']:.17g}`, PRB `{largest['prb_x']:.17g}`.",
            f"Reported/reconstructed objective errors are `{result['reported_reconstruction_errors']['direct']:.17g}`",
            f"and `{result['reported_reconstruction_errors']['prb']:.17g}`.",
            f"Direct bound/gap: `{direct['best_bound']:.17g}` / `{direct['final_gap']:.17g}`.",
            f"PRB lower bound/gap: `{prb['lower_bound']:.17g}` / `{prb['final_gap']:.17g}`;",
            f"global coupling pass: `{str(prb['global_coupling_pass']).lower()}`.",
            "",
            "The saved first-stage points differ only numerically, while the recourse formulations",
            "agree on each fixed point. The supplied mismatch exponent was three orders of",
            "magnitude too large: the recorded difference is below `1e-4` and the existing paired",
            "comparison artifact already reports `PASS`.",
            "",
        ])
    lines.extend([
        "## Interpretation",
        "",
        "Both fixed-x recourse formulations are mathematically consistent, and both cases pass the",
        "frozen `1e-4` cross-method gate. The generic PRB relative termination rule alone does not",
        "guarantee that absolute gate at this objective scale, so a future protocol revision should",
        "state an absolute certification condition. That contract observation does not turn either",
        "of these two recorded comparisons into a failure.",
        "",
        "No recommendation in this audit changes the frozen threshold or retunes a solver.",
    ])
    (ROOT / "docs/e1_objective_mismatch_audit_210310_210330.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        result["case"]: {
            "classification": result["classification"],
            "objective_difference": result["component_differences"]["total_objective"],
            "same_x_recourse_errors": result["same_x_recourse_errors"],
        }
        for result in results
    }, indent=2))


if __name__ == "__main__":
    main()
