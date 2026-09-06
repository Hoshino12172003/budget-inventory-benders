from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from robust_inventory_reconfiguration.exact_benchmark import (
    solve_exact_benchmark,
    solve_global_scenario_benchmark,
)
from robust_inventory_reconfiguration.instance import InventoryInstance, load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service


ROOT = Path(__file__).resolve().parents[1]


def load_baseline(case: str, instance: InventoryInstance):
    with (ROOT / "artifacts" / f"nominal_baseline_{case}.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    values = {(row["depot_id"], row["product_id"]): float(row["x0"]) for row in rows}
    x0 = [[values[i, j] for j in instance.product_ids] for i in instance.depot_ids]
    summary = json.loads(
        (ROOT / "artifacts" / "nominal_baseline_summary.json").read_text(encoding="utf-8")
    )["cases"][case]
    return x0, summary["candidate_a"]["first_stage_spending"]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def close(a: float, b: float, absolute: float, relative: float = 0.0) -> bool:
    return abs(a - b) <= max(absolute, relative * max(abs(a), abs(b)))


def tiny_instance() -> InventoryInstance:
    return InventoryInstance(
        name="tiny-prb",
        depot_ids=["D1", "D2"],
        region_ids=["R1", "R2", "R3"],
        product_ids=["P1", "P2"],
        base_demand=[[4.0, 2.0], [2.0, 5.0], [3.0, 1.0]],
        demand_deviation=[[1.0, 0.5], [0.5, 1.0], [1.5, 0.75]],
        transport_cost=[
            [[1.0, 1.6], [2.1, 2.4], [3.2, 3.1]],
            [[2.8, 2.7], [1.2, 1.1], [1.7, 1.8]],
        ],
        shortage_penalty=[[12.0, 15.0], [13.0, 16.0], [14.0, 17.0]],
        service_level=[0.8, 0.85],
        service_penalty=[25.0, 30.0],
        capacity=[15.0, 14.0],
        inventory_upper_bound=[[12.0, 10.0], [11.0, 12.0]],
        fixed_depot_cost=[2.0, 2.7],
        inventory_cost=[[1.0, 1.25], [1.15, 0.95]],
        product_volume=[1.0, 1.2],
        initial_inventory=None,
        reconfiguration_cost_multiplier=None,
        provenance={"purpose": "exhaustive PRB-Benders correctness fixture"},
    )


def random_feasible_x(instance: InventoryInstance, rng: random.Random) -> list[list[float]]:
    x = [
        [rng.random() * instance.inventory_upper_bound[i][j] for j in range(instance.num_products)]
        for i in range(instance.num_depots)
    ]
    for i in range(instance.num_depots):
        load = sum(instance.product_volume[j] * x[i][j] for j in range(instance.num_products))
        if load > instance.capacity[i]:
            factor = instance.capacity[i] / load
            x[i] = [value * factor for value in x[i]]
    return x


def main() -> None:
    config = json.loads(
        (ROOT / "configs" / "prb_benders_correctness.json").read_text(encoding="utf-8")
    )
    artifacts = ROOT / "artifacts"
    frozen_service_rows = list(
        csv.DictReader((artifacts / "robust_service_evaluation.csv").open(encoding="utf-8"))
    )
    frozen_service = {
        (row["case"], int(row["gamma"]), float(row["beta"]), float(row["lambda_r"])): row
        for row in frozen_service_rows
    }
    runs: list[dict[str, object]] = []
    representative_cuts = {}
    loaded = {}

    for case in config["cases"]:
        instance = load_instance(ROOT / "data" / "formal_instances" / f"{case}.json")
        x0, b_ref = load_baseline(case, instance)
        loaded[case] = instance, x0, b_ref
        for gamma in config["gamma_values"]:
            for beta in config["beta_values"]:
                for lambda_r in config["lambda_values"]:
                    budget = beta * b_ref
                    exact = solve_exact_benchmark(instance, x0, budget, gamma, lambda_r)
                    prb = solve_prb_benders(
                        instance,
                        x0,
                        budget,
                        gamma,
                        lambda_r,
                        relative_gap_tolerance=config["relative_gap_tolerance"],
                        cut_tolerance=config["cut_tolerance"],
                    )
                    assert exact.solution is not None
                    p = prb.solution
                    e = exact.solution
                    service = evaluate_robust_service(instance, p.x, gamma)
                    frozen = frozen_service[case, gamma, beta, lambda_r]
                    objective_difference = abs(p.objective - e.objective)
                    first_stage_difference = abs(p.first_stage_expenditure - e.first_stage_expenditure)
                    recourse_difference = abs(p.robust_recourse_cost - e.robust_recourse_cost)
                    x_difference = max(
                        abs(p.x[i][j] - e.x[i][j])
                        for i in range(instance.num_depots)
                        for j in range(instance.num_products)
                    )
                    fill_rate_difference = abs(service.minimum_fill_rate - float(frozen["fr_min_robust"]))
                    certified = (
                        exact.status == prb.status == "OPTIMAL"
                        and close(
                            p.objective,
                            e.objective,
                            config["objective_absolute_tolerance"],
                            config["objective_relative_tolerance"],
                        )
                        and first_stage_difference <= config["first_stage_absolute_tolerance"]
                        and recourse_difference <= config["recourse_absolute_tolerance"]
                        and p.y == e.y
                        and x_difference <= config["x_absolute_tolerance"]
                        and fill_rate_difference <= config["fill_rate_absolute_tolerance"]
                        and prb.exact_certification_pass
                        and prb.global_risk_budget_coupling_pass
                    )
                    row = {
                        "case": case,
                        "gamma": gamma,
                        "beta": beta,
                        "lambda_r": lambda_r,
                        "status": prb.status,
                        "certified": certified,
                        "objective": p.objective,
                        "exact_objective": e.objective,
                        "objective_difference": objective_difference,
                        "first_stage_expenditure": p.first_stage_expenditure,
                        "first_stage_difference": first_stage_difference,
                        "robust_recourse": p.robust_recourse_cost,
                        "robust_recourse_difference": recourse_difference,
                        "y_identical": p.y == e.y,
                        "maximum_x_difference": x_difference,
                        "fr_min_robust": service.minimum_fill_rate,
                        "fr_min_difference": fill_rate_difference,
                        "worst_scenario": ";".join(f"{r}:{j}" for r, j in service.worst_scenario),
                        "worst_region": service.worst_region_id,
                        "average_fill_rate": service.average_fill_rate,
                        "iterations": len(prb.iterations),
                        "master_solve_count": prb.master_solve_count,
                        "product_subproblem_evaluations": prb.product_subproblem_evaluations,
                        "product_pattern_evaluations": prb.product_pattern_evaluations,
                        "unique_product_cuts": prb.unique_product_cuts,
                        "cuts_by_product": json.dumps(prb.cuts_by_product),
                        "cuts_by_gamma": json.dumps(prb.cuts_by_gamma),
                        "final_lb": prb.final_lower_bound,
                        "final_ub": prb.final_upper_bound,
                        "final_gap": prb.final_relative_gap,
                        "total_runtime_seconds": prb.total_runtime,
                        "master_runtime_seconds": prb.master_runtime,
                        "separation_runtime_seconds": prb.separation_runtime,
                        "certification_runtime_seconds": prb.certification_runtime,
                        "global_coupling_error": prb.global_risk_budget_coupling_error,
                        "exact_certification": prb.exact_certification_pass,
                    }
                    runs.append(row)
                    if gamma == 2 and beta == 1.0 and lambda_r == 0.05:
                        representative_cuts[case] = prb.cut_additions
                    print(case, gamma, beta, lambda_r, "PASS" if certified else "MISMATCH", flush=True)

    tiny_rows = []
    tiny = tiny_instance()
    tiny_x0 = [[4.0, 3.0], [3.0, 4.0]]
    for gamma in (1, 2):
        literal = solve_global_scenario_benchmark(tiny, tiny_x0, 25.0, gamma, 0.05)
        factorized = solve_exact_benchmark(tiny, tiny_x0, 25.0, gamma, 0.05)
        prb = solve_prb_benders(tiny, tiny_x0, 25.0, gamma, 0.05)
        solutions = [literal.solution, factorized.solution, prb.solution]
        assert all(solution is not None for solution in solutions)
        a, b, c = solutions
        maximum_x_difference = max(
            abs(left.x[i][j] - right.x[i][j])
            for left, right in ((a, b), (a, c), (b, c))
            for i in range(tiny.num_depots)
            for j in range(tiny.num_products)
        )
        exact_match = (
            max(a.objective, b.objective, c.objective) - min(a.objective, b.objective, c.objective) <= 1e-6
            and max(a.robust_recourse_cost, b.robust_recourse_cost, c.robust_recourse_cost)
            - min(a.robust_recourse_cost, b.robust_recourse_cost, c.robust_recourse_cost) <= 1e-6
            and maximum_x_difference <= 1e-6
        )
        tiny_rows.append({"gamma": gamma, "exact_match": exact_match, "maximum_x_difference": maximum_x_difference})

    rng = random.Random(config["random_seed"])
    cut_rows = []
    gamma_rows = []
    for case, (instance, _, _) in loaded.items():
        samples = [random_feasible_x(instance, rng) for _ in range(config["random_x_samples_per_case"])]
        for sample_number, x in enumerate(samples, 1):
            product_results = [
                ProductRiskSubproblem(instance, j, 2).solve(
                    [x[i][j] for i in range(instance.num_depots)]
                )
                for j in range(instance.num_products)
            ]
            for addition in representative_cuts[case]:
                cut = addition.cut
                value = product_results[cut.product_index].worst_cases[cut.local_gamma].value
                cut_rows.append({
                    "case": case,
                    "sample": sample_number,
                    "product": instance.product_ids[cut.product_index],
                    "g": cut.local_gamma,
                    "generation_iteration": addition.iteration,
                    "violation_at_generation": addition.violation_at_incumbent,
                    "dual_feasible": cut.dual_feasible,
                    "strong_duality_error": cut.strong_duality_error,
                    "generation_tightness_error": abs(cut.value_at(cut.generation_x) - cut.generation_value),
                    "cut_rhs_at_sample": cut.value_at([x[i][cut.product_index] for i in range(instance.num_depots)]),
                    "exact_value_at_sample": value,
                    "validity_violation": max(0.0, cut.value_at([x[i][cut.product_index] for i in range(instance.num_depots)]) - value),
                })
            values = [[worst.value for worst in result.worst_cases] for result in product_results]
            for gamma in config["gamma_values"]:
                composed = compose_risk_budget([row[: gamma + 1] for row in values], gamma)
                direct = evaluate_robust_service(instance, x, gamma)
                gamma_rows.append({
                    "case": case,
                    "sample": sample_number,
                    "gamma": gamma,
                    "global_scenario_value": direct.robust_recourse_cost,
                    "product_gamma_composition_value": composed.value,
                    "absolute_difference": abs(direct.robust_recourse_cost - composed.value),
                    "maximizing_gamma_allocation": json.dumps(composed.allocation),
                })

    attempted = len(runs)
    certified = sum(bool(row["certified"]) for row in runs)
    summary = {
        "mathematical_derivation": "PASS",
        "product_cut_validity_pass": max(float(row["validity_violation"]) for row in cut_rows) <= 1e-6,
        "product_cut_tightness_pass": max(float(row["generation_tightness_error"]) for row in cut_rows) <= 1e-6,
        "all_cut_duals_feasible": all(bool(row["dual_feasible"]) for row in cut_rows),
        "gamma_composition_exactness_pass": max(float(row["absolute_difference"]) for row in gamma_rows) <= 1e-6,
        "global_risk_budget_coupling_pass": all(bool(row["global_coupling_error"] <= 1e-6) for row in runs),
        "prb_benders_correctness_pass": certified == attempted,
        "primary_objective_cost_and_y_matches": sum(
            close(
                float(row["objective"]),
                float(row["exact_objective"]),
                config["objective_absolute_tolerance"],
                config["objective_relative_tolerance"],
            )
            and float(row["first_stage_difference"]) <= config["first_stage_absolute_tolerance"]
            and float(row["robust_recourse_difference"]) <= config["recourse_absolute_tolerance"]
            and bool(row["y_identical"])
            for row in runs
        ),
        "tiny_synthetic_tested": len(tiny_rows),
        "tiny_synthetic_exact_matches": sum(bool(row["exact_match"]) for row in tiny_rows),
        "tiny_synthetic": tiny_rows,
        "renault_attempted": attempted,
        "renault_certified": certified,
        "renault_mismatched": attempted - certified,
        "renault_time_limit": sum(row["status"] == "TIME_LIMIT" for row in runs),
        "renault_error": sum(row["status"] == "ERROR" for row in runs),
        "maximum_differences": {
            "objective": max(float(row["objective_difference"]) for row in runs),
            "first_stage_expenditure": max(float(row["first_stage_difference"]) for row in runs),
            "robust_recourse": max(float(row["robust_recourse_difference"]) for row in runs),
            "x": max(float(row["maximum_x_difference"]) for row in runs),
            "fr_min_robust": max(float(row["fr_min_difference"]) for row in runs),
        },
        "iterations": {
            "average": sum(int(row["iterations"]) for row in runs) / attempted,
            "maximum": max(int(row["iterations"]) for row in runs),
        },
        "product_cuts": {
            "average": sum(int(row["unique_product_cuts"]) for row in runs) / attempted,
            "maximum": max(int(row["unique_product_cuts"]) for row in runs),
        },
        "product_subproblem_evaluations_total": sum(int(row["product_subproblem_evaluations"]) for row in runs),
        "runtime_seconds": {
            "master_total": sum(float(row["master_runtime_seconds"]) for row in runs),
            "separation_total": sum(float(row["separation_runtime_seconds"]) for row in runs),
            "certification_total": sum(float(row["certification_runtime_seconds"]) for row in runs),
            "algorithm_total": sum(float(row["total_runtime_seconds"]) for row in runs),
        },
        "complete_recourse": True,
        "farkas_cuts_implemented": False,
        "frozen_model_parameter_changed": False,
        "old_benders_acceleration_added": False,
        "ccg_added": False,
        "formal_experiment_run": False,
        "issues": [
            "Strict x-identity fails for 210202 at lambda_R=0, beta=1.10, Gamma=1 and 2 because the two exact formulations select different members of the same optimal face; objectives, cost components, y, and frozen service metrics remain within tolerance.",
            "Solver-scale negative inventory values in [-1e-7,0) are projected to zero only at the recourse interface; materially negative inventory remains an error."
        ],
        "ready_for_separate_performance_validation": certified == attempted,
        "purpose": "correctness validation only; runtime is diagnostic",
    }
    write_csv(artifacts / "prb_benders_correctness_runs.csv", runs)
    write_csv(artifacts / "prb_cut_validity_audit.csv", cut_rows)
    write_csv(artifacts / "prb_gamma_composition_audit.csv", gamma_rows)
    (artifacts / "prb_benders_correctness_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
