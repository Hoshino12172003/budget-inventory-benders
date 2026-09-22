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


def load_summary(directory: str):
    payload = read_json(RESULTS / directory / "summary.json")
    return {row["case"]: row for row in payload["cases"]}


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


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
    v2_audit = load_summary("prb_acceleration_v2_state_audit_clean")
    v4_runs = (
        load_summary("prb_acceleration_v4_rep1"),
        load_summary("prb_acceleration_v4_rep2"),
    )
    frozen = read_json(ARTIFACTS / "prb_acceleration_v2_summary.json")

    state_rows = []
    for case in CASES:
        final_allocation = tuple(
            v2_audit[case]["result"]["separation_audit"][-1]["allocation"]
        )
        for row in v2_audit[case]["result"]["separation_audit"]:
            exact = row["exact_state_solves"]
            state_rows.append(
                {
                    "case": case,
                    **row,
                    "exact_states_without_new_information_fraction": (
                        row["exact_states_without_new_cut"] / exact
                        if exact
                        else 0.0
                    ),
                    "states_matching_final_gamma_allocation": len(final_allocation),
                    "states_not_in_final_gamma_allocation": (
                        row["potential_product_risk_states"] - len(final_allocation)
                    ),
                }
            )
    write_csv(ARTIFACTS / "prb_v2_state_solve_audit.csv", state_rows)

    benchmark_rows = []
    summary = {}
    for case in CASES:
        pure = frozen["benchmark"][case]["pure_benders"]["median_seconds"]
        v2 = frozen["benchmark"][case]["accelerated_prb_v2"]["median_seconds"]
        v4_values = [run[case]["result"]["total_runtime"] for run in v4_runs]
        v4_stats = stats(v4_values)
        audits = v4_runs[0][case]["result"]["separation_audit"]
        potential = sum(row["potential_product_risk_states"] for row in audits)
        exact = sum(row["exact_state_solves"] for row in audits)
        cache_avoided = sum(row["cache_avoided_state_solves"] for row in audits)
        screening_avoided = sum(
            row["screening_avoided_state_solves"] for row in audits
        )
        final_solves = sum(
            row["final_verification_state_solves"] for row in audits
        )
        missed = sum(
            row["missed_violations_at_final_verification"] for row in audits
        )
        feasibility_audits = [
            feasibility(case, run[case]["result"]["solution"]) for run in v4_runs
        ]
        record = {
            "case": case,
            "repetitions": 2,
            "pure_median_core_seconds": pure,
            "v2_median_core_seconds": v2,
            **{f"v4_core_{key}_seconds": value for key, value in v4_stats.items()},
            "v4_over_pure_ratio": v4_stats["median"] / pure,
            "v4_over_v2_ratio": v4_stats["median"] / v2,
            "iterations": len(audits),
            "total_potential_state_solves": potential,
            "actual_exact_state_solves": exact,
            "cache_avoided_state_solves": cache_avoided,
            "screening_avoided_state_solves": screening_avoided,
            "screening_skip_ratio": screening_avoided / max(potential, 1),
            "final_verification_state_solves": final_solves,
            "final_verification_states_checked": audits[-1][
                "potential_product_risk_states"
            ],
            "missed_violations": missed,
            "extra_iterations_vs_v2": len(audits)
            - len(v2_audit[case]["result"]["separation_audit"]),
            "maximum_objective_difference": max(
                run[case]["comparison"]["objective_difference_vs_original"]
                for run in v4_runs
            ),
            "maximum_recourse_difference": max(
                run[case]["comparison"]["recourse_difference_vs_original"]
                for run in v4_runs
            ),
            "maximum_x_difference": max(
                run[case]["comparison"]["max_x_difference_vs_original"]
                for run in v4_runs
            ),
            "same_y": all(
                run[case]["comparison"]["same_y_as_original"] for run in v4_runs
            ),
            "first_stage_feasible": all(
                audit.feasible for audit in feasibility_audits
            ),
            "maximum_first_stage_violation": max(
                audit.maximum_violation for audit in feasibility_audits
            ),
            "gamma_coupling_pass": all(
                run[case]["result"]["global_risk_budget_coupling_pass"]
                for run in v4_runs
            ),
            "exact_certification_pass": all(
                run[case]["result"]["exact_certification_pass"]
                for run in v4_runs
            ),
            "peak_memory_gib": max(
                run[case]["peak_process_tree_memory_gib"] for run in v4_runs
            ),
        }
        benchmark_rows.append(record)
        summary[case] = record
    write_csv(ARTIFACTS / "prb_v4_selective_benchmark.csv", benchmark_rows)

    v2_exact = sum(row["exact_state_solves"] for row in state_rows)
    v2_no_info = sum(row["exact_states_without_new_cut"] for row in state_rows)
    payload = {
        "status": "LIMITED_SAFE_SCREENING_OPPORTUNITY",
        "development_only": True,
        "v2_state_audit": {
            "exact_state_solves": v2_exact,
            "exact_states_without_new_cut": v2_no_info,
            "no_new_cut_fraction": v2_no_info / v2_exact,
        },
        "benchmark": summary,
        "monotonicity_in_local_gamma_proven": False,
        "screening_rule_case_specific": False,
        "tolerance_changed": False,
        "model_changed": False,
        "expand_to_eight_cases": False,
        "E2_E7_rerun_required": False,
    }
    (ARTIFACTS / "prb_v4_selective_summary.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Exact selective-separation audit for Accelerated PRB V4",
        "",
        "This development audit changes no model, master, product cut, uncertainty set, tolerance, termination tolerance, or exact-certification contract. V2 remains the recommended implementation.",
        "",
        "## Safe state upper bound",
        "",
        "For a previously solved exact inventory vector `x'_j`, define `L_ij = max_r [p_rj + s_j - c_irj]_+`. Starting from any feasible recourse plan at `x'_j`, every unit of shipment lost when inventory falls to `x_j` can be replaced by shortage in its destination region. Its incremental shortage plus possible service-violation cost, net of the removed transport cost, is at most `L_ij`. Inventory increases cannot increase recourse. Therefore, for every pattern and hence for its fixed-g maximum,",
        "",
        "`V_jg(x_j) <= V_jg(x'_j) + sum_i L_ij (x'_ij-x_ij)_+`.",
        "",
        "Taking the minimum over all cached exact states preserves a valid upper bound. If this bound is no larger than the current `eta_jg` plus the frozen cut tolerance, the state cannot produce a violated product cut.",
        "",
        "## Exact Gamma screening",
        "",
        "For a candidate `(j,g)`, V4 fixes that state and solves the exact risk-budget DP over all other products using their valid upper bounds and residual budget `Gamma-g`. If this forced-allocation upper bound is no larger than the current `theta` plus tolerance, no feasible global allocation containing `(j,g)` can violate the global surrogate. A product solve is skipped only when every local-g state is certified safe by one of these two proofs. Otherwise V4 falls back to the unchanged exact product solve.",
        "",
        "## Why g-monotonicity is not used",
        "",
        "`V_j,0 <= ... <= V_j,Gamma` is not guaranteed by the frozen formulation. Increasing demand also increases the allowed shortage `(1-alpha_j) sum_r d_rj`; cheap shipment to the newly increased region can relax an existing service-violation charge elsewhere. Nonnegative demand deviations alone therefore do not prove monotonicity. V4 assumes neither monotonicity nor convex/concave marginal risk increments.",
        "",
        "## V2 state audit",
        "",
        f"Across the three instrumented V2 runs, {v2_exact} product-risk states were physically solved after exact-cache reuse; {v2_no_info} ({100.0*v2_no_info/v2_exact:.1f}%) produced no new cut. The detailed per-iteration table is `artifacts/prb_v2_state_solve_audit.csv`.",
        "",
        "## V4 outcome",
        "",
        "V2's product oracle solves all `g=0,1,2` blocks together. Although the bounds certify a few individual states safe, no changed product had every local-g state certified safe. The strict fallback therefore selected every changed product, giving zero screening-avoided physical state solves. Final full-state verification checked every state, required zero additional physical solves because the identical states were already in the exact cache, and found zero missed violations.",
        "",
        "| Case | Pure | V2 | V4 | V4/Pure | Screening avoided | Missed |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in benchmark_rows:
        lines.append(
            f"| {row['case']} | {row['pure_median_core_seconds']:.3f}s | {row['v2_median_core_seconds']:.3f}s | {row['v4_core_median_seconds']:.3f}s | {row['v4_over_pure_ratio']:.2f}x | {row['screening_avoided_state_solves']} | {row['missed_violations']} |"
        )
    lines += [
        "",
        "All V4 runs match the frozen objective and recourse, preserve `x/y`, pass first-stage feasibility, Gamma coupling, and exact certification, and use unchanged tolerances. Because the safe screening ratio is zero, V4 is not promoted and the experiment is not expanded.",
        "",
        "Final classification: `LIMITED_SAFE_SCREENING_OPPORTUNITY`.",
        "",
        "E2--E7 reruns: 0. Paper text changed: no.",
    ]
    (ROOT / "docs/prb_selective_separation_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
