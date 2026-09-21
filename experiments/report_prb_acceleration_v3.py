from __future__ import annotations

import csv
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments/results"
ARTIFACTS = ROOT / "artifacts"
CASES = ("210202", "L", "XL_low")
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.optimal_face_correctness import (
    audit_first_stage_feasibility,
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_summary(path: str):
    payload = read_json(RESULTS / path / "summary.json")
    return {row["case"]: row for row in payload["cases"]}


def stats(values):
    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "minimum": min(values),
        "maximum": max(values),
        "standard_deviation": statistics.stdev(values),
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
    v2_runs = (
        load_summary("prb_acceleration_v2_costvar"),
        load_summary("prb_acceleration_v2_costvar_rep2"),
    )
    v3_first = {
        **load_summary("prb_acceleration_v3_probe_210202_thread_rep1"),
        **load_summary("prb_acceleration_v3_probe_large_thread_rep1"),
    }
    v3_runs = (v3_first, load_summary("prb_acceleration_v3_thread_rep2"))
    v2_summary = read_json(ARTIFACTS / "prb_acceleration_v2_summary.json")
    state_audit = read_json(ARTIFACTS / "prb_v3_product_state_audit.json")
    solver_audit = read_json(ARTIFACTS / "prb_v3_solver_profile_audit.json")

    rows = []
    summary = {}
    for case in CASES:
        pure = v2_summary["benchmark"][case]["pure_benders"]
        v2_core = [run[case]["result"]["total_runtime"] for run in v2_runs]
        v2_oracle = [run[case]["result"]["separation_runtime"] for run in v2_runs]
        v2_build = [
            run[case]["result"]["oracle_model_build_runtime"] for run in v2_runs
        ]
        v2_optimization = [
            run[case]["result"]["runtime_profile"][
                "product_optimization_cumulative"
            ]["total_seconds"]
            for run in v2_runs
        ]
        v3_core = [run[case]["result"]["total_runtime"] for run in v3_runs]
        v3_oracle = [run[case]["result"]["separation_runtime"] for run in v3_runs]
        v3_build = [
            run[case]["result"]["oracle_model_build_runtime"] for run in v3_runs
        ]
        v3_optimization = [
            run[case]["result"]["runtime_profile"][
                "product_optimization_cumulative"
            ]["total_seconds"]
            for run in v3_runs
        ]
        v3_certification = [
            run[case]["result"]["certification_runtime"] for run in v3_runs
        ]
        v3_memory = [run[case]["peak_process_tree_memory_gib"] for run in v3_runs]
        objective_difference = max(
            run[case]["comparison"]["objective_difference_vs_original"]
            for run in v3_runs
        )
        recourse_difference = max(
            run[case]["comparison"]["recourse_difference_vs_original"]
            for run in v3_runs
        )
        x_difference = max(
            run[case]["comparison"]["max_x_difference_vs_original"]
            for run in v3_runs
        )
        feasibility_audits = [
            feasibility(case, run[case]["result"]["solution"]) for run in v3_runs
        ]
        record = {
            "case": case,
            "repetitions": 2,
            "pure_median_core_seconds": pure["median_seconds"],
            **{f"v2_core_{key}_seconds": value for key, value in stats(v2_core).items()},
            "v2_oracle_median_seconds": statistics.median(v2_oracle),
            "v2_build_median_seconds": statistics.median(v2_build),
            "v2_product_optimization_median_seconds": statistics.median(
                v2_optimization
            ),
            **{f"v3_core_{key}_seconds": value for key, value in stats(v3_core).items()},
            **{f"v3_oracle_{key}_seconds": value for key, value in stats(v3_oracle).items()},
            **{f"v3_build_{key}_seconds": value for key, value in stats(v3_build).items()},
            **{
                f"v3_product_optimization_{key}_seconds": value
                for key, value in stats(v3_optimization).items()
            },
            **{
                f"v3_certification_{key}_seconds": value
                for key, value in stats(v3_certification).items()
            },
            "v3_peak_memory_gib": max(v3_memory),
            "v3_over_pure_ratio": statistics.median(v3_core)
            / pure["median_seconds"],
            "v3_over_v2_ratio": statistics.median(v3_core)
            / statistics.median(v2_core),
            "construction_reduction_vs_v2": 1.0
            - statistics.median(v3_build) / statistics.median(v2_build),
            "product_optimization_reduction_vs_v2": 1.0
            - statistics.median(v3_optimization)
            / statistics.median(v2_optimization),
            "maximum_objective_difference": objective_difference,
            "maximum_recourse_difference": recourse_difference,
            "maximum_x_difference": x_difference,
            "same_y": all(
                run[case]["comparison"]["same_y_as_original"] for run in v3_runs
            ),
            "first_stage_feasible": all(
                audit.feasible for audit in feasibility_audits
            ),
            "maximum_first_stage_violation": max(
                audit.maximum_violation for audit in feasibility_audits
            ),
            "exact_certification": all(
                run[case]["result"]["exact_certification_pass"] for run in v3_runs
            ),
            "global_coupling_pass": all(
                run[case]["result"]["global_risk_budget_coupling_pass"]
                for run in v3_runs
            ),
            "iterations": v3_runs[0][case]["result"]["master_solve_count"],
            "cuts": v3_runs[0][case]["result"]["unique_product_cuts"],
        }
        rows.append(record)
        summary[case] = record

    csv_path = ARTIFACTS / "prb_acceleration_v3_benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "status": "NO_SAFE_STRUCTURAL_SIMPLIFICATION",
        "development_only": True,
        "structured_state_audit": {
            key: value for key, value in state_audit.items() if key != "rows"
        },
        "solver_profile_audit": {
            "status": solver_audit["status"],
            "selected_profile": solver_audit["selected_profile"],
            "selection_rule": solver_audit["selection_rule"],
        },
        "benchmark": summary,
        "structured_oracle_promoted": False,
        "expand_to_eight_cases": False,
        "E2_E7_rerun_required": False,
    }
    (ARTIFACTS / "prb_acceleration_v3_summary.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# PRB product-subproblem structure audit",
        "",
        "This is a development-only implementation audit. It changes no model, uncertainty set, master, cut, tolerance, or certification contract.",
        "",
        "## Exact product-state formulation",
        "",
        "For product `j`, inventory vector `x_j`, and a fixed shocked-region set `S` with `|S|=g`, demand is `d_r = dbar_rj + dhat_rj 1[r in S]`. The recourse variables are shipments `q_ir >= 0`, shortages `u_r >= 0`, and service violation `e >= 0`. It minimizes `sum_ir c_irj q_ir + sum_r p_rj u_r + s_j e`, subject to `sum_i q_ir + u_r >= d_r`, `sum_r q_ir <= x_ij`, and `sum_r u_r - e <= (1-alpha_j) sum_r d_r`.",
        "",
        "With demand duals `pi_r >= 0`, supply duals `mu_i <= 0`, and service dual `sigma <= 0`, the dual maximizes `sum_r d_r pi_r + sum_i x_ij mu_i + A sigma`, subject to `pi_r + mu_i <= c_irj`, `pi_r + sigma <= p_rj`, and `-sigma <= s_j`. The Benders cut has intercept `sum_r d_r pi_r + A sigma` and inventory coefficients `mu_i`.",
        "",
        "For fixed `g`, `V_jg(x_j)` is the maximum recourse value over all `g`-region shock patterns. The cut returned by the maximizing pattern is therefore a globally valid supporting cut for `V_jg` and is tight at the generation point.",
        "",
        "## Exploitable structure and decision",
        "",
        "Each fixed-pattern LP is a continuous capacitated transportation/min-cost-flow problem. The service term can be represented by an allowance-shortage source of capacity `A` with regional costs `p_rj`, plus an unlimited excess-shortage source with costs `p_rj+s_j`. Arbitrary depot-region transport costs, shared depot capacities, and the shared allowance pool prevent independent sorting or continuous-knapsack evaluation.",
        "",
        "A custom min-cost-flow implementation would also have to return numerically valid capacity duals under degeneracy. No repository implementation provides that contract, so no closed-form, sorting, or custom-network solver safely replaces Gurobi. The exact sparse-matrix prototype retains Gurobi and batches all scenario blocks; it is exact but slower on L and XL-low and is not promoted.",
        "",
        "V2 already maintains one Gurobi model per product, not one model per `g`. It contains `1 + R + R(R-1)/2` independent scenario blocks at Gamma=2. V3 keeps one model per product but replaces per-block Python construction with one sparse matrix insertion and bulk RHS/value/dual operations.",
        "",
        "## Exactness audit",
        "",
        f"The audit covered {state_audit['product_inventory_vectors']} product/inventory vectors and {state_audit['product_risk_states']} `(product,x_j,g)` states. Maximum value, cut-tightness, and strong-duality errors were respectively `{state_audit['maximum_value_difference']:.3e}`, `{state_audit['maximum_cut_tightness_error']:.3e}`, and `{state_audit['maximum_strong_duality_error']:.3e}`. Maximum demand-dual, supply-dual, cut-intercept, and cut-slope differences from V2 were `{state_audit['maximum_demand_dual_difference']:.3e}`, `{state_audit['maximum_supply_dual_difference']:.3e}`, `{state_audit['maximum_cut_alpha_difference']:.3e}`, and `{state_audit['maximum_cut_beta_difference']:.3e}`. Every dual was feasible and all worst patterns matched V2.",
        "",
        "## Solver micro-audit",
        "",
        "The predeclared profiles were Auto, primal simplex with Presolve 0/1, and dual simplex with Presolve 0/1/2, all with unchanged formal feasibility and optimality tolerances, Threads=1, and LPWarmStart=2. Auto had the lowest total solve time on the deterministic XL-low sample and remains selected; no solver parameter is changed.",
        "",
        "## Development benchmark",
        "",
        "| Case | Pure median | V2 median | V3 median | V3/Pure | V3/V2 | V3 oracle median | Peak GiB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case']} | {row['pure_median_core_seconds']:.3f}s | {row['v2_core_median_seconds']:.3f}s | {row['v3_core_median_seconds']:.3f}s | {row['v3_over_pure_ratio']:.2f}x | {row['v3_over_v2_ratio']:.2f}x | {row['v3_oracle_median_seconds']:.3f}s | {row['v3_peak_memory_gib']:.2f} |"
        )
    lines += [
        "",
        "All six end-to-end V3 runs match the frozen objective and recourse within the existing formal tolerance, retain the same `y`, have only floating-point-scale `x` differences, and pass global coupling and exact certification. The prototype nevertheless increases L and XL-low time because sparse-matrix/environment construction and full primal/dual extraction outweigh fewer Python model-building calls.",
        "",
        "Relative to V2, the measured construction reductions for 210202/L/XL-low are "
        + ", ".join(
            f"{100.0 * row['construction_reduction_vs_v2']:.1f}%"
            for row in rows
        )
        + ", and cumulative product-optimization reductions are "
        + ", ".join(
            f"{100.0 * row['product_optimization_reduction_vs_v2']:.1f}%"
            for row in rows
        )
        + ". Negative values denote regressions. Static scenario coefficients and sparse indices are fully precomputed, but this does not yield a net large-instance gain.",
        "",
        "Final classification: `NO_SAFE_STRUCTURAL_SIMPLIFICATION`.",
        "",
        "E2--E7 reruns: 0. Paper text changed: no. Eight-case expansion: no.",
    ]
    (ROOT / "docs/prb_product_subproblem_structure_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
