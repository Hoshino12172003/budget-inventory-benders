from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import gurobipy as gp
import run_accelerated_prb_v2_scaling30 as frozen
from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import (
    solve_accelerated_prb_benders,
)

def main():
    instance, prep, baseline, hashes = frozen.fetch_inputs("L10", 20260925)

    gp.setParam("Threads", 1)

    result = solve_accelerated_prb_benders(
        instance,
        instance.initial_inventory,
        float(prep["budget"]),
        2,
        0.05,
        relative_gap_tolerance=1e-6,
        cut_tolerance=1e-7,
        max_iterations=500,
        parallel_workers=2,
        _oracle_backend="process",
    )

    report = {
        "status": result.status,
        "exact_certification_pass": result.exact_certification_pass,
        "global_risk_budget_coupling_pass": result.global_risk_budget_coupling_pass,
        "global_risk_budget_coupling_error": result.global_risk_budget_coupling_error,
        "final_relative_gap": result.final_relative_gap,
        "final_lower_bound": result.final_lower_bound,
        "final_upper_bound": result.final_upper_bound,
        "certified_objective": result.solution.objective,
        "objective_difference_from_frozen": abs(
            result.solution.objective - baseline["final_objective"]
        ),
        "upper_bound_minus_certified_objective": (
            result.final_upper_bound - result.solution.objective
        ),
        "iterations": len(result.iterations),
        "core_seconds": result.total_runtime,
    }

    print(json.dumps(report, indent=2))

    output = ROOT / (
        "experiments/results/prb_basic_v2_fair_scaling30_W2/"
        "failed_diagnostics/v2_20260925_certification_flags.json"
    )
    frozen.write_json(output, report)

if __name__ == "__main__":
    main()
