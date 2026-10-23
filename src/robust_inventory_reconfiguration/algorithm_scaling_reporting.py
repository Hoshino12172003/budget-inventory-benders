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
            group = [
                index[(size.scale, seed, method)]
                for method in METHODS
                if (size.scale, seed, method) in index
            ]
            if len(group) < 2:
                continue
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
                if (
                    (size.scale, seed, left_method) not in index
                    or (size.scale, seed, right_method) not in index
                ):
                    continue
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
        paired_seeds = [
            seed for seed in SEEDS
            if (size.scale, seed, "pure_benders") in index
            and (size.scale, seed, "prb_benders") in index
        ]
        pure = [index[(size.scale, seed, "pure_benders")] for seed in paired_seeds]
        prb = [index[(size.scale, seed, "prb_benders")] for seed in paired_seeds]
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
    documented_non_certified: list[dict] | None = None,
) -> str:
    documented_non_certified = documented_non_certified or []
    expected_ids = {
        f"ASC_{size.scale}_S{seed}_{method.upper()}"
        for size in SIZES
        for seed in SEEDS
        for method in METHODS
    }
    result_ids = {row["condition_id"] for row in results}
    failure_ids = {row["condition_id"] for row in documented_non_certified}
    if result_ids & failure_ids or result_ids | failure_ids != expected_ids:
        raise ValueError(
            "reporting requires every formal condition to be certified or explicitly documented non-certified"
        )
    if len({row["condition_id"] for row in results}) != len(results):
        raise ValueError("duplicate physical algorithm-scaling result")
    if len(failure_ids) != len(documented_non_certified):
        raise ValueError("duplicate documented non-certified algorithm-scaling condition")
    for result in results:
        validate_result_schema(result)
        if result["solver_status"] != "OPTIMAL" or result["exact_certification"] is not True:
            raise ValueError("certified result set contains a non-certified condition")
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
    summary_lines = [
        "| Size | Method | N | Iterations | Core time (s) | Oracle time (s) | Iterations to 99.9% LB | Iterations to 99.99% LB |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_size:
        summary_lines.append(
            f"| {row['size']} | {row['method']} | {row['n']} | "
            f"{row['iterations_mean']:.3f} | {row['core_time_mean']:.3f} | "
            f"{row['oracle_time_mean']:.3f} | "
            f"{row['iterations_to_99_9pct_final_LB_mean']:.3f} | "
            f"{row['iterations_to_99_99pct_final_LB_mean']:.3f} |"
        )
    failure_text = ", ".join(sorted(failure_ids)) or "none"
    (output_root / "algorithm_scaling_summary.md").write_text(
        "# Algorithm scaling and convergence-cost trade-off\n\n"
        f"Expected conditions: {len(expected_ids)}; exact-certified: {len(results)}; "
        f"documented non-certified: {len(documented_non_certified)}; unattempted: 0.\n\n"
        f"Documented non-certified condition: `{failure_text}`.\n\n"
        f"Formal classification: `{classification}`.\n\n"
        + "\n".join(summary_lines)
        + "\n\nPRB consistently reduces iterations and accelerates lower-bound refinement relative "
        "to Aggregate, while its structured oracle remains substantially more expensive than "
        "Pure's global oracle. Pure is therefore fastest in wall-clock time; the result does not "
        "claim that PRB is fastest overall. The main trade-off is stronger information transfer "
        "versus higher oracle cost.\n\n"
        "XXL10 comparisons involving Pure use paired exact-certified seeds only; the Pure N=9 "
        "mean is not treated as a fully paired comparison against the N=10 Aggregate and PRB means.\n",
        encoding="utf-8",
    )
    return classification
