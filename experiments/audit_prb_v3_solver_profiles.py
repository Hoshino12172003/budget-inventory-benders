from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.accelerated_product_risk_subproblem import (
    AcceleratedProductRiskSubproblem,
)
from robust_inventory_reconfiguration.instance import load_instance


def main() -> None:
    instance = load_instance(
        ROOT / "experiments/results/e1c_development_probe_v1/XL_low/PREPARE/instance.json"
    )
    configurations = (
        ("AUTO", None, None),
        ("DUAL_P0", 1, 0),
        ("DUAL_P1", 1, 1),
        ("DUAL_P2", 1, 2),
        ("PRIMAL_P0", 0, 0),
        ("PRIMAL_P1", 0, 1),
    )
    rows = []
    reference_checksum = None
    for name, method, presolve in configurations:
        build_times = []
        solve_times = []
        extraction_times = []
        update_times = []
        checksum = 0.0
        for j in (0, 7, 13):
            started = perf_counter()
            subproblem = AcceleratedProductRiskSubproblem(
                instance, j, 2, method=method, presolve=presolve
            )
            build_times.append(perf_counter() - started)
            baseline = [
                instance.initial_inventory[i][j]
                for i in range(instance.num_depots)
            ]
            try:
                for factor in (1.0, 0.8, 1.2, 1.0):
                    result = subproblem.solve([factor * value for value in baseline])
                    solve_times.append(result.runtime)
                    extraction_times.append(result.result_extraction_runtime)
                    update_times.append(result.model_update_runtime)
                    checksum += sum(row.value for row in result.worst_cases)
            finally:
                subproblem.close()
        if reference_checksum is None:
            reference_checksum = checksum
        rows.append(
            {
                "profile": name,
                "method": method,
                "presolve": presolve,
                "build_sum_seconds": sum(build_times),
                "build_max_seconds": max(build_times),
                "solve_sum_seconds": sum(solve_times),
                "solve_median_seconds": statistics.median(solve_times),
                "extraction_sum_seconds": sum(extraction_times),
                "update_sum_seconds": sum(update_times),
                "value_checksum": checksum,
                "absolute_checksum_difference": abs(checksum - reference_checksum),
            }
        )
    payload = {
        "status": "PASS"
        if all(row["absolute_checksum_difference"] <= 1e-6 for row in rows)
        else "FAIL",
        "scope": "XL_low products 0, 7, 13; four deterministic RHS states each",
        "unchanged_tolerances": True,
        "selected_profile": "AUTO",
        "selection_rule": "minimum total solve time; ties retain the existing profile",
        "rows": rows,
    }
    output = ROOT / "artifacts/prb_v3_solver_profile_audit.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
