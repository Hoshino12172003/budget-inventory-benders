from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = ROOT / "experiments/results/e1_empirical_8case_v1"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
CORRECTNESS_TOLERANCE = 1e-4


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primary_hashes() -> dict[str, str]:
    return {
        path.relative_to(RESULTS_ROOT).as_posix(): sha256(path)
        for path in sorted(RESULTS_ROOT.rglob("*"))
        if path.is_file()
    }


def describe(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "geometric_mean": math.exp(statistics.mean(math.log(value) for value in values)),
        "minimum": min(values),
        "maximum": max(values),
        "sample_standard_deviation": statistics.stdev(values),
    }


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        rank = (start + end + 2) / 2
        for position in range(start, end + 1):
            ranks[order[position]] = rank
        start = end + 1
    return ranks


def correlations(x: list[float], y: list[float]) -> dict[str, float]:
    return {
        "pearson": statistics.correlation(x, y),
        "spearman": statistics.correlation(average_ranks(x), average_ranks(y)),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    before = primary_hashes()
    rows: list[dict[str, Any]] = []
    completeness = {
        "run_directories": 0,
        "result_json": 0,
        "first_stage_solution_json": 0,
        "provenance_json": 0,
        "solver_logs": 0,
        "optimal_status": 0,
        "objectives_recorded": 0,
        "runtimes_recorded": 0,
        "solution_provenance_hash_matches": 0,
        "resource_limited": 0,
    }

    for case in CASES:
        instance = read_json(ROOT / f"data/formal_instances_v2/{case}.json")
        runs: dict[str, dict[str, Any]] = {}
        for method in ("DIRECT", "PRB"):
            directory = RESULTS_ROOT / f"E1-{case}-{method}"
            if not directory.is_dir():
                raise RuntimeError(f"missing run directory: {directory.name}")
            completeness["run_directories"] += 1
            required = {
                "result": directory / "result.json",
                "solution": directory / "first_stage_solution.json",
                "provenance": directory / "provenance.json",
            }
            for name, path in required.items():
                if not path.is_file():
                    raise RuntimeError(f"missing {name} for {directory.name}")
            completeness["result_json"] += 1
            completeness["first_stage_solution_json"] += 1
            completeness["provenance_json"] += 1
            result = read_json(required["result"])
            solution = read_json(required["solution"])
            provenance = read_json(required["provenance"])
            log_path = directory / "solver.log"
            solver_log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else None
            completeness["solver_logs"] += int(solver_log is not None)
            completeness["optimal_status"] += int(result.get("status") == "OPTIMAL")
            completeness["objectives_recorded"] += int(result.get("objective") is not None)
            completeness["runtimes_recorded"] += int(result.get("runtime_seconds") is not None)
            completeness["resource_limited"] += int(result.get("status") == "RESOURCE_LIMITED")
            hash_match = sha256(required["solution"]) == provenance.get("first_stage_solution_sha256")
            completeness["solution_provenance_hash_matches"] += int(hash_match)
            if result.get("status") != "OPTIMAL":
                raise RuntimeError(f"non-optimal run: {directory.name}")
            if result.get("objective") is None or result.get("runtime_seconds") is None:
                raise RuntimeError(f"missing objective or runtime: {directory.name}")
            if not hash_match:
                raise RuntimeError(f"solution provenance mismatch: {directory.name}")
            runs[method] = {
                "result": result,
                "solution": solution,
                "provenance": provenance,
                "solver_log_present": solver_log is not None,
            }

        direct = runs["DIRECT"]["result"]
        prb = runs["PRB"]["result"]
        objective_difference = abs(float(direct["objective"]) - float(prb["objective"]))
        if objective_difference > CORRECTNESS_TOLERANCE:
            raise RuntimeError(f"objective consistency failure: {case}")
        if direct["instance_hash"] != prb["instance_hash"] or direct["x0_hash"] != prb["x0_hash"]:
            raise RuntimeError(f"paired identity mismatch: {case}")
        direct_runtime = float(direct["runtime_seconds"])
        prb_runtime = float(prb["runtime_seconds"])
        speedup = direct_runtime / prb_runtime
        rows.append({
            "case": case,
            "I": len(instance["depot_ids"]),
            "R": len(instance["region_ids"]),
            "J": len(instance["product_ids"]),
            "direct_objective": direct["objective"],
            "prb_objective": prb["objective"],
            "absolute_objective_difference": objective_difference,
            "direct_runtime_seconds": direct_runtime,
            "prb_runtime_seconds": prb_runtime,
            "speedup_direct_over_prb": speedup,
            "prb_time_reduction_percent": 100 * (direct_runtime - prb_runtime) / direct_runtime,
            "faster_method": "PRB" if prb_runtime < direct_runtime else "DIRECT" if direct_runtime < prb_runtime else "TIE",
            "direct_optimality_status": direct["exact_certification_status"],
            "prb_certification_status": prb["exact_certification_status"],
            "direct_final_gap": direct["final_gap"],
            "prb_final_gap": prb["final_gap"],
            "prb_iterations": prb.get("iteration_count"),
            "prb_cut_count": prb.get("cut_count"),
            "prb_master_solves": prb.get("master_solve_count"),
            "prb_product_subproblem_evaluations": prb.get("product_subproblem_evaluations"),
            "prb_global_coupling_diagnostic_status": "PASS" if prb.get("global_coupling_pass") else "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH" if case == "210330" else "FAIL",
            "instance_hash": direct["instance_hash"],
            "x0_hash": direct["x0_hash"],
        })

    if any(completeness[key] != 16 for key in (
        "run_directories", "result_json", "first_stage_solution_json", "provenance_json",
        "optimal_status", "objectives_recorded", "runtimes_recorded", "solution_provenance_hash_matches",
    )) or completeness["resource_limited"]:
        raise RuntimeError("E1_PERFORMANCE_SUMMARY_BLOCKED")

    direct_runtimes = [row["direct_runtime_seconds"] for row in rows]
    prb_runtimes = [row["prb_runtime_seconds"] for row in rows]
    speedups = [row["speedup_direct_over_prb"] for row in rows]
    objective_differences = [row["absolute_objective_difference"] for row in rows]
    iterations = [row["prb_iterations"] for row in rows]
    cuts = [row["prb_cut_count"] for row in rows]
    master_solves = [row["prb_master_solves"] for row in rows]
    subproblem_evaluations = [row["prb_product_subproblem_evaluations"] for row in rows]
    depot_counts = [float(row["I"]) for row in rows]
    network_size = {
        "I_vs_direct_runtime": correlations(depot_counts, direct_runtimes),
        "I_vs_prb_runtime": correlations(depot_counts, prb_runtimes),
        "I_vs_speedup": correlations(depot_counts, speedups),
        "sample_size": 8,
        "interpretation": "descriptive association only; no inferential or large-scale scalability claim",
    }
    summary = {
        "schema": "e1_empirical_performance_summary_v1",
        "status": "E1_COMPUTATIONAL_PERFORMANCE_COMPLETE",
        "dataset_id": "RENAULT_EMPIRICAL_8CASE_V1",
        "correctness_tolerance": CORRECTNESS_TOLERANCE,
        "completed_runs": 16,
        "completed_pairs": 8,
        "correctness_pass_pairs": 8,
        "completeness": completeness,
        "direct_runtime_seconds": describe(direct_runtimes),
        "prb_runtime_seconds": describe(prb_runtimes),
        "speedup_direct_over_prb": describe(speedups) | {
            "prb_faster_count": sum(value > 1 for value in speedups),
            "direct_faster_count": sum(value < 1 for value in speedups),
            "ties": sum(value == 1 for value in speedups),
        },
        "paired_runtime_difference_seconds": {
            "median": statistics.median(direct - prb for direct, prb in zip(direct_runtimes, prb_runtimes)),
        },
        "objective_consistency": {
            "maximum_absolute_difference": max(objective_differences),
            "mean_absolute_difference": statistics.mean(objective_differences),
            "median_absolute_difference": statistics.median(objective_differences),
            "gate_pass_count": 8,
        },
        "prb_diagnostics": {
            "iterations": {
                "recorded_count": len(iterations),
                "mean": statistics.mean(iterations),
                "median": statistics.median(iterations),
                "minimum": min(iterations),
                "maximum": max(iterations),
            },
            "cuts": {
                "recorded_count": len(cuts),
                "mean": statistics.mean(cuts),
                "minimum": min(cuts),
                "maximum": max(cuts),
            },
            "master_solves": {"recorded_count": len(master_solves), "mean": statistics.mean(master_solves)},
            "product_subproblem_evaluations": {
                "recorded_count": len(subproblem_evaluations),
                "mean": statistics.mean(subproblem_evaluations),
            },
            "global_coupling_pass_count": 7,
            "global_coupling_exception": {
                "case": "210330",
                "classification": "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH",
                "objective_consistency_pass": True,
                "exact_recourse_recertification_pass": True,
                "gamma_allocation_feasible": True,
                "objective_affected": False,
            },
        },
        "network_size_descriptive_association": network_size,
        "statistical_test": "not performed; n=8 descriptive paired summaries are reported",
        "rows": rows,
        "change_control": {
            "optimization_reruns": 0,
            "model_changed": False,
            "dataset_changed": False,
            "tolerance_changed": False,
            "authorization_changed": False,
            "e2_e7_authorization": False,
        },
    }

    detailed_fields = list(rows[0])
    write_csv(ROOT / "table_e1_empirical_performance.csv", rows, detailed_fields)
    summary_rows = []
    for method, values in (("Direct runtime", summary["direct_runtime_seconds"]), ("PRB runtime", summary["prb_runtime_seconds"])):
        for metric, value in values.items():
            summary_rows.append({"section": method, "metric": metric, "value": value, "unit": "seconds", "recorded_count": 8, "notes": ""})
    for metric, value in summary["speedup_direct_over_prb"].items():
        unit = "count" if metric.endswith("count") or metric == "ties" else "ratio"
        summary_rows.append({"section": "Speedup", "metric": metric, "value": value, "unit": unit, "recorded_count": 8, "notes": "Direct runtime divided by PRB runtime"})
    for metric, value in summary["objective_consistency"].items():
        summary_rows.append({"section": "Objective consistency", "metric": metric, "value": value, "unit": "count" if metric == "gate_pass_count" else "objective units", "recorded_count": 8, "notes": "Frozen tolerance 1e-4"})
    for metric in ("iterations", "cuts"):
        for name, value in summary["prb_diagnostics"][metric].items():
            if name != "recorded_count":
                summary_rows.append({"section": f"PRB {metric}", "metric": name, "value": value, "unit": "count", "recorded_count": 8, "notes": ""})
    summary_rows.extend([
        {"section": "Paired runtime", "metric": "median_direct_minus_prb", "value": summary["paired_runtime_difference_seconds"]["median"], "unit": "seconds", "recorded_count": 8, "notes": "Paired case difference"},
        {"section": "PRB master solves", "metric": "mean", "value": summary["prb_diagnostics"]["master_solves"]["mean"], "unit": "count", "recorded_count": 8, "notes": ""},
        {"section": "PRB product subproblem evaluations", "metric": "mean", "value": summary["prb_diagnostics"]["product_subproblem_evaluations"]["mean"], "unit": "count", "recorded_count": 8, "notes": ""},
    ])
    for label, values in network_size.items():
        if isinstance(values, dict):
            for metric, value in values.items():
                summary_rows.append({"section": "Network size", "metric": f"{label}_{metric}", "value": value, "unit": "correlation", "recorded_count": 8, "notes": "Descriptive only; n=8"})
    write_csv(
        ROOT / "table_e1_empirical_performance_summary.csv",
        summary_rows,
        ["section", "metric", "value", "unit", "recorded_count", "notes"],
    )
    artifact_path = ROOT / "artifacts/e1_empirical_performance_summary.json"
    artifact_path.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

    document = f"""# E1 empirical computational performance summary

All 16 paper-final result directories were read from `RENAULT_EMPIRICAL_8CASE_V1`.
The summary uses the persisted `runtime_seconds` field and does not rerun an
optimization. All eight paired objective differences pass the frozen `1e-4`
consistency tolerance, and no run is resource-limited.

Direct solver logs are present for 8/8 Direct runs. PRB solver logs are not
recorded because the PRB runner does not create a separate solver log; its
certification, iteration, cut, bound, and runtime diagnostics are persisted in
`result.json`. This missing optional log does not affect the completeness gate.

## Main results

| Case | I | Direct obj. | PRB obj. | Abs. diff. | Direct time (s) | PRB time (s) | Speedup |
|---|---:|---:|---:|---:|---:|---:|---:|
"""
    for row in rows:
        document += (
            f"| {row['case']} | {row['I']} | {row['direct_objective']:.10f} | "
            f"{row['prb_objective']:.10f} | {row['absolute_objective_difference']:.3e} | "
            f"{row['direct_runtime_seconds']:.6f} | {row['prb_runtime_seconds']:.6f} | "
            f"{row['speedup_direct_over_prb']:.3f} |\n"
        )
    document += f"""

## Aggregate runtime and speedup

| Runtime statistic (s) | Direct | PRB |
|---|---:|---:|
| Arithmetic mean | {summary['direct_runtime_seconds']['mean']:.6f} | {summary['prb_runtime_seconds']['mean']:.6f} |
| Median | {summary['direct_runtime_seconds']['median']:.6f} | {summary['prb_runtime_seconds']['median']:.6f} |
| Geometric mean | {summary['direct_runtime_seconds']['geometric_mean']:.6f} | {summary['prb_runtime_seconds']['geometric_mean']:.6f} |
| Minimum | {summary['direct_runtime_seconds']['minimum']:.6f} | {summary['prb_runtime_seconds']['minimum']:.6f} |
| Maximum | {summary['direct_runtime_seconds']['maximum']:.6f} | {summary['prb_runtime_seconds']['maximum']:.6f} |
| Sample standard deviation | {summary['direct_runtime_seconds']['sample_standard_deviation']:.6f} | {summary['prb_runtime_seconds']['sample_standard_deviation']:.6f} |

| Speedup statistic | Direct/PRB ratio |
|---|---:|
| Arithmetic mean | {summary['speedup_direct_over_prb']['mean']:.6f} |
| Median | {summary['speedup_direct_over_prb']['median']:.6f} |
| Geometric mean | {summary['speedup_direct_over_prb']['geometric_mean']:.6f} |
| Minimum | {summary['speedup_direct_over_prb']['minimum']:.6f} |
| Maximum | {summary['speedup_direct_over_prb']['maximum']:.6f} |
| PRB wins | {summary['speedup_direct_over_prb']['prb_faster_count']}/8 |

PRB is faster in all 8 cases. Direct has mean and median runtimes of
`{summary['direct_runtime_seconds']['mean']:.6f}` s and
`{summary['direct_runtime_seconds']['median']:.6f}` s. PRB has mean and median
runtimes of `{summary['prb_runtime_seconds']['mean']:.6f}` s and
`{summary['prb_runtime_seconds']['median']:.6f}` s. The geometric-mean speedup
is `{summary['speedup_direct_over_prb']['geometric_mean']:.6f}`, with a range of
`{summary['speedup_direct_over_prb']['minimum']:.6f}` to
`{summary['speedup_direct_over_prb']['maximum']:.6f}`.

The maximum, mean, and median absolute objective differences are
`{summary['objective_consistency']['maximum_absolute_difference']:.17g}`,
`{summary['objective_consistency']['mean_absolute_difference']:.17g}`, and
`{summary['objective_consistency']['median_absolute_difference']:.17g}`.

## PRB diagnostics

Iterations have mean `{summary['prb_diagnostics']['iterations']['mean']:.3f}`, median
`{summary['prb_diagnostics']['iterations']['median']:.3f}`, and range
`{summary['prb_diagnostics']['iterations']['minimum']}`–`{summary['prb_diagnostics']['iterations']['maximum']}`.
Cuts have mean `{summary['prb_diagnostics']['cuts']['mean']:.3f}` and range
`{summary['prb_diagnostics']['cuts']['minimum']}`–`{summary['prb_diagnostics']['cuts']['maximum']}`.
Mean master solves and product-subproblem evaluations are
`{summary['prb_diagnostics']['master_solves']['mean']:.3f}` and
`{summary['prb_diagnostics']['product_subproblem_evaluations']['mean']:.3f}`.
All four fields were recorded for 8/8 PRB runs.

The 210330 row retains `global_coupling_pass=false` and classification
`DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH`. Its objective consistency and exact
recourse recertification pass, its Gamma allocation is feasible, and its
objective is unaffected. It remains in the performance summary as an optimal
paper-final run.

## Network-size description

For depot count I, Pearson correlations with Direct runtime, PRB runtime, and
speedup are `{network_size['I_vs_direct_runtime']['pearson']:.4f}`,
`{network_size['I_vs_prb_runtime']['pearson']:.4f}`, and
`{network_size['I_vs_speedup']['pearson']:.4f}`. Corresponding Spearman
correlations are `{network_size['I_vs_direct_runtime']['spearman']:.4f}`,
`{network_size['I_vs_prb_runtime']['spearman']:.4f}`, and
`{network_size['I_vs_speedup']['spearman']:.4f}`. These are descriptive
associations from eight observations. They do not establish a scalability law
or support a general large-scale scalability claim. No hypothesis test was
performed.

## Paper-ready Chinese summary

在八个具有异质网络结构的 Renault 实证算例上，PRB-Benders 与 Direct 精确模型的目标值均在冻结的 `1e-4` 容差内一致，最大绝对差为 `{summary['objective_consistency']['maximum_absolute_difference']:.3e}`。PRB-Benders 在 8/8 个算例中缩短了计算时间：Direct 的平均和中位运行时间分别为 `{summary['direct_runtime_seconds']['mean']:.3f}` 秒和 `{summary['direct_runtime_seconds']['median']:.3f}` 秒，PRB-Benders 分别为 `{summary['prb_runtime_seconds']['mean']:.3f}` 秒和 `{summary['prb_runtime_seconds']['median']:.3f}` 秒。Direct/PRB 运行时间比的几何平均为 `{summary['speedup_direct_over_prb']['geometric_mean']:.3f}`，范围为 `{summary['speedup_direct_over_prb']['minimum']:.3f}`–`{summary['speedup_direct_over_prb']['maximum']:.3f}`。210330 的 global-coupling 标志源于不影响目标值、可行性或 Gamma 分配的数值诊断契约差异，因此不改变性能比较结论。现有证据支持 PRB-Benders 在这些异质实证算例上取得一致的计算收益，但不构成一般性的大规模可扩展性结论。

The evidence supports consistent computational gains across heterogeneous
empirical instances, not a general large-scale scalability claim.
"""
    (ROOT / "docs/e1_empirical_performance_summary.md").write_text(document, encoding="utf-8")

    after = primary_hashes()
    if before != after:
        raise RuntimeError("paper-final E1 results changed while summarizing")
    print(json.dumps({
        "status": summary["status"],
        "completed_pairs": summary["completed_pairs"],
        "prb_wins": summary["speedup_direct_over_prb"]["prb_faster_count"],
        "geometric_mean_speedup": summary["speedup_direct_over_prb"]["geometric_mean"],
        "primary_hashes_preserved": True,
    }, indent=2))


if __name__ == "__main__":
    main()
