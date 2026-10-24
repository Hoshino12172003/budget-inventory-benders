from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.accelerated_product_risk_subproblem import (
    AcceleratedProductRiskSubproblem,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.structured_product_risk_subproblem import (
    StructuredProductRiskSubproblem,
)


CASES = ("210202", "L", "XL_low")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_case(case: str):
    if case == "210202":
        return load_instance(ROOT / "data/formal_instances_v2/210202.json")
    return load_instance(
        ROOT / f"experiments/results/e1c_development_probe_v1/{case}/PREPARE/instance.json"
    )


def state_vectors(instance, product: int, rng: random.Random):
    baseline = [instance.initial_inventory[i][product] for i in range(instance.num_depots)]
    upper = [instance.inventory_upper_bound[i][product] for i in range(instance.num_depots)]
    return (
        baseline,
        [0.75 * value for value in baseline],
        [min(limit, 1.10 * value) for value, limit in zip(baseline, upper)],
        [rng.random() * limit for limit in upper],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/prb_v3_product_state_audit.json",
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    rng = random.Random(20260921)
    rows = []
    for case in CASES:
        instance = load_case(case)
        for j in range(instance.num_products):
            build_started = perf_counter()
            v2 = AcceleratedProductRiskSubproblem(instance, j, 2)
            v2_build = perf_counter() - build_started
            build_started = perf_counter()
            v3 = StructuredProductRiskSubproblem(instance, j, 2)
            v3_build = perf_counter() - build_started
            try:
                for state_index, vector in enumerate(state_vectors(instance, j, rng)):
                    expected = v2.solve(vector)
                    actual = v3.solve(vector)
                    for left, right in zip(expected.worst_cases, actual.worst_cases):
                        rows.append(
                            {
                                "case": case,
                                "product": instance.product_ids[j],
                                "state_index": state_index,
                                "local_gamma": right.local_gamma,
                                "v2_value": left.value,
                                "v3_value": right.value,
                                "absolute_value_difference": abs(left.value - right.value),
                                "v2_pattern": list(left.pattern),
                                "v3_pattern": list(right.pattern),
                                "same_pattern": left.pattern == right.pattern,
                                "maximum_demand_dual_difference": max(
                                    abs(a - b)
                                    for a, b in zip(
                                        left.demand_dual, right.demand_dual
                                    )
                                ),
                                "maximum_supply_dual_difference": max(
                                    abs(a - b)
                                    for a, b in zip(
                                        left.supply_dual, right.supply_dual
                                    )
                                ),
                                "service_dual_difference": abs(
                                    left.service_dual - right.service_dual
                                ),
                                "cut_alpha_difference": abs(
                                    left.cut.alpha - right.cut.alpha
                                ),
                                "maximum_cut_beta_difference": max(
                                    abs(a - b)
                                    for a, b in zip(left.cut.beta, right.cut.beta)
                                ),
                                "v3_dual_feasible": right.cut.dual_feasible,
                                "v3_cut_tightness_error": abs(
                                    right.cut.value_at(vector) - right.value
                                ),
                                "v3_strong_duality_error": right.cut.strong_duality_error,
                                "v2_solve_seconds": expected.runtime,
                                "v3_solve_seconds": actual.runtime,
                                "v2_build_seconds": v2_build,
                                "v3_build_seconds": v3_build,
                            }
                        )
            finally:
                v2.close()
                v3.close()
    summary = {
        "status": "PASS"
        if max(row["absolute_value_difference"] for row in rows) <= 1e-6
        and all(row["v3_dual_feasible"] for row in rows)
        and max(row["v3_cut_tightness_error"] for row in rows) <= 1e-6
        else "FAIL",
        "seed": 20260921,
        "product_inventory_vectors": len(rows) // 3,
        "product_risk_states": len(rows),
        "maximum_value_difference": max(
            row["absolute_value_difference"] for row in rows
        ),
        "maximum_cut_tightness_error": max(
            row["v3_cut_tightness_error"] for row in rows
        ),
        "maximum_strong_duality_error": max(
            row["v3_strong_duality_error"] for row in rows
        ),
        "maximum_demand_dual_difference": max(
            row["maximum_demand_dual_difference"] for row in rows
        ),
        "maximum_supply_dual_difference": max(
            row["maximum_supply_dual_difference"] for row in rows
        ),
        "maximum_service_dual_difference": max(
            row["service_dual_difference"] for row in rows
        ),
        "maximum_cut_alpha_difference": max(
            row["cut_alpha_difference"] for row in rows
        ),
        "maximum_cut_beta_difference": max(
            row["maximum_cut_beta_difference"] for row in rows
        ),
        "all_duals_feasible": all(row["v3_dual_feasible"] for row in rows),
        "same_worst_pattern_count": sum(row["same_pattern"] for row in rows),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    csv_output = output.with_suffix(".csv")
    with csv_output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary))
    if summary["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
