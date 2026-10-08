from __future__ import annotations

import csv
from math import exp, log
from pathlib import Path
from statistics import mean, median, stdev

from .algorithm_scaling import METHODS, SEEDS, SIZES


RESULT_FIELDS = (
    "experiment_id", "condition_id", "method", "size", "seed", "instance_id",
    "instance_hash", "config_hash", "code_commit", "model_identity", "solver_profile",
    "Gamma", "beta", "lambda_R", "SL", "phi_multiplier", "solver_status",
    "exact_certification", "final_objective", "final_lower_bound", "final_upper_bound",
    "relative_gap", "iterations", "cuts", "feasibility_cuts", "optimality_cuts",
    "iterations_to_99pct_final_LB", "iterations_to_99_5pct_final_LB",
    "iterations_to_99_9pct_final_LB", "iterations_to_99_99pct_final_LB",
    "total_core_solve_time", "master_time", "oracle_time", "certification_time",
    "initialization_other_overhead", "master_share", "oracle_share",
    "peak_process_tree_memory_gib", "result_reused",
)

TRAJECTORY_FIELDS = (
    "experiment_id", "condition_id", "method", "size", "seed", "instance_id",
    "iteration", "LB", "UB", "gap", "normalized_LB", "master_time_seconds",
    "oracle_time_seconds", "certification_time_seconds", "cumulative_time_seconds",
    "cuts_added",
)

CHARACTERISTIC_FIELDS = (
    "instance_id", "instance_hash", "size", "seed", "I", "R", "J",
    "uncertainty_components", "scenario_related_dimensions",
    "estimated_master_variables_pure", "estimated_master_variables_structured_aggregate",
    "estimated_master_variables_prb", "estimated_oracle_variables_pure",
    "estimated_oracle_product_risk_blocks", "first_stage_variables",
    "actual_master_variables_pure_formula",
    "actual_master_variables_structured_aggregate_formula",
    "actual_master_variables_prb_formula", "actual_oracle_variables_pure_formula",
    "actual_oracle_variables_structured_total_formula",
    "pure_binary_variables", "pure_continuous_variables", "pure_total_variables",
    "pure_constraints", "prb_product_risk_blocks", "prb_master_surrogates",
    "prb_product_cut_dimension", "aggregate_cut_dimension", "direct_variables",
    "direct_constraints",
)


def validate_result_schema(result: dict) -> None:
    missing = [field for field in RESULT_FIELDS if field not in result]
    if missing:
        raise ValueError(f"algorithm-scaling result schema missing: {','.join(missing)}")


def validate_trajectory_schema(row: dict) -> None:
    missing = [field for field in TRAJECTORY_FIELDS if field not in row]
    if missing:
        raise ValueError(f"algorithm-scaling trajectory schema missing: {','.join(missing)}")


def _quartile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _statistics(values: list[float], prefix: str) -> dict[str, float]:
    return {
        f"{prefix}_mean": mean(values),
        f"{prefix}_median": median(values),
        f"{prefix}_stdev": stdev(values) if len(values) > 1 else 0.0,
        f"{prefix}_q1": _quartile(values, 0.25),
        f"{prefix}_q3": _quartile(values, 0.75),
    }


def _summarize(group: list[dict], identity: dict) -> dict:
    row = {**identity, "n": len(group)}
    metrics = {
        "iterations": "iterations",
        "core_time": "total_core_solve_time",
        "master_time": "master_time",
        "oracle_time": "oracle_time",
        "certification_time": "certification_time",
        "cuts": "cuts",
        "iterations_to_99pct_final_LB": "iterations_to_99pct_final_LB",
        "iterations_to_99_5pct_final_LB": "iterations_to_99_5pct_final_LB",
        "iterations_to_99_9pct_final_LB": "iterations_to_99_9pct_final_LB",
        "iterations_to_99_99pct_final_LB": "iterations_to_99_99pct_final_LB",
    }
    for prefix, field in metrics.items():
        row.update(_statistics([float(item[field]) for item in group], prefix))
    times = [float(item["total_core_solve_time"]) for item in group]
    row["core_time_geometric_mean"] = exp(mean([log(value) for value in times])) if all(value > 0 for value in times) else None
    row["certified_n"] = sum(item["solver_status"] == "OPTIMAL" and item["exact_certification"] is True for item in group)
    return row


def build_summary_by_size(results: list[dict]) -> list[dict]:
    return [
        _summarize(
            [row for row in results if row["size"] == size.scale and row["method"] == method],
            {"size": size.scale, "method": method},
        )
        for size in SIZES
        for method in METHODS
    ]


def build_summary_by_method(results: list[dict]) -> list[dict]:
    return [
        _summarize([row for row in results if row["method"] == method], {"method": method})
        for method in METHODS
    ]


