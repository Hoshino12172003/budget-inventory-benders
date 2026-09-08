from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from experiments.run_e3_budget_local import BETA_GRID, expected_run_ids, make_run_id


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "experiments/results/e3_budget_sensitivity_v1"
DEFAULT_OUTPUT = ROOT / "artifacts/e3_budget_sensitivity_summary.csv"
METRICS = (
    "objective", "robust_recourse_cost", "RI", "RS", "total_adjustment",
    "budget_utilization", "worst_recourse_shortage_cost",
    "worst_recourse_service_penalty_cost", "worst_recourse_total_shortage",
    "minimum_fill_rate", "average_fill_rate", "active_depots",
)


def load_complete_results(result_root: Path, cases: list[str]) -> dict[str, dict[str, dict]]:
    results = {}
    seen = set()
    for path in sorted(result_root.glob("*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["run_id"] in seen:
            raise ValueError(f"duplicate E3 run: {result['run_id']}")
        seen.add(result["run_id"])
        results.setdefault(result["case"], {})[f"{result['beta']:.2f}"] = result
    expected = set(expected_run_ids(cases))
    if seen != expected:
        raise ValueError(f"incomplete E3 results: missing={sorted(expected - seen)}, extra={sorted(seen - expected)}")
    return results


def percent_delta(value: float, baseline: float) -> float:
    return 100.0 * (value - baseline) / baseline


def summary_rows(results: dict[str, dict[str, dict]], cases: list[str]) -> list[dict]:
    rows = []
    for case in cases:
        baseline = results[case]["1.00"]
        for beta in BETA_GRID:
            result = results[case][f"{float(beta):.2f}"]
            row = {
                "run_id": make_run_id(case, beta), "case": case, "beta": float(beta),
                **{metric: result[metric] for metric in METRICS},
                "objective_delta_pct_vs_B100": percent_delta(result["objective"], baseline["objective"]),
                "recourse_delta_pct_vs_B100": percent_delta(result["robust_recourse_cost"], baseline["robust_recourse_cost"]),
                "RI_delta_vs_B100": result["RI"] - baseline["RI"],
                "RS_delta_vs_B100": result["RS"] - baseline["RS"],
                "fixed_cost": result["fixed_cost"], "inventory_cost": result["inventory_cost"],
                "reconfiguration_cost": result["reconfiguration_cost"],
                "budget_used": result["budget_used"], "budget_slack": result["budget_slack"],
                "budget_feasibility_pass": result["budget_feasibility_pass"],
                "reused_from_E1_or_E2": result["reused_from_E1_or_E2"],
            }
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-root", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    cases = json.loads((ROOT / "experiments/configs/formal/e3_budget_sensitivity_authorization.json").read_text(encoding="utf-8"))["cases"]
    rows = summary_rows(load_complete_results(args.result_root, cases), cases)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} E3 rows")


if __name__ == "__main__":
    main()
