from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean, median

from .service_calibration import enumerate_conditions


RESULT_FIELDS = (
    "experiment_id", "case_id", "condition_id", "run_type", "config_hash",
    "instance_hash", "data_hash", "canonical_instance_identity", "code_commit",
    "code_identity_hash", "Gamma", "beta", "lambda_R", "SL", "phi_multiplier",
    "phi_vector_hash", "phi_min", "phi_max", "phi_mean", "solver_status",
    "optimality_certification", "objective", "lower_bound", "upper_bound",
    "optimality_gap", "benders_iterations", "number_of_cuts", "core_solve_time",
    "master_time", "oracle_subproblem_time", "certification_time", "RI", "RS",
    "material_reconfiguration", "total_upward_adjustment", "total_downward_adjustment",
    "budget", "reconfiguration_spending", "budget_utilization", "budget_binding",
    "total_shortage", "shortage_cost", "service_violation_amount",
    "service_violation_metric_status", "service_penalty_cost", "aggregate_fill_rate",
    "minimum_fill_rate", "worst_region", "worst_product", "active_depot_count",
    "active_depot_set", "activated_depots_vs_baseline", "deactivated_depots_vs_baseline",
    "reused", "reuse_source_run",
)


def validate_result_schema(result: dict) -> None:
    missing = [field for field in RESULT_FIELDS if field not in result]
    if missing:
        raise ValueError(f"service calibration result missing fields: {','.join(missing)}")


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str] | tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _summary_rows(case_rows: list[dict], run_type: str, parameter: str) -> list[dict]:
    output = []
    levels = sorted({float(row[parameter]) for row in case_rows if row["run_type"] == run_type})
    for level in levels:
        rows = [row for row in case_rows if row["run_type"] == run_type and float(row[parameter]) == level]
        output.append({
            parameter: level,
            "case_count": len(rows),
            "mean_objective": mean(float(row["objective"]) for row in rows),
            "median_objective": median(float(row["objective"]) for row in rows),
            "mean_normalized_objective": mean(float(row["normalized_objective_relative_to_baseline"]) for row in rows),
            "median_normalized_objective": median(float(row["normalized_objective_relative_to_baseline"]) for row in rows),
            "mean_RI": mean(float(row["RI"]) for row in rows),
            "median_RI": median(float(row["RI"]) for row in rows),
            "material_cases": sum(bool(row["material_reconfiguration"]) for row in rows),
            "mean_RS": mean(float(row["RS"]) for row in rows),
            "mean_shortage": mean(float(row["total_shortage"]) for row in rows),
            "mean_fill_rate": mean(float(row["aggregate_fill_rate"]) for row in rows),
            "mean_service_penalty": mean(float(row["service_penalty_cost"]) for row in rows),
            "mean_budget_utilization": mean(float(row["budget_utilization"]) for row in rows),
            "cases_with_active_depot_changes": sum(bool(row["activated_depots_vs_baseline"] or row["deactivated_depots_vs_baseline"]) for row in rows),
        })
    return output


def build_case_rows(physical_results: list[dict]) -> list[dict]:
    by_id = {row["condition_id"]: row for row in physical_results}
    if len(by_id) != len(physical_results):
        raise ValueError("duplicate physical result condition_id")
    rows = []
    conditions = enumerate_conditions()
    for condition in conditions:
        source = by_id.get(condition.physical_result_id)
        if source is None:
            raise ValueError(f"missing physical result {condition.physical_result_id}")
        baseline = by_id[f"SC-{condition.case_id}-BASELINE"]
        row = dict(source)
        row.update({
            "condition_id": condition.condition_id,
            "physical_result_id": condition.physical_result_id,
            "run_type": condition.run_type,
            "SL": condition.service_level,
            "phi_multiplier": condition.phi_multiplier,
            "normalized_objective_relative_to_baseline": float(source["objective"]) / float(baseline["objective"]),
        })
        base_depots = set(json.loads(baseline["active_depot_set"]))
        current_depots = set(json.loads(source["active_depot_set"]))
        row["activated_depots_vs_baseline"] = json.dumps(sorted(current_depots - base_depots))
        row["deactivated_depots_vs_baseline"] = json.dumps(sorted(base_depots - current_depots))
        rows.append(row)
    return rows


def write_reports(physical_results: list[dict], baseline_audit: list[dict], output_dir: Path) -> None:
    for result in physical_results:
        validate_result_schema(result)
    if len(physical_results) != 40 or len({row["condition_id"] for row in physical_results}) != 40:
        raise ValueError("reporting requires exactly 40 unique physical results")
    output_dir.mkdir(parents=True, exist_ok=True)
    case_rows = build_case_rows(physical_results)
    if len(case_rows) != 48:
        raise ValueError("reporting requires exactly 48 OFAT analysis rows")
    all_fields = list(RESULT_FIELDS)
    case_fields = list(dict.fromkeys([*RESULT_FIELDS, "physical_result_id", "normalized_objective_relative_to_baseline"]))
    _write_csv(output_dir / "service_calibration_all_results.csv", physical_results, all_fields)
    _write_csv(output_dir / "service_calibration_case_level.csv", case_rows, case_fields)
    sl_rows = _summary_rows(case_rows, "sl_sensitivity", "SL")
    phi_rows = _summary_rows(case_rows, "phi_sensitivity", "phi_multiplier")
    _write_csv(output_dir / "service_calibration_sl_summary.csv", sl_rows, list(sl_rows[0]))
    _write_csv(output_dir / "service_calibration_phi_summary.csv", phi_rows, list(phi_rows[0]))
    _write_csv(output_dir / "service_calibration_baseline_reuse_audit.csv", baseline_audit, list(baseline_audit[0]))
    lines = [
        "# Service calibration robustness summary", "",
        "- Design: OFAT; full SL x phi interaction was not run.",
        "- Physical results: 40 (8 reused baselines and 32 new solves).",
        "- Analysis rows: 48 (24 SL and 24 phi conditions).", "",
        "## SL sensitivity", "",
    ]
    lines.extend(f"- SL={row['SL']:.2f}: mean normalized objective={row['mean_normalized_objective']:.6f}, material cases={row['material_cases']}/8" for row in sl_rows)
    lines.extend(["", "## Phi sensitivity", ""])
    lines.extend(f"- phi_multiplier={row['phi_multiplier']:.2f}: mean normalized objective={row['mean_normalized_objective']:.6f}, material cases={row['material_cases']}/8" for row in phi_rows)
    (output_dir / "service_calibration_robustness_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
