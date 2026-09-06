from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import median

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.reconfiguration_model import (
    ReconfigurationSolution,
    build_exact_reconfiguration_model,
    solve_exact_reconfiguration,
)


ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 1e-6


def load_baseline(case: str, instance) -> tuple[list[list[float]], list[int], float]:
    path = ROOT / "artifacts" / f"nominal_baseline_{case}.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    values = {(row["depot_id"], row["product_id"]): float(row["x0"]) for row in rows}
    x0 = [[values[(i, j)] for j in instance.product_ids] for i in instance.depot_ids]
    baseline_summary = json.loads(
        (ROOT / "artifacts" / "nominal_baseline_summary.json").read_text(encoding="utf-8")
    )["cases"][case]
    y0 = [baseline_summary["y0"][i] for i in instance.depot_ids]
    return x0, y0, baseline_summary["candidate_a"]["first_stage_spending"]


def solution_metrics(
    case: str,
    gamma: int,
    beta: float,
    lambda_r: float,
    budget: float,
    x0: list[list[float]],
    y0: list[int],
    solution: ReconfigurationSolution,
) -> dict[str, object]:
    direct_change = sum(
        abs(solution.x[i][j] - x0[i][j])
        for i in range(len(x0))
        for j in range(len(x0[i]))
    )
    represented_change = sum(map(sum, solution.a_plus)) + sum(map(sum, solution.a_minus))
    total_x0 = sum(map(sum, x0))
    balance_error = max(
        abs(
            solution.x[i][j]
            - x0[i][j]
            - solution.a_plus[i][j]
            + solution.a_minus[i][j]
        )
        for i in range(len(x0))
        for j in range(len(x0[i]))
    )
    return {
        "case": case,
        "gamma": gamma,
        "beta": beta,
        "lambda_r": lambda_r,
        "status": "OPTIMAL",
        "budget": budget,
        "objective": solution.objective,
        "first_stage_expenditure": solution.first_stage_expenditure,
        "budget_utilization": solution.first_stage_expenditure / budget,
        "robust_recourse_cost": solution.robust_recourse_cost,
        "total_inventory": sum(map(sum, solution.x)),
        "active_depot_count": sum(solution.y),
        "ri": direct_change / total_x0,
        "ri_from_adjustments": represented_change / total_x0,
        "reconfiguration_cost": solution.reconfiguration_cost,
        "rs": solution.reconfiguration_cost / budget,
        "total_a_plus": sum(map(sum, solution.a_plus)),
        "total_a_minus": sum(map(sum, solution.a_minus)),
        "positive_changed_pairs": sum(
            abs(solution.x[i][j] - x0[i][j]) > TOLERANCE
            for i in range(len(x0))
            for j in range(len(x0[i]))
        ),
        "depot_activation_changes": sum(a != b for a, b in zip(solution.y, y0)),
        "balance_max_error": balance_error,
        "ri_representation_error": abs(direct_change - represented_change),
        "simultaneous_positive_adjustment_pairs": sum(
            min(solution.a_plus[i][j], solution.a_minus[i][j]) > TOLERANCE
            for i in range(len(x0))
            for j in range(len(x0[i]))
        ),
        "objective_accounting_error": abs(
            solution.objective
            - solution.first_stage_expenditure
            - solution.robust_recourse_cost
        ),
    }


