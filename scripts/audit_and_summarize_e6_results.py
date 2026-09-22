from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import experiments.run_e6_budget_risk_local as runner
from robust_inventory_reconfiguration.first_stage_solution import (
    matrix_from_artifact,
    validate_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.scenarios import scenario_count


ARTIFACTS = ROOT / "artifacts"
CASE_TABLE = ARTIFACTS / "e6_table_budget_risk_interaction_case_level.csv"
AGGREGATE_TABLE = ARTIFACTS / "e6_table_budget_risk_interaction_aggregate.csv"
CONTRAST_TABLE = ARTIFACTS / "e6_table_interaction_contrasts.csv"
DEPOT_TABLE = ARTIFACTS / "e6_table_depot_response.csv"
RUNTIME_TABLE = ARTIFACTS / "e6_runtime_accounting_audit.csv"
FINAL_AUDIT = ARTIFACTS / "e6_final_result_audit.json"
REVIEW_PACKAGE = ROOT / "e6_full_review_package.zip"
TOLERANCE = 1e-4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_identity(root: Path) -> str:
    files = {
        str(path.relative_to(root)).replace("\\", "/"): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    return runner.canonical_hash(files)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _entries(values: list[dict]) -> dict[tuple[str, str], float]:
    return {
        (item["depot_id"], item["product_id"]): float(item["value"])
        for item in values
    }


def _read_results() -> tuple[dict[str, Path], dict[str, dict]]:
    expected = {condition.run_id for condition in runner.enumerate_conditions()}
    directories = {path.name: path for path in runner.RESULT_ROOT.iterdir() if path.is_dir()}
    results: dict[str, dict] = {}
    for run_id, directory in directories.items():
        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        if result["run_id"] in results:
            raise RuntimeError(f"duplicate E6 run ID: {result['run_id']}")
        results[result["run_id"]] = result
    if set(directories) != expected or set(results) != expected:
        raise RuntimeError(
            f"incomplete E6 grid: missing={sorted(expected - set(results))}, "
            f"extra={sorted(set(results) - expected)}"
        )
    return directories, results


def _package_comparison(directories: dict[str, Path]) -> dict:
    if not REVIEW_PACKAGE.is_file():
        return {"available": False, "classification": "UNAVAILABLE"}
    compared = 0
    mismatches = []
    with zipfile.ZipFile(REVIEW_PACKAGE) as archive:
        names = set(archive.namelist())
        for run_id, directory in directories.items():
            for filename in ("result.json", "first_stage_solution.json", "provenance.json"):
                name = f"e6_budget_risk_interaction_v1/{run_id}/{filename}"
                if name not in names:
                    mismatches.append(f"missing:{name}")
                    continue
                compared += 1
                if hashlib.sha256(archive.read(name)).hexdigest() != sha256(directory / filename):
                    mismatches.append(f"hash:{name}")
    return {
        "available": True,
        "artifact_files_compared": compared,
        "mismatches": mismatches,
        "classification": "216_OF_216_BYTE_IDENTICAL" if compared == 216 and not mismatches else "MISMATCH",
    }


def _completion_times(directories: dict[str, Path]) -> dict[str, dict]:
    ordered = []
    for run_id, directory in directories.items():
        provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
        ordered.append((datetime.fromisoformat(provenance["created_at_utc"]), run_id))
    ordered.sort()
    output = {}
    previous = None
    for completed, run_id in ordered:
        output[run_id] = {
            "completion_utc": completed.isoformat(),
            "previous_completion_utc": previous.isoformat() if previous else None,
            "inter_completion_gap_seconds": (completed - previous).total_seconds() if previous else None,
        }
        previous = completed
    return output


def _runtime_row(result: dict, directory: Path, completion: dict) -> dict:
    gamma = int(result["Gamma"])
    reported = float(result["runtime_seconds"])
    gap = completion["inter_completion_gap_seconds"]
    anomaly = bool(not result["reused"] and gap is not None and gap > max(60.0, 10.0 * reported))
    return {
        "run_id": result["run_id"],
        "case": result["case"],
        "beta_token": result["beta_token"],
        "beta": result["beta"],
        "Gamma_token": result["Gamma_token"],
        "Gamma": gamma,
        "reuse_or_new": "REUSE" if result["reused"] else "NEW_SOLVE",
        "reuse_source_run": result["reuse_source_run"],
        "reported_runtime_seconds": reported,
        "reported_runtime_exact_scope": (
            "SOURCE_REPORTED_PRB_RUNTIME_COPIED" if result["reused"]
            else "PRB_BUILD_MASTER_THROUGH_EXACT_PRODUCT_RECERTIFICATION"
        ),
        "certification_in_reported_timer": True,
        "service_post_evaluation_in_reported_timer": False,
        "artifact_writing_in_reported_timer": False,
        "completion_utc": completion["completion_utc"],
        "result_mtime_utc": datetime.fromtimestamp(
            (directory / "result.json").stat().st_mtime
        ).astimezone().isoformat(),
        "previous_completion_utc": completion["previous_completion_utc"],
        "inter_completion_gap_seconds": gap,
        "reconstructed_wallclock_seconds": None,
        "wallclock_reconstruction_status": "UNAVAILABLE_NO_RUNNER_START_TIMESTAMP",
        "global_scenarios_in_post_evaluation": scenario_count(
            load_instance(ROOT / f"data/formal_instances_v2/{result['case']}.json"), gamma
        ),
        "product_risk_blocks_in_post_evaluation": 8 * sum(math.comb(12, k) for k in range(gamma + 1)),
        "runtime_scope_classification": (
            "SOURCE_TIMING_SCOPE_INHERITED" if result["reused"] else
            "CORE_PRB_AND_CERTIFICATION_ONLY|POST_EVALUATION_EXCLUDED_FROM_TIMER|"
            "RUNNER_WALLCLOCK_NOT_CAPTURED|MULTI_STAGE_TIMING_ACCOUNTING_GAP"
        ),
        "timing_anomaly_flag": anomaly,
    }


def _audit_run(
    condition: runner.Condition,
    directory: Path,
    result: dict,
    plan: dict,
    manifest: dict,
) -> tuple[dict, dict, list[str]]:
    errors = []
    result_path = directory / "result.json"
    solution_path = directory / "first_stage_solution.json"
    provenance_path = directory / "provenance.json"
    if not all(path.is_file() for path in (result_path, solution_path, provenance_path)):
        return {}, {}, ["missing_primary_file"]
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    solution = json.loads(solution_path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / manifest["result_schema"]).read_text(encoding="utf-8"))
    instance = load_instance(ROOT / f"data/formal_instances_v2/{condition.case}.json")
    x0_artifact = json.loads(
        (ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case}.json").read_text(
            encoding="utf-8"
        )
    )
    try:
        validate_first_stage_solution_artifact(solution, instance)
    except ValueError as error:
        errors.append(f"solution_artifact:{error}")
    x = matrix_from_artifact(solution, instance, "x")
    a_plus = matrix_from_artifact(solution, instance, "a_plus")
    a_minus = matrix_from_artifact(solution, instance, "a_minus")
    y = [int(item["value"]) for item in solution["y"]]
    x0 = x0_artifact["x0"]
    y0 = [int(value) for value in x0_artifact["y0"]]
    fixed = sum(instance.fixed_depot_cost[i] * y[i] for i in range(instance.num_depots))
    inventory = sum(
        instance.inventory_cost[i][j] * x[i][j]
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    solver_adjustment = sum(
        a_plus[i][j] + a_minus[i][j]
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    reconfiguration = manifest["lambda_R"] * sum(
        instance.inventory_cost[i][j] * (a_plus[i][j] + a_minus[i][j])
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    differences = [
        abs(x[i][j] - x0[i][j])
        for i in range(instance.num_depots) for j in range(instance.num_products)
    ]
    adjustment = sum(differences)
    x0_total = sum(map(sum, x0))
    ri = adjustment / x0_total
    active_ids = [instance.depot_ids[i] for i, value in enumerate(y) if value]
    x0_active_ids = [instance.depot_ids[i] for i, value in enumerate(y0) if value]
    positive_inventory_ids = [
        instance.depot_ids[i] for i, row in enumerate(x)
        if sum(row) > manifest["materiality_tolerance"]
    ]
    x0_positive_inventory_ids = [
        instance.depot_ids[i] for i, row in enumerate(x0)
        if sum(row) > manifest["materiality_tolerance"]
    ]
    opened = sorted(set(active_ids) - set(x0_active_ids))
    closed = sorted(set(x0_active_ids) - set(active_ids))
    changed_count = sum(value > manifest["materiality_tolerance"] for value in differences)
    budget_used = fixed + inventory + reconfiguration
    component_recourse = result["shortage_cost"] + result["transportation_cost"] + result["service_penalty"]
    source_solution_path = None
    source_commit = None
    if plan["classification"] == "REUSE":
        source_root = runner.E3_ROOT if plan["selected_source_experiment"] == "E3" else runner.E4_ROOT
        source_directory = source_root / plan["selected_source_run"]
        source_solution_path = source_directory / "first_stage_solution.json"
        source_commit = json.loads(source_solution_path.read_text(encoding="utf-8"))[
            "git_commit"
        ]
    feasibility = {
        "nonnegative": min(value for row in x for value in row) >= -1e-6
        and min(value for row in a_plus for value in row) >= -1e-6
        and min(value for row in a_minus for value in row) >= -1e-6,
        "balance": max(
            abs(x[i][j] - x0[i][j] - a_plus[i][j] + a_minus[i][j])
            for i in range(instance.num_depots) for j in range(instance.num_products)
        ) <= 1e-5,
        "capacity": all(
            sum(instance.product_volume[j] * x[i][j] for j in range(instance.num_products))
            <= instance.capacity[i] * y[i] + 1e-5
            for i in range(instance.num_depots)
        ),
        "upper_bound": all(
            x[i][j] <= instance.inventory_upper_bound[i][j] * y[i] + 1e-5
            for i in range(instance.num_depots) for j in range(instance.num_products)
        ),
        "budget": budget_used <= result["B"] + manifest["budget_feasibility_tolerance"],
    }
    checks = {
        "run_identity": result["run_id"] == provenance["run_id"] == condition.run_id,
        "condition_identity": result["case"] == condition.case
        and result["beta_token"] == condition.beta_token
        and result["Gamma_token"] == condition.gamma_token
        and result["lambda_R"] == manifest["lambda_R"],
        "dataset_and_model_identity": result["dataset_id"] == manifest["dataset_id"]
        and result["model_identity_sha256"] == manifest["model_identity_sha256"]
        and result["prb_identity_sha256"] == manifest["prb_identity_sha256"],
        "schema_required_fields": set(schema["required"]) <= set(result),
        "result_hash": provenance["result_sha256"] == sha256(result_path),
        "solution_hash": provenance["first_stage_solution_sha256"] == sha256(solution_path),
        "historical_runner_hash": provenance["runner_sha256"] == runner.git_file_sha256(
            provenance["git_commit"], "experiments/run_e6_budget_risk_local.py"
        ),
        "historical_manifest_hash": provenance["manifest_sha256"] == runner.git_file_sha256(
            provenance["git_commit"],
            "experiments/configs/formal/e6_budget_risk_interaction_authorization.json",
        ),
        "solution_commit": solution["git_commit"]
        == (source_commit if source_commit is not None else provenance["git_commit"]),
        "reused_solution_identity": source_solution_path is None
        or sha256(source_solution_path) == sha256(solution_path),
        "status": result["status"] == "OPTIMAL",
        "certification": result["certification_status"] == "CERTIFIED_PRB_EXACT"
        and result["exact_certification_pass"] is True,
        "reuse_classification": result["reused"] == (plan["classification"] == "REUSE"),
        "reuse_source": result["reuse_source_run"] == plan["selected_source_run"],
        "objective_accounting": abs(result["objective"] - budget_used - result["robust_recourse_cost"]) <= TOLERANCE,
        "recourse_component_accounting": abs(result["robust_recourse_cost"] - component_recourse) <= TOLERANCE,
        "fixed_cost": abs(result["fixed_cost"] - fixed) <= TOLERANCE,
        "inventory_cost": abs(result["inventory_cost"] - inventory) <= TOLERANCE,
        "reconfiguration_cost": abs(result["reconfiguration_cost"] - reconfiguration) <= TOLERANCE,
        "canonical_adjustment": abs(result["canonical_total_adjustment"] - adjustment) <= 1e-6,
        "RI": abs(result["RI"] - ri) <= 1e-9,
        "changed_pairs": result["changed_pair_count"] == changed_count,
        "active_depots": result["active_depots"] == len(active_ids)
        and result["active_depot_ids"] == active_ids,
        "opened_closed": sorted(result["opened_depots"]) == opened
        and sorted(result["closed_depots"]) == closed,
        "solution_accounting": abs(solution["objective"] - result["objective"]) <= TOLERANCE
        and abs(solution["first_stage_expenditure"] - budget_used) <= TOLERANCE
        and abs(solution["robust_recourse_cost"] - result["robust_recourse_cost"]) <= TOLERANCE,
        **{f"feasible_{key}": value for key, value in feasibility.items()},
    }
    errors.extend(key for key, passed in checks.items() if not passed)
    coupling = result.get("global_coupling_pass")
    if coupling is False:
        errors.append("global_coupling_failure")
    coupling_classification = (
        "PASS" if coupling is True else
        "SOURCE_SCHEMA_FIELD_UNAVAILABLE_NOT_FAILURE" if result["reused"] and coupling is None else
        "FAIL"
    )
    row = {
        **result,
        "recomputed_fixed_cost": fixed,
        "recomputed_inventory_cost": inventory,
        "solver_based_total_adjustment": solver_adjustment,
        "recomputed_reconfiguration_cost": reconfiguration,
        "recomputed_budget_used": budget_used,
        "recomputed_canonical_total_adjustment": adjustment,
        "recomputed_RI": ri,
        "recomputed_RS": reconfiguration / result["B"],
        "adjustment_max_coordinate_share": max(differences) / adjustment if adjustment else 0.0,
        "x0_y_active_depot_count": len(x0_active_ids),
        "x0_y_active_depot_ids": "|".join(x0_active_ids),
        "final_y_active_depot_count": len(active_ids),
        "final_y_active_depot_ids": "|".join(active_ids),
        "opened_y_depot_ids": "|".join(opened),
        "closed_y_depot_ids": "|".join(closed),
        "y_network_change": bool(opened or closed),
        "x0_positive_inventory_depot_count": len(x0_positive_inventory_ids),
        "final_positive_inventory_depot_count": len(positive_inventory_ids),
        "positive_inventory_depot_ids": "|".join(positive_inventory_ids),
        "positive_inventory_footprint_change": set(positive_inventory_ids) != set(x0_positive_inventory_ids),
        "global_coupling_diagnostic_classification": coupling_classification,
        "static_first_stage_feasibility_pass": all(feasibility.values()),
        "primary_artifact_integrity_pass": not errors,
        "adjustment_fingerprint": runner.canonical_hash([round(value, 10) for value in differences]),
        "x_fingerprint": runner.canonical_hash(
            [round(value, 10) for matrix_row in x for value in matrix_row]
        ),
        "_x_values": [value for matrix_row in x for value in matrix_row],
    }
    depot = {
        "case": condition.case,
        "beta_token": condition.beta_token,
        "beta": float(condition.beta),
        "Gamma_token": condition.gamma_token,
        "Gamma": condition.gamma,
        "x0_y_active_depot_count": len(x0_active_ids),
        "final_y_active_depot_count": len(active_ids),
        "x0_y_active_depot_ids": "|".join(x0_active_ids),
        "final_y_active_depot_ids": "|".join(active_ids),
        "opened_y_depot_ids": "|".join(opened),
        "closed_y_depot_ids": "|".join(closed),
        "y_network_change": bool(opened or closed),
        "x0_positive_inventory_depot_count": len(x0_positive_inventory_ids),
        "final_positive_inventory_depot_count": len(positive_inventory_ids),
        "positive_inventory_footprint_change": set(positive_inventory_ids) != set(x0_positive_inventory_ids),
    }
    return row, depot, errors


def _add_reference_metrics(rows: list[dict]) -> None:
    indexed = {(row["case"], row["beta_token"], row["Gamma"]): row for row in rows}
    for row in rows:
        reference = indexed[(row["case"], "B100", 2)]
        same_budget_g0 = indexed[(row["case"], row["beta_token"], 0)]
        row["normalized_objective"] = row["objective"] / reference["objective"]
        row["normalized_robust_recourse"] = row["robust_recourse_cost"] / reference["robust_recourse_cost"]
        x_differences = [
            abs(value - reference_value)
            for value, reference_value in zip(row["_x_values"], same_budget_g0["_x_values"])
        ]
        row["x_composition_changed_vs_same_beta_G0"] = any(value > 1e-6 for value in x_differences)
        row["x_L1_difference_vs_same_beta_G0"] = sum(x_differences)
        row["x_max_difference_vs_same_beta_G0"] = max(x_differences)
        row["x_differing_coordinate_count_vs_same_beta_G0"] = sum(
            value > 1e-6 for value in x_differences
        )
        row["RI_change_vs_same_beta_G0"] = row["RI"] - same_budget_g0["RI"]
        row["objective_change_vs_same_beta_G0"] = row["objective"] - same_budget_g0["objective"]
        row["recourse_change_vs_same_beta_G0"] = (
            row["robust_recourse_cost"] - same_budget_g0["robust_recourse_cost"]
        )


AGGREGATE_METRICS = (
    "objective", "normalized_objective", "robust_recourse_cost", "normalized_robust_recourse",
    "fixed_cost", "inventory_cost", "reconfiguration_cost", "RI", "RS",
    "canonical_total_adjustment", "budget_utilization", "budget_slack",
    "inventory_spending_share", "reconfiguration_spending_share", "shortage_cost",
    "transportation_cost", "service_penalty", "total_shortage", "minimum_fill_rate",
    "average_fill_rate", "active_depots", "runtime_seconds", "iterations", "cuts",
    "master_solves", "subproblem_evaluations",
)


def aggregate_rows(rows: list[dict]) -> list[dict]:
    output = []
    for beta_token, beta in runner.BETA_BY_TOKEN.items():
        for gamma_token, gamma in runner.GAMMA_BY_TOKEN.items():
            cell = [row for row in rows if row["beta_token"] == beta_token and row["Gamma"] == gamma]
            summary = {
                "beta_token": beta_token,
                "beta": float(beta),
                "Gamma_token": gamma_token,
                "Gamma": gamma,
                "case_count": len(cell),
                "material_case_count": sum(row["material_reconfiguration"] for row in cell),
                "active_depot_change_case_count": sum(row["y_network_change"] for row in cell),
                "positive_inventory_footprint_change_case_count": sum(
                    row["positive_inventory_footprint_change"] for row in cell
                ),
                "budget_binding_case_count": sum(row["budget_binding"] for row in cell),
                "composition_change_vs_G0_case_count": sum(
                    row["x_composition_changed_vs_same_beta_G0"] for row in cell
                ),
            }
            for metric in AGGREGATE_METRICS:
                values = [float(row[metric]) for row in cell]
                summary[f"mean_{metric}"] = statistics.mean(values)
                summary[f"median_{metric}"] = statistics.median(values)
                summary[f"min_{metric}"] = min(values)
                summary[f"max_{metric}"] = max(values)
            output.append(summary)
    return output


def _first_material(indexed: dict, beta: float, tolerance: float) -> str:
    for gamma in (0, 2, 4):
        if indexed[(beta, gamma)]["RI"] > tolerance:
            return str(gamma)
    return "none_through_4"


def contrast_rows(rows: list[dict], manifest: dict) -> list[dict]:
    output = []
    for case in runner.CASES:
        indexed = {
            (float(row["beta"]), int(row["Gamma"])): row
            for row in rows if row["case"] == case
        }
        values = {"case": case}
        for beta in (0.8, 1.0, 1.2):
            token = f"B{int(beta * 100):03d}"
            g0, g4 = indexed[(beta, 0)], indexed[(beta, 4)]
            for name, field in (
                ("RI", "RI"), ("objective", "objective"),
                ("recourse", "robust_recourse_cost"), ("RS", "RS")
            ):
                delta = float(g4[field]) - float(g0[field])
                values[f"delta_Gamma_{name}_{token}"] = delta
                values[f"percent_change_Gamma_{name}_{token}"] = (
                    delta / float(g0[field]) if float(g0[field]) else None
                )
            values[f"first_material_gamma_{token}"] = _first_material(
                indexed, beta, manifest["materiality_tolerance"]
            )
            values[f"active_depot_change_any_{token}"] = any(
                indexed[(beta, gamma)]["y_network_change"] for gamma in (0, 2, 4)
            )
            values[f"composition_change_G0_to_G4_{token}"] = (
                g4["x_composition_changed_vs_same_beta_G0"]
            )
            values[f"x_L1_change_G0_to_G4_{token}"] = g4[
                "x_L1_difference_vs_same_beta_G0"
            ]
            values[f"x_coordinate_changes_G0_to_G4_{token}"] = g4[
                "x_differing_coordinate_count_vs_same_beta_G0"
            ]
            values[f"budget_binding_transition_{token}"] = (
                g0["budget_binding"] != g4["budget_binding"]
            )
        values["DID_RI_tight_vs_relaxed"] = (
            values["delta_Gamma_RI_B080"] - values["delta_Gamma_RI_B120"]
        )
        values["DID_RI_reference_vs_relaxed"] = (
            values["delta_Gamma_RI_B100"] - values["delta_Gamma_RI_B120"]
        )
        values["DID_objective_tight_vs_relaxed"] = (
            values["delta_Gamma_objective_B080"] - values["delta_Gamma_objective_B120"]
        )
        values["DID_recourse_tight_vs_relaxed"] = (
            values["delta_Gamma_recourse_B080"] - values["delta_Gamma_recourse_B120"]
        )
        b080_material_at_g0 = indexed[(0.8, 0)]["material_reconfiguration"]
        values["extensive_intensive_classification"] = (
            "INTENSIVE_MARGIN_FROM_G0" if b080_material_at_g0 else "EXTENSIVE_MARGIN_AFTER_G0"
        )
        labels = []
        if abs(values["delta_Gamma_RI_B080"]) <= 1e-3:
            labels.append("SCARCITY_INDUCED_RECONFIGURATION_SATURATION")
        if values["DID_RI_tight_vs_relaxed"] < -manifest["materiality_tolerance"]:
            labels.append("RISK_RESPONSE_SUPPRESSED_BY_SCARCITY")
        if values["composition_change_G0_to_G4_B080"]:
            labels.append("AGGREGATE_RI_INVARIANT_BUT_COMPOSITION_CHANGES")
        if not labels:
            labels.append("MIXED_CASE_SPECIFIC_INTERACTION")
        values["mechanism_classification"] = "|".join(labels)
        output.append(values)
    return output


def main() -> None:
    manifest = runner.load_manifest()
    runner.validate_manifest(manifest)
    directories, results = _read_results()
    plan_rows = runner.build_reuse_plan(manifest)
    plan = {row["run_id"]: row for row in plan_rows}
    completion = _completion_times(directories)
    rows = []
    depot_rows = []
    runtime_rows = []
    failures = {}
    primary_hashes = {}
    for condition in runner.enumerate_conditions():
        directory = directories[condition.run_id]
        row, depot, errors = _audit_run(
            condition, directory, results[condition.run_id], plan[condition.run_id], manifest
        )
        rows.append(row)
        depot_rows.append(depot)
        runtime_rows.append(_runtime_row(results[condition.run_id], directory, completion[condition.run_id]))
        if errors:
            failures[condition.run_id] = errors
        primary_hashes[condition.run_id] = {
            filename: sha256(directory / filename)
            for filename in ("result.json", "first_stage_solution.json", "provenance.json")
        }
    _add_reference_metrics(rows)
    for row in rows:
        del row["_x_values"]
    aggregate = aggregate_rows(rows)
    contrasts = contrast_rows(rows, manifest)
    prior_audit = json.loads((ARTIFACTS / "e6_static_audit.json").read_text(encoding="utf-8"))
    current_protected = {
        name: tree_identity(ROOT / f"experiments/results/e{number}_{suffix}")
        for name, number, suffix in (
            ("E1", 1, "empirical_8case_v1"),
            ("E2", 2, "existing_nominal_robust_v1"),
            ("E3", 3, "budget_sensitivity_v1"),
            ("E4", 4, "gamma_sensitivity_v1"),
            ("E5", 5, "reconfiguration_friction_v1"),
        )
    }
    protected_preserved = current_protected == prior_audit["protected_result_root_identities"]
    package = _package_comparison(directories)
    status = (
        "E6_FINAL_AUDIT_PASS_WITH_RUNTIME_ACCOUNTING_LIMITATION"
        if not failures and protected_preserved and package.get("classification") != "MISMATCH"
        else "E6_FINAL_AUDIT_BLOCKED"
    )
    audit = {
        "schema": "e6_final_result_audit_v1",
        "status": status,
        "E6_RESULTS_COMPLETE": len(rows) == 72,
        "total_conditions": len(rows),
        "optimal_status_count": sum(row["status"] == "OPTIMAL" for row in rows),
        "exact_certification_pass_count": sum(row["exact_certification_pass"] for row in rows),
        "reuse_count": sum(row["reused"] for row in rows),
        "new_solve_count": sum(not row["reused"] for row in rows),
        "global_coupling_pass_count": sum(row.get("global_coupling_pass") is True for row in rows),
        "global_coupling_source_field_unavailable_count": sum(
            row["global_coupling_diagnostic_classification"]
            == "SOURCE_SCHEMA_FIELD_UNAVAILABLE_NOT_FAILURE" for row in rows
        ),
        "failures": failures,
        "reuse_provenance_identity_valid": not any(
            any(error.startswith("reuse_") for error in errors) for errors in failures.values()
        ),
        "protected_E1_E5_hashes_preserved": protected_preserved,
        "protected_result_root_identities": current_protected,
        "review_package_comparison": package,
        "primary_artifact_hashes": primary_hashes,
        "runtime_accounting": {
            "reported_runtime_definition": (
                "perf_counter from immediately before PRB master construction through final exact "
                "product recourse certification; includes PRB master and separation loop and final "
                "product certification"
            ),
            "excluded": [
                "instance and x0 loading before solve_prb_benders",
                "evaluate_e4_service exact service/reporting evaluation",
                "cost and mechanism metric construction",
                "first-stage artifact construction",
                "JSON, provenance, hashing, and atomic artifact writes",
                "process startup and external idle time",
            ],
            "Gamma4_post_evaluation_product_risk_blocks": 6352,
            "Gamma4_post_evaluation_global_scenarios": 3469497,
            "exact_wallclock_reconstructable": False,
            "limitation": "no runner start timestamp or stage timers persisted",
            "classification": [
                "CORE_SOLVER_TIME_ONLY",
                "POST_EVALUATION_EXCLUDED_FROM_TIMER",
                "RUNNER_WALLCLOCK_NOT_CAPTURED",
                "MULTI_STAGE_TIMING_ACCOUNTING_GAP",
            ],
        },
        "E6_new_first_stage_optimization_solves": 0,
        "E6_primary_results_overwritten": False,
    }
    write_csv(CASE_TABLE, rows)
    write_csv(AGGREGATE_TABLE, aggregate)
    write_csv(CONTRAST_TABLE, contrasts)
    write_csv(DEPOT_TABLE, depot_rows)
    write_csv(RUNTIME_TABLE, runtime_rows)
    FINAL_AUDIT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(status)
    if status == "E6_FINAL_AUDIT_BLOCKED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