def validate_pairwise_fairness(results: list[dict], objective_tolerance: float) -> None:
    index = {(row["size"], row["seed"], row["method"]): row for row in results}
    for size in SIZES:
        for seed in SEEDS:
            group = [index[(size.scale, seed, method)] for method in METHODS]
            identity_fields = ("instance_hash", "config_hash", "model_identity", "Gamma", "beta", "lambda_R", "SL", "phi_multiplier", "solver_profile")
            for field in identity_fields:
                if len({row[field] for row in group}) != 1:
                    raise ValueError(f"pairwise identity mismatch {size.scale}/{seed}/{field}")
            if not all(row["solver_status"] == "OPTIMAL" and row["exact_certification"] is True for row in group):
                raise ValueError(f"pairwise exact-certification failure {size.scale}/{seed}")
            objectives = [float(row["final_objective"]) for row in group]
            if max(objectives) - min(objectives) > objective_tolerance:
                raise ValueError(f"pairwise objective mismatch {size.scale}/{seed}")


def build_pairwise(results: list[dict]) -> list[dict]:
    index = {(row["size"], row["seed"], row["method"]): row for row in results}
    pairs = (
        ("pure_benders", "prb_benders"),
        ("aggregate_benders_structured_oracle", "prb_benders"),
        ("pure_benders", "aggregate_benders_structured_oracle"),
    )
    rows = []
    for size in SIZES:
        for seed in SEEDS:
            for left_method, right_method in pairs:
                left = index[(size.scale, seed, left_method)]
                right = index[(size.scale, seed, right_method)]
                rows.append({
                    "size": size.scale,
                    "seed": seed,
                    "method_a": left_method,
                    "method_b": right_method,
                    "objective_difference_b_minus_a": right["final_objective"] - left["final_objective"],
                    "iteration_difference_b_minus_a": right["iterations"] - left["iterations"],
                    "relative_iteration_reduction_b_vs_a": (left["iterations"] - right["iterations"]) / left["iterations"],
                    "core_time_ratio_b_over_a": right["total_core_solve_time"] / left["total_core_solve_time"],
                    "master_time_ratio_b_over_a": right["master_time"] / left["master_time"] if left["master_time"] else None,
                    "oracle_time_ratio_b_over_a": right["oracle_time"] / left["oracle_time"] if left["oracle_time"] else None,
                })
    return rows


def classify_tradeoff(results: list[dict]) -> str:
    index = {(row["size"], row["seed"], row["method"]): row for row in results}
    fewer_by_size = []
    faster_by_size = []
    dearer_oracle_by_size = []
    for size in SIZES:
        pure = [index[(size.scale, seed, "pure_benders")] for seed in SEEDS]
        prb = [index[(size.scale, seed, "prb_benders")] for seed in SEEDS]
        fewer_by_size.append(median([row["iterations"] for row in prb]) < median([row["iterations"] for row in pure]))
        faster_by_size.append(median([row["total_core_solve_time"] for row in prb]) < median([row["total_core_solve_time"] for row in pure]))
        dearer_oracle_by_size.append(median([row["oracle_time"] for row in prb]) > median([row["oracle_time"] for row in pure]))
    if all(fewer_by_size) and all(faster_by_size):
        return "PRB_FEWER_ITERATIONS_AND_FASTER_TOTAL_TIME"
    if all(fewer_by_size) and all(dearer_oracle_by_size):
        return "PRB_FEWER_ITERATIONS_BUT_HIGHER_ORACLE_COST"
    if any(fewer_by_size) and not all(fewer_by_size):
        return "SIZE_DEPENDENT_TRADEOFF"
    return "PRB_NO_CLEAR_CONVERGENCE_ADVANTAGE"


def _write_csv(path: Path, rows: list[dict], fields: tuple[str, ...] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    selected = list(fields or tuple(rows[0].keys()))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=selected, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_reports(
    results: list[dict],
    trajectories: list[dict],
    characteristics: list[dict],
    output_root: Path,
    *,
    objective_tolerance: float,
) -> str:
    if len(results) != len(SIZES) * len(SEEDS) * len(METHODS):
        raise ValueError("reporting requires the complete 90-condition formal grid")
    if len({row["condition_id"] for row in results}) != len(results):
        raise ValueError("duplicate physical algorithm-scaling result")
    for result in results:
        validate_result_schema(result)
    for row in trajectories:
        validate_trajectory_schema(row)
    validate_pairwise_fairness(results, objective_tolerance)
    summary_size = build_summary_by_size(results)
    summary_method = build_summary_by_method(results)
    pairwise = build_pairwise(results)
    classification = classify_tradeoff(results)
    _write_csv(output_root / "algorithm_scaling_all_results.csv", results, RESULT_FIELDS)
    _write_csv(output_root / "algorithm_scaling_summary_by_size.csv", summary_size)
    _write_csv(output_root / "algorithm_scaling_summary_by_method.csv", summary_method)
    _write_csv(output_root / "algorithm_scaling_pairwise.csv", pairwise)
    _write_csv(output_root / "algorithm_scaling_iteration_trajectory.csv", trajectories, TRAJECTORY_FIELDS)
    _write_csv(output_root / "algorithm_scaling_instance_characteristics.csv", characteristics, CHARACTERISTIC_FIELDS)
    (output_root / "algorithm_scaling_summary.md").write_text(
        "# Algorithm scaling and convergence-cost trade-off\n\n"
        f"Formal classification: `{classification}`.\n\n"
        "This classification jointly uses paired iterations, core time, master time, and oracle time. "
        "It does not assert that PRB is universally faster.\n",
        encoding="utf-8",
    )
    return classification
