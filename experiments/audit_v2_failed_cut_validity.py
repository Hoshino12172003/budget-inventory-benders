"""Read-only V2 Benders cut audit for L10/20260925.

Place alongside run_accelerated_prb_v2_scaling30.py in experiments/.
Re-solves ONLY the failed V2 condition with its original parameters, then
independently checks every returned cut at the final V2 inventory using the
original product risk subproblem solver. Does not edit production source,
results, or thresholds. A passing check is NOT a formal proof of every cut
at every feasible first-stage point.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import gurobipy as gp
import run_accelerated_prb_v2_scaling30 as frozen
from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import (
    solve_accelerated_prb_benders,
)
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem

SIZE, SEED, WORKERS = "L10", 20260925, 2


def main() -> None:
    instance, prep, baseline, _ = frozen.fetch_inputs(SIZE, SEED)
    gp.setParam("Threads", 1)
    solved = solve_accelerated_prb_benders(
        instance, instance.initial_inventory, float(prep["budget"]), 2, 0.05,
        relative_gap_tolerance=1e-6,
        cut_tolerance=1e-7,
        max_iterations=500,
        parallel_workers=WORKERS,
        _oracle_backend="process",
    )

    x = solved.solution.x
    exact_costs = []
    for j in range(instance.num_products):
        model = ProductRiskSubproblem(instance, j, 2)
        try:
            recourse = model.solve([x[i][j] for i in range(instance.num_depots)])
            exact_costs.append([float(s.value) for s in recourse.worst_cases])
        finally:
            model.model.dispose()

    cut_dual_failures = []
    cut_at_final_x_violations = []
    max_strong_duality_error = 0.0
    max_cut_over_recourse = float("-inf")
    max_cut_generation_mismatch = 0.0
    for idx, cut in enumerate(solved.cuts):
        if not cut.dual_feasible:
            cut_dual_failures.append(idx)
        max_strong_duality_error = max(max_strong_duality_error, float(cut.strong_duality_error))
        at_generation = cut.value_at(cut.generation_x)
        max_cut_generation_mismatch = max(
            max_cut_generation_mismatch,
            abs(float(at_generation) - float(cut.generation_value)),
        )
        j, g = cut.product_index, cut.local_gamma
        at_final = cut.value_at([x[i][j] for i in range(instance.num_depots)])
        over = float(at_final) - exact_costs[j][g]
        max_cut_over_recourse = max(max_cut_over_recourse, over)
        if over > 1e-6:
            cut_at_final_x_violations.append({
                "cut_index": idx, "product": j, "gamma": g,
                "cut_value_at_final_x": float(at_final),
                "independent_exact_product_risk": exact_costs[j][g],
                "cut_over_exact": float(over),
            })

    lower = float(solved.final_lower_bound)
    upper = float(solved.final_upper_bound)
    obj = float(solved.solution.objective)
    scale = max(1., abs(lower), abs(upper))
    report = {
        "size": SIZE, "seed": SEED, "workers": WORKERS,
        "status": solved.status,
        "exact_certification_pass": bool(solved.exact_certification_pass),
        "global_risk_budget_coupling_pass": bool(solved.global_risk_budget_coupling_pass),
        "global_risk_budget_coupling_error": float(solved.global_risk_budget_coupling_error),
        "reported_final_relative_gap": float(solved.final_relative_gap),
        "signed_lower_minus_upper": lower-upper,
        "signed_lower_minus_upper_div_scale": (lower-upper)/scale,
        "last_iteration_new_cuts": int(solved.iterations[-1].cuts_added) if hasattr(solved.iterations[-1], 'cuts_added') else None,
        "final_objective": obj,
        "reference_basic_objective_difference": obj - float(baseline["final_objective"]),
        "cut_count": len(solved.cuts),
        "dual_infeasible_cut_indices": cut_dual_failures,
        "max_cut_strong_duality_error": max_strong_duality_error,
        "max_cut_generation_value_mismatch": max_cut_generation_mismatch,
        "max_cut_over_independent_recourse_at_final_x": max_cut_over_recourse,
        "cut_violations_at_final_x_over_1e_6": cut_at_final_x_violations,
        "scope_note": (
            "Checks all returned V2 cuts for reported dual feasibility and strong duality, "
            "and independently checks them at final inventory. Does not establish "
            "whole-domain cut validity or certify final master bound."
        ),
    }
    path = ROOT / (
        "experiments/results/prb_basic_v2_fair_scaling30_W2/failed_diagnostics/"
        "audit_L10_20260925_v2_cuts.json"
    )
    frozen.write_json(path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"[AUDIT WRITTEN] {path}")

if __name__ == "__main__":
    main()