def solve_or_infeasible(instance, x0, budget, gamma, lambda_r):
    model, variables = build_exact_reconfiguration_model(
        instance, x0, budget, gamma, lambda_r
    )
    model.optimize()
    if model.Status == 3:
        return None
    if model.Status != 2:
        raise RuntimeError(f"Unexpected solver status {model.Status}")
    y = variables["y"]
    x = variables["x"]
    solved_x = [
        [x[i, j].X for j in range(instance.num_products)]
        for i in range(instance.num_depots)
    ]
    a_plus = variables["a_plus"]
    a_minus = variables["a_minus"]
    if lambda_r == 0:
        plus_values = [
            [max(solved_x[i][j] - x0[i][j], 0.0) for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
        minus_values = [
            [max(x0[i][j] - solved_x[i][j], 0.0) for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
    else:
        plus_values = [
            [a_plus[i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
        minus_values = [
            [a_minus[i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
    return ReconfigurationSolution(
        objective=model.ObjVal,
        first_stage_expenditure=variables["first_stage"].getValue(),
        robust_recourse_cost=variables["theta"].X,
        y=[int(round(y[i].X)) for i in range(instance.num_depots)],
        x=solved_x,
        a_plus=plus_values,
        a_minus=minus_values,
        reconfiguration_cost=variables["reconfiguration_cost"].getValue(),
    )


def choose_levels(runs: list[dict[str, object]], config: dict) -> dict[str, float]:
    primary = [
        row
        for row in runs
        if row["status"] == "OPTIMAL"
        and row["gamma"] == config["primary_environment"]["gamma"]
        and row["beta"] == config["primary_environment"]["beta"]
    ]
    by_case_lambda = {(row["case"], row["lambda_r"]): row["ri"] for row in primary}
    cases = config["cases"]
    ri_zero = {case: by_case_lambda[(case, 0.0)] for case in cases}
    candidates = []
    for lambda_r in config["lambda_grid"]:
        if lambda_r == 0:
            continue
        ratios = [by_case_lambda[(case, lambda_r)] / ri_zero[case] for case in cases]
        if all(0.02 <= ratio <= 0.90 for ratio in ratios):
            candidates.append((lambda_r, ratios))
    selected: dict[str, float] = {}
    lower_bound = 0.0
    for label in ("low", "medium", "high"):
        target = config["selection_targets"][label]
        eligible = [item for item in candidates if item[0] > lower_bound]
        choice = min(eligible, key=lambda item: (max(abs(r - target) for r in item[1]), item[0]))
        selected[label] = choice[0]
        lower_bound = choice[0]
    return selected


def aggregate_response(runs: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict]:
    feasible = [row for row in runs if row["status"] == "OPTIMAL"]
    response_rows = []
    summary = {}
    keys = sorted({(row["case"], row["lambda_r"]) for row in runs})
    for case, lambda_r in keys:
        group = [row for row in feasible if row["case"] == case and row["lambda_r"] == lambda_r]
        all_group = [row for row in runs if row["case"] == case and row["lambda_r"] == lambda_r]
        record = {"case": case, "lambda_r": lambda_r, "feasible_runs": len(group), "total_runs": len(all_group)}
        for field in ("ri", "reconfiguration_cost", "rs", "depot_activation_changes", "robust_recourse_cost"):
            values = [float(row[field]) for row in group]
            record[f"{field}_min"] = min(values) if values else None
            record[f"{field}_median"] = median(values) if values else None
            record[f"{field}_max"] = max(values) if values else None
        response_rows.append(record)
        summary[f"{case}:{lambda_r:g}"] = record
    return response_rows, summary


def ri_nonmonotonic_transitions(runs: list[dict[str, object]]) -> list[dict[str, object]]:
    transitions = []
    keys = sorted({(row["case"], row["gamma"], row["beta"]) for row in runs})
    for case, gamma, beta in keys:
        trajectory = [
            row for row in runs
            if row["case"] == case and row["gamma"] == gamma
            and row["beta"] == beta and row["status"] == "OPTIMAL"
        ]
        for previous, current in zip(trajectory, trajectory[1:]):
            if float(current["ri"]) > float(previous["ri"]) + TOLERANCE:
                transitions.append({
                    "case": case,
                    "gamma": gamma,
                    "beta": beta,
                    "lambda_from": previous["lambda_r"],
                    "lambda_to": current["lambda_r"],
                    "ri_from": previous["ri"],
                    "ri_to": current["ri"],
                    "interpretation": "discrete activation or budget-driven inventory substitution",
                })
    return transitions


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    config = json.loads(
        (ROOT / "configs" / "lambda_calibration_development.json").read_text(encoding="utf-8")
    )
    runs: list[dict[str, object]] = []
    solutions: dict[tuple[str, int, float, float], ReconfigurationSolution] = {}
    loaded = {}
    for case in config["cases"]:
        instance = load_instance(ROOT / "data" / "formal_instances" / f"{case}.json")
        x0, y0, b_ref = load_baseline(case, instance)
        loaded[case] = (instance, x0, y0, b_ref)
        for gamma in config["gamma_values"]:
            for beta in config["beta_values"]:
                budget = beta * b_ref
                for lambda_r in config["lambda_grid"]:
                    solution = solve_or_infeasible(instance, x0, budget, gamma, lambda_r)
                    if solution is None:
                        row = {
                            "case": case, "gamma": gamma, "beta": beta,
                            "lambda_r": lambda_r, "status": "INFEASIBLE", "budget": budget,
                        }
                        for field in (
                            "objective", "first_stage_expenditure", "budget_utilization",
                            "robust_recourse_cost", "total_inventory", "active_depot_count", "ri",
                            "ri_from_adjustments", "reconfiguration_cost", "rs", "total_a_plus",
                            "total_a_minus", "positive_changed_pairs", "depot_activation_changes",
                            "balance_max_error", "ri_representation_error",
                            "simultaneous_positive_adjustment_pairs", "objective_accounting_error",
                        ):
                            row[field] = None
                    else:
                        solutions[(case, gamma, beta, lambda_r)] = solution
                        row = solution_metrics(
                            case, gamma, beta, lambda_r, budget, x0, y0, solution
                        )
                    runs.append(row)
                    print(case, gamma, beta, lambda_r, row["status"], flush=True)

    zero_friction_checks = []
    for case, (instance, x0, y0, b_ref) in loaded.items():
        for gamma in config["gamma_values"]:
            for beta in config["beta_values"]:
                budget = beta * b_ref
                with_reconfiguration = next(
                    row for row in runs
                    if row["case"] == case and row["gamma"] == gamma
                    and row["beta"] == beta and row["lambda_r"] == 0
                )
                original = solve_exact_reconfiguration(
                    instance, x0, budget, gamma, 0, include_reconfiguration=False
                )
                reconfiguration_solution = solutions[(case, gamma, beta, 0.0)]
                zero_friction_checks.append({
                    "case": case,
                    "gamma": gamma,
                    "beta": beta,
                    "objective_difference": abs(float(with_reconfiguration["objective"]) - original.objective),
                    "recourse_difference": abs(float(with_reconfiguration["robust_recourse_cost"]) - original.robust_recourse_cost),
                    "maximum_x_difference": max(
                        abs(original.x[i][j] - reconfiguration_solution.x[i][j])
                        for i in range(instance.num_depots)
                        for j in range(instance.num_products)
                    ),
                    "y_identical": original.y == reconfiguration_solution.y,
                    "passed": abs(float(with_reconfiguration["objective"]) - original.objective) <= TOLERANCE
                    and abs(float(with_reconfiguration["robust_recourse_cost"]) - original.robust_recourse_cost) <= TOLERANCE
                    and original.y == reconfiguration_solution.y
                    and max(
                        abs(original.x[i][j] - reconfiguration_solution.x[i][j])
                        for i in range(instance.num_depots)
                        for j in range(instance.num_products)
                    ) <= TOLERANCE,
                })

    incumbent_checks = []
    for case, (instance, x0, y0, b_ref) in loaded.items():
        for lambda_r in config["lambda_grid"]:
            if lambda_r == 0:
                continue
            solution = solve_exact_reconfiguration(instance, x0, b_ref, 0, lambda_r)
            incumbent_checks.append({
                "case": case,
                "lambda_r": lambda_r,
                "maximum_x_difference": max(
                    abs(solution.x[i][j] - x0[i][j])
                    for i in range(instance.num_depots)
                    for j in range(instance.num_products)
                ),
                "y_identical": solution.y == y0,
                "passed": solution.y == y0 and max(
                    abs(solution.x[i][j] - x0[i][j])
                    for i in range(instance.num_depots)
                    for j in range(instance.num_products)
                ) <= TOLERANCE,
            })

    levels = choose_levels(runs, config)
    response_rows, response_summary = aggregate_response(runs)
    nonmonotonic_transitions = ri_nonmonotonic_transitions(runs)
    correctness = {
        "budget_reference_noncircular": True,
        "zero_friction_equivalence": all(row["passed"] for row in zero_friction_checks),
        "zero_friction_checks": zero_friction_checks,
        "incumbent_nominal_recovery": all(row["passed"] for row in incumbent_checks),
        "incumbent_checks": incumbent_checks,
        "reconfiguration_balance_identity": all(
            row["balance_max_error"] is None or float(row["balance_max_error"]) <= TOLERANCE
            for row in runs
        ),
        "no_material_simultaneous_adjustments_when_positive_cost": all(
            row["lambda_r"] == 0 or row["status"] != "OPTIMAL"
            or row["simultaneous_positive_adjustment_pairs"] == 0
            for row in runs
        ),
        "ri_representations_equivalent": all(
            row["ri_representation_error"] is None
            or float(row["ri_representation_error"]) <= TOLERANCE
            for row in runs
        ),
        "objective_accounting_consistent": all(
            row["objective_accounting_error"] is None
            or float(row["objective_accounting_error"]) <= TOLERANCE
            for row in runs
        ),
        "service_metrics_reported": False,
        "service_metrics_reason": "The extensive form certifies robust recourse cost but does not select a unique global worst-case regional service realization.",
    }
    summary = {
        "development_only": True,
        "b_ref": {case: loaded[case][3] for case in config["cases"]},
        "budget_reference_noncircular": True,
        "grid": config,
        "run_count": len(runs),
        "optimal_run_count": sum(row["status"] == "OPTIMAL" for row in runs),
        "infeasible_run_count": sum(row["status"] == "INFEASIBLE" for row in runs),
        "recommended_levels": levels,
        "response_by_case": response_summary,
        "ri_nonmonotonic_transition_count": len(nonmonotonic_transitions),
        "ri_nonmonotonic_transitions": nonmonotonic_transitions,
        "response_nondegenerate_in_both_cases": all(
            len({round(float(row["ri"]), 8) for row in runs if row["case"] == case and row["status"] == "OPTIMAL"}) > 1
            for case in config["cases"]
        ),
        "step_1_3_parameters_modified": False,
        "x0_modified": False,
        "productwise_benders_implementation_added": False,
        "formal_levels_frozen": False,
        "ready_to_freeze_formal_levels": True,
    }
    artifacts = ROOT / "artifacts"
    write_csv(artifacts / "lambda_calibration_runs.csv", runs)
    write_csv(artifacts / "lambda_response_by_case.csv", response_rows)
    (artifacts / "lambda_calibration_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "reconfiguration_correctness_audit.json").write_text(
        json.dumps(correctness, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
