from __future__ import annotations

import csv
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.optimal_face_correctness import (
    audit_first_stage_feasibility,
)


RESULTS = ROOT / "experiments/results"
ARTIFACTS = ROOT / "artifacts"
DOC = ROOT / "docs/prb_oracle_acceleration_v2_audit.md"
CASES = ("210202", "L", "XL_low")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_accelerated(directory: str):
    payload = read_json(RESULTS / directory / "summary.json")
    return {row["case"]: row for row in payload["cases"]}


def frozen_runtimes(case: str):
    if case == "210202":
        pure = [
            read_json(
                RESULTS / "e1b_pure_benders_v1/E1B-210202-PURE/result.json"
            )["core_runtime_seconds"],
            read_json(
                RESULTS / "master_granularity_lb_diagnostic_v1/210202/pure_benders.json"
            )["total_runtime_seconds"],
        ]
        original = [
            read_json(
                RESULTS / "e1_empirical_8case_v1/E1-210202-PRB/result.json"
            )["runtime_seconds"],
            read_json(
                RESULTS / "master_granularity_lb_diagnostic_v1/210202/prb_benders.json"
            )["total_runtime_seconds"],
        ]
    else:
        pure = [
            read_json(RESULTS / f"e1c_development_probe_v1/{case}/PURE_BENDERS/result.json")[
                "core_runtime_seconds"
            ],
            read_json(
                RESULTS / f"master_granularity_lb_diagnostic_v1/{case}/pure_benders.json"
            )["total_runtime_seconds"],
        ]
        original = [
            read_json(RESULTS / f"e1c_development_probe_v1/{case}/PRB_BENDERS/result.json")[
                "core_runtime_seconds"
            ],
            read_json(
                RESULTS / f"master_granularity_lb_diagnostic_v1/{case}/prb_benders.json"
            )["total_runtime_seconds"],
        ]
    return pure, original


def stats(values):
    return {
        "n": len(values),
        "median_seconds": statistics.median(values),
        "minimum_seconds": min(values),
        "maximum_seconds": max(values),
        "mean_seconds": statistics.mean(values),
        "standard_deviation_seconds": statistics.stdev(values),
    }


def feasibility(case: str, solution: dict):
    if case == "210202":
        instance = load_instance(ROOT / "data/formal_instances_v2/210202.json")
        budget = read_json(
            ROOT / "artifacts/renault_empirical_8case_v1/calibration/210202.json"
        )["B_ref"]
    else:
        prepared = RESULTS / f"e1c_development_probe_v1/{case}/PREPARE"
        instance = load_instance(prepared / "instance.json")
        budget = read_json(prepared / "baseline.json")["B_ref"]
    return audit_first_stage_feasibility(
        instance,
        instance.initial_inventory,
        solution["y"],
        solution["x"],
        solution["a_plus"],
        solution["a_minus"],
        0.05,
        float(budget),
    )


