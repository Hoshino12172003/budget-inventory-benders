from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from experiments.run_e3_budget_local import BETA_GRID, expected_run_ids, make_run_id


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "experiments/results/e3_budget_sensitivity_v1"
DEFAULT_OUTPUT = ROOT / "artifacts/e3_budget_sensitivity_summary.csv"
DEFAULT_PAPER_OUTPUT_DIR = ROOT / "artifacts"
REPORTING_TOLERANCE = 1e-6
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
                "B": result["B"], "B_ref": result["B_ref"],
                "first_stage_economic_cost": result["budget_used"],
                "fixed_cost": result["fixed_cost"], "inventory_cost": result["inventory_cost"],
                "reconfiguration_cost": result["reconfiguration_cost"],
                "budget_used": result["budget_used"], "budget_slack": result["budget_slack"],
                "total_a_plus": result["total_a_plus"], "total_a_minus": result["total_a_minus"],
                "changed_pair_count": result["changed_pair_count"],
                "opened_depots": "|".join(result["opened_depots"]),
                "closed_depots": "|".join(result["closed_depots"]),
                "transport_cost": result["robust_recourse_cost"]
                - result["worst_recourse_shortage_cost"]
                - result["worst_recourse_service_penalty_cost"],
                "worst_region": result.get("worst_region", ""),
                "runtime_seconds": result["runtime_seconds"], "iterations": result["iterations"],
                "master_solves": result["master_solves"],
                "product_subproblem_evaluations": result["product_subproblem_evaluations"],
                "cuts_added": result["cuts_added"],
                "certification_status": result["certification_status"], "status": result["status"],
                "objective_delta_pct_vs_B100": percent_delta(result["objective"], baseline["objective"]),
                "objective_absolute_change_from_previous_beta": "",
                "objective_change_vs_B100": result["objective"] - baseline["objective"],
                "recourse_delta_pct_vs_B100": percent_delta(result["robust_recourse_cost"], baseline["robust_recourse_cost"]),
                "recourse_change_vs_B100": result["robust_recourse_cost"] - baseline["robust_recourse_cost"],
                "RI_delta_vs_B100": result["RI"] - baseline["RI"],
                "RS_delta_vs_B100": result["RS"] - baseline["RS"],
                "budget_utilization_delta_vs_B100": result["budget_utilization"] - baseline["budget_utilization"],
                "total_adjustment_delta_vs_B100": result["total_adjustment"] - baseline["total_adjustment"],
                "shortage_cost_delta_vs_B100": result["worst_recourse_shortage_cost"] - baseline["worst_recourse_shortage_cost"],
                "service_penalty_delta_vs_B100": result["worst_recourse_service_penalty_cost"] - baseline["worst_recourse_service_penalty_cost"],
                "average_fill_rate_delta_vs_B100": result["average_fill_rate"] - baseline["average_fill_rate"],
                "normalized_objective": result["objective"] / baseline["objective"],
                "normalized_robust_recourse": result["robust_recourse_cost"] / baseline["robust_recourse_cost"],
                "budget_feasibility_pass": result["budget_feasibility_pass"],
                "reused_from_E1_or_E2": result["reused_from_E1_or_E2"],
            }
            rows.append(row)
    previous = {}
    for row in rows:
        if row["case"] in previous:
            row["objective_absolute_change_from_previous_beta"] = row["objective"] - previous[row["case"]]
        previous[row["case"]] = row["objective"]
    return rows


def aggregate_rows(rows: list[dict]) -> list[dict]:
    output = []
    metrics = (
        "objective", "normalized_objective", "robust_recourse_cost", "normalized_robust_recourse",
        "RI", "RS", "budget_utilization", "total_adjustment",
        "worst_recourse_shortage_cost", "worst_recourse_service_penalty_cost", "average_fill_rate",
    )
    for beta in BETA_GRID:
        selected = [row for row in rows if row["beta"] == float(beta)]
        aggregate = {"beta": float(beta)}
        for metric in metrics:
            values = [float(row[metric]) for row in selected]
            aggregate.update({
                f"mean_{metric}": statistics.mean(values),
                f"median_{metric}": statistics.median(values),
                f"min_{metric}": min(values),
                f"max_{metric}": max(values),
            })
        aggregate["mean_objective_improvement_vs_B100_pct"] = statistics.mean(
            -float(row["objective_delta_pct_vs_B100"]) for row in selected
        )
        aggregate["material_reconfiguration_case_count"] = sum(float(row["RI"]) > REPORTING_TOLERANCE for row in selected)
        output.append(aggregate)
    return output


def threshold_rows(rows: list[dict], cases: list[str]) -> list[dict]:
    output = []
    for case in cases:
        selected = sorted((row for row in rows if row["case"] == case), key=lambda row: row["beta"])
        by_beta = {row["beta"]: row for row in selected}
        plateau = ""
        for current, following in zip(selected, selected[1:]):
            improvement = current["objective"] - following["objective"]
            if improvement <= REPORTING_TOLERANCE:
                plateau = current["beta"]
                break
        output.append({
            "case": case, "B_ref": selected[0]["B_ref"],
            **{f"objective_B{int(beta * 100):03d}": by_beta[float(beta)]["objective"] for beta in BETA_GRID},
            **{f"normalized_objective_B{int(beta * 100):03d}": by_beta[float(beta)]["normalized_objective"] for beta in BETA_GRID},
            "first_empirical_plateau_beta": plateau,
            "B110_vs_B120_objective_change": by_beta[1.2]["objective"] - by_beta[1.1]["objective"],
            "B110_budget_utilization": by_beta[1.1]["budget_utilization"],
            "B120_budget_utilization": by_beta[1.2]["budget_utilization"],
            "B110_budget_slack": by_beta[1.1]["budget_slack"],
            "B120_budget_slack": by_beta[1.2]["budget_slack"],
            "B100_RI": by_beta[1.0]["RI"], "B080_RI": by_beta[0.8]["RI"], "B090_RI": by_beta[0.9]["RI"],
        })
    return output


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-root", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--paper-output-dir", type=Path, default=DEFAULT_PAPER_OUTPUT_DIR)
    args = parser.parse_args()
    cases = json.loads((ROOT / "experiments/configs/formal/e3_budget_sensitivity_authorization.json").read_text(encoding="utf-8"))["cases"]
    rows = summary_rows(load_complete_results(args.result_root, cases), cases)
    write_csv(args.output, rows)
    write_csv(args.paper_output_dir / "e3_table_budget_sensitivity_case_level.csv", rows)
    write_csv(args.paper_output_dir / "e3_table_budget_sensitivity_aggregate.csv", aggregate_rows(rows))
    write_csv(args.paper_output_dir / "e3_table_budget_thresholds.csv", threshold_rows(rows, cases))
    print(f"wrote {len(rows)} E3 rows")


if __name__ == "__main__":
    main()
