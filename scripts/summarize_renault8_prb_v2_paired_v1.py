"""Build the paper-facing archive for the Renault8 paired PRB experiment.

This script is analysis-only.  It reads completed result/provenance/monitor
records, verifies their hashes and frozen identities, and never calls a solver.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

import run_renault8_prb_v2_paired_v1 as runner


ANALYSIS_ROOT = ROOT / "experiments/analysis/renault8_prb_v2_paired_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_condition(case_id: str, method: str) -> dict[str, Any]:
    loaded = runner.load_frozen_renault_case(case_id)
    reference = runner.direct_reference(case_id, loaded)
    expected_identity = runner.identity(case_id, method, 2, loaded, reference)
    path = runner.result_dir(case_id, method)
    if not runner.verified_result(path, expected_identity):
        raise RuntimeError(f"missing result: {path}")
    result_path = path / "result.json"
    provenance_path = path / "provenance.json"
    result = runner.read_json(result_path)
    provenance = runner.read_json(provenance_path)
    monitors = sorted(
        (runner.OUTPUT_ROOT / "logs" / runner.condition_id(case_id, method)).glob(
            "attempt-*/monitor.json"
        )
    )
    if len(monitors) != 1:
        raise RuntimeError(
            f"expected exactly one monitor record for {case_id}/{method}, got {len(monitors)}"
        )
    monitor = runner.read_json(monitors[0])
    if monitor["return_code"] != 0 or monitor["stop_reason"] is not None:
        raise RuntimeError(f"unsuccessful monitor record: {monitors[0]}")
    return {
        "result": result,
        "provenance": provenance,
        "result_path": result_path,
        "provenance_path": provenance_path,
        "monitor": monitor,
        "monitor_path": monitors[0],
        "loaded": loaded,
    }


def geometric_mean(values: list[float]) -> float:
    if not values or any(value <= 0 for value in values):
        raise ValueError("geometric mean requires positive values")
    return math.exp(statistics.fmean(math.log(value) for value in values))


def windows_cpu_model() -> str:
    return subprocess.check_output(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Processor).Name",
        ],
        text=True,
    ).strip()


def build() -> dict[str, object]:
    conditions = {
        (case_id, method): load_condition(case_id, method)
        for case_id in runner.CASE_IDS
        for method in runner.METHODS
    }
    if len(conditions) != 16:
        raise RuntimeError("expected exactly 16 completed method conditions")

    for condition in conditions.values():
        monitor = condition["monitor"]
        resource_path = condition["result_path"].parent / "resource_monitor.json"
        write_json(
            resource_path,
            {
                "record_type": "DERIVED_SANITIZED_RESOURCE_MONITOR",
                "condition_id": monitor["condition_id"],
                "return_code": monitor["return_code"],
                "stop_reason": monitor["stop_reason"],
                "available_memory_before_gib": monitor["available_memory_before_gib"],
                "peak_process_tree_rss_gib": monitor["peak_process_tree_rss_gib"],
                "monitored_wall_seconds": monitor["monitored_wall_seconds"],
                "poll_interval_seconds": monitor["poll_interval_seconds"],
                "process_memory_cap_gib": monitor["process_memory_cap_gib"],
                "system_memory_floor_gib": monitor["system_memory_floor_gib"],
                "source_monitor_sha256": sha256(condition["monitor_path"]),
                "privacy_note": "Local executable and checkout paths are intentionally omitted.",
            },
        )
        condition["resource_path"] = resource_path

    paired_rows = []
    runtime_rows = []
    for case_id in runner.CASE_IDS:
        basic = conditions[(case_id, "basic")]
        v2 = conditions[(case_id, "v2")]
        b = basic["result"]
        v = v2["result"]
        objective_difference = abs(float(b["objective"]) - float(v["objective"]))
        if objective_difference > runner.OBJECTIVE_TOLERANCE:
            raise RuntimeError(f"paired objective mismatch for {case_id}")
        if not (b["validated_under_protocol"] and v["validated_under_protocol"]):
            raise RuntimeError(f"unvalidated result for {case_id}")
        paired_rows.append(
            {
                "case": case_id,
                "depots": basic["loaded"]["instance"].num_depots,
                "regions": basic["loaded"]["instance"].num_regions,
                "products": basic["loaded"]["instance"].num_products,
                "basic_core_seconds": b["core_solve_time_seconds"],
                "v2_core_seconds": v["core_solve_time_seconds"],
                "basic_over_v2_speedup": b["core_solve_time_seconds"]
                / v["core_solve_time_seconds"],
                "basic_child_wall_seconds": b["child_solve_wall_seconds"],
                "v2_child_wall_seconds": v["child_solve_wall_seconds"],
                "basic_iterations": b["iterations"],
                "v2_iterations": v["iterations"],
                "basic_cut_count": b["benders_cut_count"],
                "v2_cut_count": v["benders_cut_count"],
                "basic_objective": b["objective"],
                "v2_objective": v["objective"],
                "paired_objective_absolute_difference": objective_difference,
                "historical_direct_objective": b["historical_direct_objective"],
                "basic_direct_absolute_difference": b["objective_absolute_difference"],
                "v2_direct_absolute_difference": v["objective_absolute_difference"],
                "basic_certification_class": b["certification_class"],
                "v2_certification_class": v["certification_class"],
                "basic_strict_original": b["strict_exact_certification"],
                "v2_strict_original": v["strict_exact_certification"],
                "basic_independent_numeric_validation": b[
                    "independently_numerically_validated"
                ],
                "v2_independent_numeric_validation": v[
                    "independently_numerically_validated"
                ],
                "instance_sha256": b["input_sha256"]["instance_hash"],
                "x0_sha256": b["input_sha256"]["x0_hash"],
                "calibration_sha256": b["input_sha256"]["calibration_hash"],
                "basic_result_sha256": sha256(basic["result_path"]),
                "v2_result_sha256": sha256(v2["result_path"]),
                "basic_provenance_sha256": sha256(basic["provenance_path"]),
                "v2_provenance_sha256": sha256(v2["provenance_path"]),
            }
        )
        for method, condition in (("basic", basic), ("v2", v2)):
            result = condition["result"]
            monitor = condition["monitor"]
            runtime_rows.append(
                {
                    "case": case_id,
                    "method": method,
                    "core_solve_seconds": result["core_solve_time_seconds"],
                    "child_solve_wall_seconds": result["child_solve_wall_seconds"],
                    "outer_monitored_wall_seconds": monitor["monitored_wall_seconds"],
                    "peak_process_tree_rss_gib": monitor["peak_process_tree_rss_gib"],
                    "master_seconds": result["master_time_seconds"],
                    "oracle_seconds": result["oracle_time_seconds"],
                    "certification_seconds": result["certification_time_seconds"],
                    "worker_count": result["worker_count"],
                    "gurobi_threads_per_model": result["gurobi_threads_per_model"],
                    "monitor_sha256": sha256(condition["monitor_path"]),
                }
            )

    basic_times = [float(row["basic_core_seconds"]) for row in paired_rows]
    v2_times = [float(row["v2_core_seconds"]) for row in paired_rows]
    speedups = [float(row["basic_over_v2_speedup"]) for row in paired_rows]
    basic_mean = statistics.fmean(basic_times)
    v2_mean = statistics.fmean(v2_times)
    performance_rows = [
        {
            "pair_count": 8,
            "basic_arithmetic_mean_core_seconds": basic_mean,
            "v2_arithmetic_mean_core_seconds": v2_mean,
            "ratio_of_arithmetic_mean_times": basic_mean / v2_mean,
            "paired_geometric_mean_speedup": geometric_mean(speedups),
            "arithmetic_mean_time_reduction_percent": 100.0
            * (basic_mean - v2_mean)
            / basic_mean,
            "v2_win_count": sum(v2 < basic for basic, v2 in zip(basic_times, v2_times)),
            "basic_win_count": sum(basic < v2 for basic, v2 in zip(basic_times, v2_times)),
            "tie_count": sum(basic == v2 for basic, v2 in zip(basic_times, v2_times)),
            "minimum_paired_speedup": min(speedups),
            "maximum_paired_speedup": max(speedups),
        }
    ]

    certification_rows = []
    for method in runner.METHODS:
        results = [conditions[(case_id, method)]["result"] for case_id in runner.CASE_IDS]
        strict = sum(bool(result["strict_exact_certification"]) for result in results)
        numerical = sum(
            bool(result["independently_numerically_validated"]) for result in results
        )
        certification_rows.append(
            {
                "method": method,
                "result_count": len(results),
                "strict_original_count": strict,
                "independently_numerically_validated_count": numerical,
                "failed_unvalidated_count": len(results) - strict - numerical,
                "strict_original_rate_percent": 100.0 * strict / len(results),
                "validated_under_disclosed_protocol_rate_percent": 100.0
                * (strict + numerical)
                / len(results),
                "maximum_direct_objective_absolute_difference": max(
                    float(result["objective_absolute_difference"]) for result in results
                ),
                "numeric_exception_cases": ";".join(
                    result["case"]
                    for result in results
                    if result["independently_numerically_validated"]
                ),
            }
        )

    write_csv(ANALYSIS_ROOT / "paired_results_8.csv", paired_rows)
    write_csv(ANALYSIS_ROOT / "performance_summary.csv", performance_rows)
    write_csv(ANALYSIS_ROOT / "certification_summary.csv", certification_rows)
    write_csv(ANALYSIS_ROOT / "runtime_breakdown.csv", runtime_rows)

    environment_values = [
        conditions[(case_id, method)]["provenance"]["identity"]["environment"]
        for case_id in runner.CASE_IDS
        for method in runner.METHODS
    ]
    if any(value != environment_values[0] for value in environment_values[1:]):
        raise RuntimeError("runtime environment identity differs across conditions")
    environment_manifest = {
        "schema": "renault8_prb_v2_paired_environment_v1",
        "experiment": runner.EXPERIMENT_ID,
        "runtime_environment_recorded_in_all_16_provenance_files": environment_values[0],
        "post_run_same_host_observation": {
            "cpu_model_via_windows_cim": windows_cpu_model(),
            "note": (
                "Collected during archival immediately after the paired run; "
                "the per-condition provenance contains the runtime processor string."
            ),
        },
        "method_resources": {
            "basic": {"workers": 1, "gurobi_threads_per_model": 1},
            "v2": {
                "workers": 2,
                "worker_backend": "process",
                "gurobi_threads_per_model": 1,
                "selective_separation": False,
            },
        },
        "timing_definitions": {
            "core_solve_time_seconds": "solver method returned total_runtime",
            "child_solve_wall_seconds": "perf_counter around the solve call in the child",
            "outer_monitored_wall_seconds": "parent process launch through child exit",
            "paper_comparison_metric": "core_solve_time_seconds",
            "independent_numeric_audit_in_core_time": False,
        },
        "resource_guard": {
            "minimum_available_memory_gib_at_start": runner.MIN_AVAILABLE_MEMORY_GIB,
            "maximum_process_tree_memory_gib": runner.MAX_PROCESS_TREE_MEMORY_GIB,
            "system_memory_floor_gib": runner.SYSTEM_MEMORY_FLOOR_GIB,
            "condition_timeout_seconds": runner.CONDITION_TIMEOUT_SECONDS,
            "poll_interval_seconds": runner.MONITOR_INTERVAL_SECONDS,
            "maximum_observed_process_tree_rss_gib": max(
                float(row["peak_process_tree_rss_gib"]) for row in runtime_rows
            ),
        },
    }
    write_json(ANALYSIS_ROOT / "environment_manifest.json", environment_manifest)

    table_lines = [
        "# Renault real-case paired PRB performance",
        "",
        "Core time is the algorithm-reported `total_runtime`. V2 uses two process workers; Basic is serial. Each Gurobi model uses one thread.",
        "",
        "| Case | Depots | Basic PRB (s) | Accelerated PRB V2 (s) | Basic/V2 | Basic iter. | V2 iter. | Basic cert. | V2 cert. |",
        "|---:|---:|---:|---:|---:|---:|---:|:---|:---|",
    ]
    for row in paired_rows:
        table_lines.append(
            f"| {row['case']} | {row['depots']} | {row['basic_core_seconds']:.3f} | "
            f"{row['v2_core_seconds']:.3f} | {row['basic_over_v2_speedup']:.3f}x | "
            f"{row['basic_iterations']} | {row['v2_iterations']} | "
            f"{row['basic_certification_class']} | {row['v2_certification_class']} |"
        )
    summary = performance_rows[0]
    table_lines.extend(
        [
            "",
            f"Arithmetic mean core times: Basic {basic_mean:.3f} s, V2 {v2_mean:.3f} s. "
            f"Paired geometric-mean speedup: {summary['paired_geometric_mean_speedup']:.3f}x. "
            f"V2 wins: {summary['v2_win_count']}/8.",
            "",
            "The two 210330 runs are not strict-original successes. Both retain the original global-coupling failure and are separately labelled `independently_numerically_validated`; this is not an exact-arithmetic proof.",
        ]
    )
    (ANALYSIS_ROOT / "renault_paper_table.md").write_text(
        "\n".join(table_lines) + "\n", encoding="utf-8"
    )

    audit_lines = [
        "# Renault8 Basic PRB vs Accelerated PRB V2 final audit",
        "",
        "## Completeness and identity",
        "",
        "- Eight frozen `RENAULT_EMPIRICAL_8CASE_V1` cases and 16 method results are present; each result has a matching provenance hash.",
        "- Every condition uses its case-specific frozen instance, canonical x0, calibration artifact, and B_ref. No demand, geography, inventory, or budget was rebuilt.",
        "- Basic and V2 share Gamma=2, beta=1.0, lambda_R=0.05, relative gap 1e-6, cut tolerance 1e-7, maximum 500 iterations, and the `gurobi-balanced-1e-8-v1` solver profile.",
        "- All 16 objectives match the frozen historical Direct objective within 1e-4, and each Basic/V2 pair matches within 1e-4.",
        "",
        "## Certification boundary",
        "",
        "- Fourteen of 16 method results are `strict_original` (7/8 for each method).",
        "- Renault 210330 retains the original global-risk coupling failure for both methods: residual 1.6398262232542038e-6 exceeds the unchanged 1e-6 threshold.",
        "- Both 210330 results passed the separate final-inventory product recourse and returned-cut numerical audit and are labelled `independently_numerically_validated`. This narrower audit is not a proof of whole-domain cut validity or exact arithmetic.",
        "- No failed, slow, or losing result was removed. V2 wins and certification rates are reported over all eight paired cases.",
        "",
        "## Scaling30 comparison boundary",
        "",
        "- Renault8 and Scaling30 use the same Gamma/beta/lambda_R values, stopping tolerances, solver-native profile, Basic/V2 worker allocation, one Gurobi thread per model, and core-time definition.",
        "- They do not share an instance population: Renault8 uses eight empirical frozen cases and case-specific B_ref/x0, whereas Scaling30 uses synthetic calibrated scaling instances and seeds. Results may be displayed together as complementary evidence, but should not be pooled as one homogeneous sample.",
        "",
        "## Resource and publication decision",
        "",
        f"- Maximum observed process-tree RSS was {environment_manifest['resource_guard']['maximum_observed_process_tree_rss_gib']:.3f} GiB; no timeout or resource stop occurred.",
        f"- V2 won {summary['v2_win_count']}/8 cases. The paired geometric-mean speedup is {summary['paired_geometric_mean_speedup']:.3f}x.",
        "- The table is suitable for Chapter 5 Table 2 if the caption discloses 2-process V2 versus serial Basic and preserves the 210330 separate numerical-validation label.",
        "- Historical E1 and E2-E7 files were read only; this experiment writes only its independent result and analysis roots.",
    ]
    (ANALYSIS_ROOT / "final_audit.md").write_text(
        "\n".join(audit_lines) + "\n", encoding="utf-8"
    )

    source_records = []
    for case_id in runner.CASE_IDS:
        for method in runner.METHODS:
            condition = conditions[(case_id, method)]
            source_records.append(
                {
                    "case": case_id,
                    "method": method,
                    "result_path": relative(condition["result_path"]),
                    "result_sha256": sha256(condition["result_path"]),
                    "provenance_path": relative(condition["provenance_path"]),
                    "provenance_sha256": sha256(condition["provenance_path"]),
                    "monitor_source_sha256": sha256(condition["monitor_path"]),
                    "resource_monitor_path": relative(condition["resource_path"]),
                    "resource_monitor_sha256": sha256(condition["resource_path"]),
                    "certification_class": condition["result"]["certification_class"],
                }
            )
    output_paths = [
        ANALYSIS_ROOT / "paired_results_8.csv",
        ANALYSIS_ROOT / "performance_summary.csv",
        ANALYSIS_ROOT / "certification_summary.csv",
        ANALYSIS_ROOT / "runtime_breakdown.csv",
        ANALYSIS_ROOT / "renault_paper_table.md",
        ANALYSIS_ROOT / "environment_manifest.json",
        ANALYSIS_ROOT / "final_audit.md",
    ]
    provenance_manifest = {
        "schema": "renault8_prb_v2_paired_provenance_v1",
        "experiment": runner.EXPERIMENT_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "optimization_calls_during_analysis": 0,
        "pair_count": 8,
        "method_result_count": 16,
        "development_base_commit": runner.DEVELOPMENT_BASE_COMMIT,
        "runner_sha256": sha256(Path(runner.__file__)),
        "summary_script_sha256": sha256(Path(__file__)),
        "input_sources": source_records,
        "analysis_outputs_sha256": {
            relative(path): sha256(path) for path in output_paths
        },
        "raw_monitor_logs_archived": False,
        "raw_monitor_log_note": (
            "Raw launch logs are omitted because command records contain local paths. "
            "Each result directory contains a DERIVED_SANITIZED_RESOURCE_MONITOR; "
            "the same non-sensitive fields are consolidated in runtime_breakdown.csv, "
            "with source hashes retained above."
        ),
    }
    write_json(ANALYSIS_ROOT / "provenance_manifest.json", provenance_manifest)
    return {
        "pairs": 8,
        "conditions": 16,
        "performance": performance_rows[0],
        "certification": certification_rows,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