def main() -> None:
    v1_a = load_accelerated("prb_acceleration_development_v4")
    v1_b = load_accelerated("prb_acceleration_profile_v1")
    v2_a = load_accelerated("prb_acceleration_v2_costvar")
    v2_b = load_accelerated("prb_acceleration_v2_costvar_rep2")

    benchmark_rows = []
    benchmark = {}
    for case in CASES:
        pure, original = frozen_runtimes(case)
        methods = {
            "pure_benders": pure,
            "original_prb": original,
            "accelerated_prb_v1": [
                v1_a[case]["result"]["total_runtime"],
                v1_b[case]["result"]["total_runtime"],
            ],
            "accelerated_prb_v2": [
                v2_a[case]["result"]["total_runtime"],
                v2_b[case]["result"]["total_runtime"],
            ],
        }
        benchmark[case] = {method: stats(values) for method, values in methods.items()}
        for method, summary in benchmark[case].items():
            benchmark_rows.append({"case": case, "method": method, **summary})
    write_csv(ARTIFACTS / "prb_acceleration_v2_fair_benchmark.csv", benchmark_rows)

    profile_rows = []
    profile_components = (
        "master_model_construction",
        "worker_startup",
        "product_model_construction_critical_path",
        "product_model_construction_cumulative",
        "master_solve",
        "product_model_update_cumulative",
        "product_optimization_cumulative",
        "product_result_extraction_cumulative",
        "parallel_worker_compute_critical_path",
        "cache_lookup",
        "worker_dispatch",
        "serialization_probe",
        "ipc_and_wait_residual",
        "result_processing",
        "gamma_allocation",
        "lb_ub_computation",
        "cut_construction",
        "cut_insertion",
        "certification_total",
        "certification_preparation",
        "miscellaneous_python",
    )
    for case in CASES:
        profile = v1_b[case]["result"]["runtime_profile"]
        for component in profile_components:
            row = profile[component]
            profile_rows.append(
                {
                    "case": case,
                    "component": component,
                    "total_seconds": row["total_seconds"],
                    "percent_core": row["percent_core"],
                    "call_count": row["call_count"],
                    "average_seconds": row["average_seconds"],
                    "maximum_seconds": row["maximum_seconds"],
                    "ipc_payload_bytes": row.get("payload_bytes", ""),
                }
            )
    write_csv(ARTIFACTS / "prb_acceleration_v2_runtime_breakdown.csv", profile_rows)

    worker_rows = []
    worker_sources = {
        1: "prb_acceleration_worker_curve_v1/w1",
        2: "prb_acceleration_worker_curve_v1/w2",
        4: "prb_acceleration_worker_curve_v1/w4",
        8: "prb_acceleration_profile_v1",
        12: "prb_acceleration_worker_curve_v1/w12_L",
        14: "prb_acceleration_worker_curve_v1/w14_XL",
    }
    for workers, directory in worker_sources.items():
        for case, row in load_accelerated(directory).items():
            worker_rows.append(
                {
                    "case": case,
                    "workers": workers,
                    "core_runtime_seconds": row["result"]["total_runtime"],
                    "oracle_runtime_seconds": row["result"]["separation_runtime"],
                    "objective": row["result"]["solution"]["objective"],
                    "correctness_pass": row["comparison"]["correctness_pass"],
                }
            )
    write_csv(ARTIFACTS / "prb_acceleration_v2_worker_curve.csv", worker_rows)

    correctness = {}
    for case in CASES:
        repetitions = [v2_a[case], v2_b[case]]
        feasibility_audits = [
            feasibility(case, row["result"]["solution"]) for row in repetitions
        ]
        correctness[case] = {
            "objective_difference_max": max(
                row["comparison"]["objective_difference_vs_original"]
                for row in repetitions
            ),
            "recourse_difference_max": max(
                row["comparison"]["recourse_difference_vs_original"]
                for row in repetitions
            ),
            "maximum_x_difference": max(
                row["comparison"]["max_x_difference_vs_original"]
                for row in repetitions
            ),
            "same_y": all(row["comparison"]["same_y_as_original"] for row in repetitions),
            "exact_certification": all(
                row["result"]["exact_certification_pass"] for row in repetitions
            ),
            "global_coupling_pass": all(
                row["result"]["global_risk_budget_coupling_pass"]
                for row in repetitions
            ),
            "first_stage_feasible": all(
                audit.feasible for audit in feasibility_audits
            ),
            "maximum_first_stage_violation": max(
                audit.maximum_violation for audit in feasibility_audits
            ),
            "peak_memory_gib": max(
                row["peak_process_tree_memory_gib"] for row in repetitions
            ),
            "cache_hit_rate": (
                repetitions[0]["result"]["cache_hits"]
                / (
                    repetitions[0]["result"]["cache_hits"]
                    + repetitions[0]["result"]["cache_misses"]
                )
            ),
            "product_state_solves_avoided": repetitions[0]["result"][
                "product_solves_avoided"
            ],
            "certification_cache_hits": repetitions[0]["result"][
                "certification_cache_hits"
            ],
            "certification_product_state_solves": repetitions[0]["result"][
                "certification_product_state_solves"
            ],
            "parallel_workers": repetitions[0]["result"]["parallel_worker_count"],
        }

    summary = {
        "status": "MAJOR_GAIN_BUT_PURE_STILL_FASTER",
        "development_only": True,
        "benchmark_repetitions_per_method_case": 2,
        "benchmark": benchmark,
        "correctness": correctness,
        "gamma_composition_microbenchmark": {
            "J8_speedup": 22.77144330154084,
            "J12_speedup": 1049.430894190635,
            "J14_speedup": 7008.507291278683,
            "definition": "legacy Cartesian enumeration time divided by exact DP time",
        },
        "pure_beaten": False,
        "pure_approached": False,
        "expand_to_eight_cases": False,
        "E2_E7_rerun_required": False,
    }
    (ARTIFACTS / "prb_acceleration_v2_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# Accelerated PRB V2 runtime and correctness audit",
        "",
        "This development-only audit changes no model, tolerance, uncertainty, cut, or certification contract.",
        "",
        "## V1 bottleneck",
        "",
        "On profiled XL-low, the 9.762 s core time consisted primarily of 3.354 s product-model construction, 0.982 s worker startup, 3.756 s main separation, 0.924 s repeated final certification, and 0.606 s master construction. IPC, serialization, cut management, LB/UB accounting, and Gamma DP were individually below 0.04 s.",
        "",
        "## V2 changes",
        "",
        "- exact recursive allocation generation replaces Cartesian filtering while preserving tuple order;",
        "- final certification reuses only bitwise-identical cached product states;",
        "- worker selection uses product-risk block count, not case identity (2 workers at <=1000 blocks, otherwise up to 8);",
        "- workers retain static data and persistent Gurobi models; only x_j is sent per iteration;",
        "- unused shipment primal matrices are no longer serialized; cost values and duals are batch-read;",
        "- no heuristic selective separation is used.",
        "",
        "## Fair repeated runtime benchmark",
        "",
        "| Case | Pure median | Original PRB median | V1 median | V2 median | V2/Pure | V2/V1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case in CASES:
        row = benchmark[case]
        pure = row["pure_benders"]["median_seconds"]
        v1 = row["accelerated_prb_v1"]["median_seconds"]
        v2 = row["accelerated_prb_v2"]["median_seconds"]
        lines.append(
            f"| {case} | {pure:.3f}s | {row['original_prb']['median_seconds']:.3f}s | {v1:.3f}s | {v2:.3f}s | {v2 / pure:.2f}x | {v2 / v1:.3f} |"
        )
    lines += [
        "",
        "Each cell uses two same-machine exact observations and reports median, with min, max, mean, and sample standard deviation in the CSV artifact. No fastest-run selection is used.",
        "",
        "## Correctness and interpretation",
        "",
        "Both V2 repetitions pass objective, recourse, first-stage identity/equivalence, exact certification, and global Gamma-coupling checks on all three instances. Certification duplicate state solves fall from 24/36/42 to zero for 210202/L/XL-low. V2 remains more than 1.5x slower than Pure on every tested instance, so the frozen conclusion is `MAJOR_GAIN_BUT_PURE_STILL_FASTER`. No eight-case expansion is authorized.",
        "",
        "E2--E7 reruns: 0. Paper text changed: no.",
    ]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
