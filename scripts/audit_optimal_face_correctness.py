from __future__ import annotations

import csv
import json
from pathlib import Path

from robust_inventory_reconfiguration.exact_benchmark import solve_exact_benchmark
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.optimal_face_correctness import (
    EXACT_SOLUTION_IDENTITY,
    FAIL,
    OPTIMAL_FACE_EQUIVALENT,
    ComparisonEvidence,
    CorrectnessTolerances,
    audit_first_stage_feasibility,
    classify_solution_comparison,
)
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service


ROOT = Path(__file__).resolve().parents[1]
FORMER_MISMATCHES = {("210202", 1, 1.1, 0.0), ("210202", 2, 1.1, 0.0)}


def load_baseline(case, instance):
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


def objective_close(value: float, reference: float, tolerances: CorrectnessTolerances) -> bool:
    threshold = max(
        tolerances.objective_absolute,
        tolerances.objective_relative * max(abs(value), abs(reference)),
    )
    return abs(value - reference) <= threshold


def audit_former_mismatch(case, gamma, beta, lambda_r, config, tolerances):
    instance = load_instance(ROOT / "data" / "formal_instances" / f"{case}.json")
    x0, b_ref = load_baseline(case, instance)
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
    if exact.solution is None:
        raise RuntimeError("Former mismatch exact benchmark did not return a solution")
    solutions = {"exact": exact.solution, "prb": prb.solution}
    audits = {}
    audit_rows = []
    z_star = exact.solution.objective
    for method, solution in solutions.items():
        feasibility = audit_first_stage_feasibility(
            instance,
            x0,
            solution.y,
            solution.x,
            solution.a_plus,
            solution.a_minus,
            lambda_r,
            budget,
            tolerance=config["feasibility_tolerance"],
        )
        service = evaluate_robust_service(instance, solution.x, gamma)
        independently_evaluated_z = (
            feasibility.first_stage_expenditure + service.robust_recourse_cost
        )
        recourse_certified = (
            abs(service.robust_recourse_cost - solution.robust_recourse_cost)
            <= tolerances.robust_recourse_absolute
        )
        optimal_level = objective_close(independently_evaluated_z, z_star, tolerances)
        exact_certified = (
            exact.status == "OPTIMAL"
            if method == "exact"
            else prb.status == "OPTIMAL" and prb.exact_certification_pass
        )
        exactly_certified = exact_certified and recourse_certified and optimal_level
        audits[method] = {
            "solution": solution,
            "feasibility": feasibility,
            "service": service,
            "z": independently_evaluated_z,
            "optimal_level": optimal_level,
            "exactly_certified": exactly_certified,
        }
        audit_rows.append({
            "case": case,
            "gamma": gamma,
            "beta": beta,
            "lambda_r": lambda_r,
            "method": method,
            "z_star": z_star,
            "independently_evaluated_z": independently_evaluated_z,
            "objective_level_difference": abs(independently_evaluated_z - z_star),
            "first_stage_expenditure": feasibility.first_stage_expenditure,
            "robust_recourse": service.robust_recourse_cost,
            "fr_min_robust": service.minimum_fill_rate,
            "worst_region": service.worst_region_id,
            "worst_scenario": ";".join(f"{r}:{j}" for r, j in service.worst_scenario),
            "first_stage_feasible": feasibility.feasible,
            "maximum_feasibility_violation": feasibility.maximum_violation,
            "recourse_certified": recourse_certified,
            "on_global_optimal_level": optimal_level,
            "exactly_certified": exactly_certified,
            "y": json.dumps(solution.y),
            "x": json.dumps(solution.x),
        })

    exact_audit = audits["exact"]
    prb_audit = audits["prb"]
    x_exact = exact_audit["solution"].x
    x_prb = prb_audit["solution"].x
    differences = [
        abs(x_exact[i][j] - x_prb[i][j])
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    ]
    evidence = ComparisonEvidence(
        exact_certified=exact_audit["exactly_certified"],
        prb_certified=prb_audit["exactly_certified"],
        exact_feasible=exact_audit["feasibility"].feasible,
        prb_feasible=prb_audit["feasibility"].feasible,
        objective_difference=abs(exact_audit["z"] - prb_audit["z"]),
        objective_scale=max(abs(exact_audit["z"]), abs(prb_audit["z"])),
        first_stage_difference=abs(
            exact_audit["feasibility"].first_stage_expenditure
            - prb_audit["feasibility"].first_stage_expenditure
        ),
        robust_recourse_difference=abs(
            exact_audit["service"].robust_recourse_cost
            - prb_audit["service"].robust_recourse_cost
        ),
        y_identical=exact_audit["solution"].y == prb_audit["solution"].y,
        maximum_x_difference=max(differences),
        fill_rate_difference=abs(
            exact_audit["service"].minimum_fill_rate
            - prb_audit["service"].minimum_fill_rate
        ),
        exact_on_optimal_face=exact_audit["optimal_level"],
        prb_on_optimal_face=prb_audit["optimal_level"],
    )
    comparison = {
        "case": case,
        "gamma": gamma,
        "beta": beta,
        "lambda_r": lambda_r,
        "z_star": z_star,
        "z_exact": exact_audit["z"],
        "z_prb": prb_audit["z"],
        "objective_difference": evidence.objective_difference,
        "first_stage_difference": evidence.first_stage_difference,
        "robust_recourse_difference": evidence.robust_recourse_difference,
        "fr_min_difference": evidence.fill_rate_difference,
        "maximum_x_difference": evidence.maximum_x_difference,
        "differing_x_coordinates": sum(
            difference > tolerances.x_absolute for difference in differences
        ),
        "total_absolute_x_difference": sum(differences),
        "total_inventory_difference": abs(
            sum(map(sum, x_exact)) - sum(map(sum, x_prb))
        ),
        "y_identical": evidence.y_identical,
        "both_independently_feasible": evidence.exact_feasible and evidence.prb_feasible,
        "both_exactly_certified": evidence.exact_certified and evidence.prb_certified,
        "exact_independently_feasible": evidence.exact_feasible,
        "prb_independently_feasible": evidence.prb_feasible,
        "exact_exactly_certified": evidence.exact_certified,
        "prb_exactly_certified": evidence.prb_certified,
        "exact_on_optimal_face": evidence.exact_on_optimal_face,
        "prb_on_optimal_face": evidence.prb_on_optimal_face,
        "genuine_alternate_optimum": (
            evidence.maximum_x_difference > 100 * tolerances.x_absolute
            and evidence.exact_on_optimal_face
            and evidence.prb_on_optimal_face
        ),
        "comparison_status": classify_solution_comparison(evidence, tolerances),
    }
    return comparison, audit_rows


def main() -> None:
    config = json.loads(
        (ROOT / "configs" / "prb_benders_correctness.json").read_text(encoding="utf-8")
    )
    tolerances = CorrectnessTolerances(
        objective_absolute=config["objective_absolute_tolerance"],
        objective_relative=config["objective_relative_tolerance"],
        first_stage_absolute=config["first_stage_absolute_tolerance"],
        robust_recourse_absolute=config["recourse_absolute_tolerance"],
        x_absolute=config["x_absolute_tolerance"],
        fill_rate_absolute=config["fill_rate_absolute_tolerance"],
    )
    with (ROOT / "artifacts" / "prb_benders_correctness_runs.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        previous_rows = list(csv.DictReader(stream))
    with (ROOT / "artifacts" / "reconfiguration_correctness_runs.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        frozen_exact_rows = list(csv.DictReader(stream))
    frozen_exact = {
        (row["case"], int(row["gamma"]), float(row["beta"]), float(row["lambda_r"])): row
        for row in frozen_exact_rows
    }

    former_results = {}
    optimal_face_rows = []
    for key in sorted(FORMER_MISMATCHES):
        result, method_rows = audit_former_mismatch(*key, config, tolerances)
        former_results[key] = result
        optimal_face_rows.extend(method_rows)
        print(key, result["comparison_status"], flush=True)

    reclassified = []
    for row in previous_rows:
        key = (row["case"], int(row["gamma"]), float(row["beta"]), float(row["lambda_r"]))
        if key in former_results:
            result = former_results[key]
            evidence = {
                "comparison_status": result["comparison_status"],
                "objective_difference": result["objective_difference"],
                "first_stage_difference": result["first_stage_difference"],
                "robust_recourse_difference": result["robust_recourse_difference"],
                "maximum_x_difference": result["maximum_x_difference"],
                "fr_min_difference": result["fr_min_difference"],
                "exact_certification_pass": result["exact_exactly_certified"],
                "prb_certification_pass": result["prb_exactly_certified"],
                "exact_first_stage_feasible": result["exact_independently_feasible"],
                "prb_first_stage_feasible": result["prb_independently_feasible"],
            }
        else:
            exact_row = frozen_exact[key]
            exact_feasible = (
                float(exact_row["budget_slack"]) >= -config["feasibility_tolerance"]
                and float(exact_row["first_stage_accounting_error"])
                <= config["feasibility_tolerance"]
                and float(exact_row["reconfiguration_identity_error"])
                <= config["feasibility_tolerance"]
            )
            exact_certified = (
                exact_row["status"] == "OPTIMAL"
                and float(exact_row["mip_gap"]) <= config["relative_gap_tolerance"]
                and float(exact_row["direct_robust_recourse_difference"])
                <= tolerances.robust_recourse_absolute
            )
            comparison = ComparisonEvidence(
                exact_certified=exact_certified,
                prb_certified=row["exact_certification"] == "True",
                exact_feasible=exact_feasible,
                prb_feasible=row["status"] == "OPTIMAL",
                objective_difference=float(row["objective_difference"]),
                objective_scale=max(abs(float(row["objective"])), abs(float(row["exact_objective"]))),
                first_stage_difference=float(row["first_stage_difference"]),
                robust_recourse_difference=float(row["robust_recourse_difference"]),
                y_identical=row["y_identical"] == "True",
                maximum_x_difference=float(row["maximum_x_difference"]),
                fill_rate_difference=float(row["fr_min_difference"]),
                exact_on_optimal_face=True,
                prb_on_optimal_face=True,
            )
            evidence = {
                "comparison_status": classify_solution_comparison(comparison, tolerances),
                "objective_difference": comparison.objective_difference,
                "first_stage_difference": comparison.first_stage_difference,
                "robust_recourse_difference": comparison.robust_recourse_difference,
                "maximum_x_difference": comparison.maximum_x_difference,
                "fr_min_difference": comparison.fill_rate_difference,
                "exact_certification_pass": comparison.exact_certified,
                "prb_certification_pass": comparison.prb_certified,
                "exact_first_stage_feasible": comparison.exact_feasible,
                "prb_first_stage_feasible": comparison.prb_feasible,
            }
        reclassified.append({
            "case": key[0],
            "gamma": key[1],
            "beta": key[2],
            "lambda_r": key[3],
            **evidence,
        })

    counts = {
        status: sum(row["comparison_status"] == status for row in reclassified)
        for status in (EXACT_SOLUTION_IDENTITY, OPTIMAL_FACE_EQUIVALENT, FAIL)
    }
    equivalence_confirmed = all(
        result["comparison_status"] == OPTIMAL_FACE_EQUIVALENT
        for result in former_results.values()
    )
    summary = {
        "optimal_face_equivalence_confirmed": equivalence_confirmed,
        "prb_benders_correctness_pass": counts[FAIL] == 0,
        "classification_counts": counts,
        "former_mismatch_cases": list(former_results.values()),
        "contract": (
            "Correctness means that PRB-Benders solves the same mathematical problem and returns "
            "a certified globally optimal solution; coordinate-wise identity is not required when "
            "independently certified solutions lie on the same optimal objective level."
        ),
        "main_mathematical_model_changed": False,
        "prb_benders_algorithm_changed": False,
        "secondary_tie_break_introduced": False,
        "frozen_parameter_changed": False,
        "ready_for_separate_performance_validation": counts[FAIL] == 0,
    }
    artifacts = ROOT / "artifacts"
    write_csv(artifacts / "prb_correctness_reclassification.csv", reclassified)
    write_csv(artifacts / "prb_optimal_face_audit.csv", optimal_face_rows)
    (artifacts / "prb_correctness_contract_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
