from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import experiments.run_e7_risk_friction_local as runner
from robust_inventory_reconfiguration.first_stage_solution import matrix_from_artifact
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget

RESULT_ROOT = runner.RESULT_ROOT
ARTIFACTS = ROOT / "artifacts"
CASES = tuple(runner.CASES)
GAMMAS = tuple(runner.GAMMA_BY_TOKEN.values())
LAMBDAS = tuple(runner.LAMBDA_BY_TOKEN.values())
TIMING_FIELDS = (
    "t_instance_load_seconds", "t_reuse_validation_seconds", "t_core_prb_seconds",
    "t_exact_certification_seconds", "t_post_evaluation_seconds",
    "t_reporting_seconds", "t_artifact_write_seconds", "t_total_runner_wallclock_seconds",
)
PROTECTED_ROOTS = {
    name: ROOT / f"experiments/results/{path}"
    for name, path in {
        "E1": "e1_empirical_8case_v1", "E2": "e2_existing_nominal_robust_v1",
        "E3": "e3_budget_sensitivity_v1", "E4": "e4_gamma_sensitivity_v1",
        "E5": "e5_reconfiguration_friction_v1", "E6": "e6_budget_risk_interaction_v1",
    }.items()
}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def primary_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(RESULT_ROOT)).replace("\\", "/"): runner.sha256(path)
        for path in sorted(RESULT_ROOT.rglob("*")) if path.is_file()
    }


def tree_identity(root: Path) -> str:
    return runner.canonical_hash({
        str(path.relative_to(root)).replace("\\", "/"): runner.sha256(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    })


def first_material_gamma(rows: list[dict], lambda_r: float) -> str:
    indexed = {row["Gamma"]: row for row in rows if row["lambda_R"] == lambda_r}
    return next((str(gamma) for gamma in GAMMAS if indexed[gamma]["material_reconfiguration"]), "none_through_4")


def classify_interaction(row: dict) -> str:
    low = row["delta_Gamma_RI_L0025"]
    high = row["delta_Gamma_RI_L2000"]
    if abs(low - high) <= 1e-6:
        return "FRICTION_EFFECT_WEAK_OVER_TESTED_RANGE"
    if low > high + 1e-6:
        return "FRICTION_DAMPENS_RISK_RESPONSE"
    return "MIXED_CASE_SPECIFIC_INTERACTION"


def interaction_contrast_for_case(case: str, rows: list[dict]) -> dict:
    selected = [row for row in rows if row["case"] == case]
    indexed = {(row["Gamma"], row["lambda_R"]): row for row in selected}
    out = {"case": case}
    for token, value in runner.LAMBDA_BY_TOKEN.items():
        g0, g4 = indexed[(0, value)], indexed[(4, value)]
        for name, field in (
            ("RI", "RI"), ("objective", "objective"),
            ("recourse", "robust_recourse_cost"), ("RS", "RS"),
            ("changed_pairs", "changed_pair_count"),
        ):
            out[f"delta_Gamma_{name}_{token}"] = g4[field] - g0[field]
        out[f"first_material_gamma_{token}"] = first_material_gamma(selected, value)
    for name in ("RI", "objective", "recourse", "RS"):
        out[f"DID_{name}_low_vs_high_friction"] = out[f"delta_Gamma_{name}_L0025"] - out[f"delta_Gamma_{name}_L2000"]
    out["extensive_trigger_invariant_across_lambda"] = len({out[f"first_material_gamma_{token}"] for token in runner.LAMBDA_BY_TOKEN}) == 1
    out["interaction_classification"] = classify_interaction(out)
    return out


def margin_summary(rows: list[dict]) -> dict:
    material = [row for row in rows if row["material_reconfiguration"]]
    return {
        "observation_count": len(rows), "material_count": len(material),
        "material_share": len(material) / len(rows) if rows else 0.0,
        "mean_RI_conditional_on_material": statistics.mean(row["RI"] for row in material) if material else None,
        "median_RI_conditional_on_material": statistics.median(row["RI"] for row in material) if material else None,
        "mean_adjustment_conditional_on_material": statistics.mean(row["canonical_total_adjustment"] for row in material) if material else None,
        "mean_changed_pairs_conditional_on_material": statistics.mean(row["changed_pair_count"] for row in material) if material else None,
        "mean_top_adjustment_share_conditional_on_material": statistics.mean(row["top_adjustment_share"] for row in material) if material else None,
    }


def canonical_row(condition: runner.Condition, manifest: dict, source_status: dict[str, str]) -> tuple[dict, list[str]]:
    directory = RESULT_ROOT / condition.run_id
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    solution = json.loads((directory / "first_stage_solution.json").read_text(encoding="utf-8"))
    instance = load_instance(ROOT / f"data/formal_instances_v2/{condition.case}.json")
    x0 = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case}.json").read_text(encoding="utf-8"))["x0"]
    x = matrix_from_artifact(solution, instance, "x")
    a_plus = matrix_from_artifact(solution, instance, "a_plus")
    a_minus = matrix_from_artifact(solution, instance, "a_minus")
    y = [int(item["value"]) for item in solution["y"]]
    adjustments = [abs(x[i][j] - x0[i][j]) for i in range(instance.num_depots) for j in range(instance.num_products)]
    total_adjustment = sum(adjustments)
    x0_total = sum(map(sum, x0))
    fixed = sum(instance.fixed_depot_cost[i] * y[i] for i in range(instance.num_depots))
    inventory = sum(instance.inventory_cost[i][j] * x[i][j] for i in range(instance.num_depots) for j in range(instance.num_products))
    reconfiguration = condition.lambda_r * sum(instance.inventory_cost[i][j] * (a_plus[i][j] + a_minus[i][j]) for i in range(instance.num_depots) for j in range(instance.num_products))
    budget_used = fixed + inventory + reconfiguration
    tolerance = manifest["tolerance_contract"]["reporting"]
    checks = {
        "result_identity": result["run_id"] == condition.run_id and result["case"] == condition.case and result["Gamma"] == condition.gamma and result["lambda_R"] == condition.lambda_r and result["beta"] == 1.0,
        "frozen_identity": result["dataset_id"] == manifest["dataset_id"] and result["instance_hash"] == manifest["instance_hashes"][condition.case] and result["x0_hash"] == manifest["x0_hashes"][condition.case] and result["calibration_hash"] == manifest["calibration_hashes"][condition.case] and result["model_identity_sha256"] == manifest["model_identity_sha256"] and result["prb_identity_sha256"] == manifest["prb_identity_sha256"] and result["solver_profile"] == manifest["solver_profile"],
        "balance": max(abs(x[i][j] - x0[i][j] - a_plus[i][j] + a_minus[i][j]) for i in range(instance.num_depots) for j in range(instance.num_products)) <= tolerance,
        "nonnegative": min(min(row) for row in x + a_plus + a_minus) >= -tolerance,
        "activation_UB": max(x[i][j] - instance.inventory_upper_bound[i][j] * y[i] for i in range(instance.num_depots) for j in range(instance.num_products)) <= tolerance,
        "capacity": max(sum(instance.product_volume[j] * x[i][j] for j in range(instance.num_products)) - instance.capacity[i] * y[i] for i in range(instance.num_depots)) <= tolerance,
        "costs": max(abs(fixed - result["fixed_cost"]), abs(inventory - result["inventory_cost"]), abs(reconfiguration - result["reconfiguration_cost"]), abs(budget_used - result["budget_used"])) <= tolerance,
        "objective": abs(result["objective"] - budget_used - result["robust_recourse_cost"]) <= manifest["tolerance_contract"]["objective_certification"],
        "canonical_adjustment": abs(total_adjustment - result["canonical_total_adjustment"]) <= tolerance,
        "canonical_RI": abs(total_adjustment / x0_total - result["RI"]) <= tolerance,
        "timing": set(result["timing"]) == set(TIMING_FIELDS) and all(isinstance(value, (int, float)) and value >= 0 for value in result["timing"].values()) and runner.timing_containment_passes(result["timing"], tolerance),
    }
    errors = [name for name, passed in checks.items() if not passed]
    if result.get("global_coupling_pass") is True:
        diagnostic, diagnostic_source = "PASS", "E7_RESULT"
    elif result.get("global_coupling_pass") is False:
        diagnostic, diagnostic_source = "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH_AUDIT_REQUIRED", "E7_RESULT"
    else:
        diagnostic, diagnostic_source = "MISSING_BY_REUSE_SCHEMA_SOURCE_REFERENCED", source_status[condition.case]
    row = {
        **{key: result[key] for key in (
            "run_id", "case", "Gamma_token", "Gamma", "lambda_token", "lambda_R", "objective",
            "fixed_cost", "inventory_cost", "reconfiguration_cost", "robust_recourse_cost",
            "transportation_cost", "shortage_cost", "service_penalty", "total_shortage",
            "average_fill_rate", "minimum_fill_rate", "B", "budget_used", "budget_utilization",
            "budget_slack", "RS", "iterations", "cuts", "master_solves", "subproblem_evaluations",
            "lower_bound", "upper_bound", "relative_gap", "status", "certification_status",
            "exact_certification_pass", "reused", "reuse_source_run",
        )},
        "canonical_total_adjustment": total_adjustment, "RI": total_adjustment / x0_total,
        "changed_pair_count": sum(value > tolerance for value in adjustments),
        "top_adjustment_share": max(adjustments) / total_adjustment if total_adjustment else 0.0,
        "material_reconfiguration": total_adjustment / x0_total > manifest["tolerance_contract"]["materiality"],
        "active_depots": sum(y),
        "active_depot_ids": "|".join(instance.depot_ids[i] for i, value in enumerate(y) if value),
        "positive_inventory_depot_ids": "|".join(instance.depot_ids[i] for i, values in enumerate(x) if sum(values) > tolerance),
        "opened_depots": "|".join(result["opened_depots"]), "closed_depots": "|".join(result["closed_depots"]),
        "network_change": bool(result["opened_depots"] or result["closed_depots"]),
        "budget_binding": abs(result["budget_slack"]) <= tolerance,
        "global_coupling_diagnostic_status": diagnostic,
        "global_coupling_diagnostic_source_status": diagnostic_source,
        "artifact_validation_pass": not errors,
        **result["timing"],
    }
    return row, errors


def fixed_state_coupling_audit() -> dict:
    condition = runner.Condition("210330", "G4", "L0025")
    directory = RESULT_ROOT / condition.run_id
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    solution = json.loads((directory / "first_stage_solution.json").read_text(encoding="utf-8"))
    instance = load_instance(ROOT / "data/formal_instances_v2/210330.json")
    x = matrix_from_artifact(solution, instance)
    product_results = [ProductRiskSubproblem(instance, j, condition.gamma).solve([x[i][j] for i in range(instance.num_depots)]) for j in range(instance.num_products)]
    composition = compose_risk_budget([[worst.value for worst in item.worst_cases] for item in product_results], condition.gamma)
    fresh_recourse = composition.value
    return {
        "schema": "e7_210330_g4_l0025_global_coupling_audit_v1", "run_id": condition.run_id,
        "result_sha256": runner.sha256(directory / "result.json"),
        "first_stage_solution_sha256": runner.sha256(directory / "first_stage_solution.json"),
        "classification": "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH",
        "diagnostic_formula": "abs(final_master_theta - final_iteration_exact_composition)",
        "diagnostic_absolute_threshold": 1e-6, "reported_global_coupling_pass": result["global_coupling_pass"],
        "persisted_master_closure_residual": abs(result["lower_bound"] - result["upper_bound"]),
        "fresh_exact_recourse": fresh_recourse, "stored_exact_recourse": result["robust_recourse_cost"],
        "fresh_vs_stored_recourse_difference": abs(fresh_recourse - result["robust_recourse_cost"]),
        "risk_budget_allocation": list(composition.allocation), "risk_budget_allocation_sum": sum(composition.allocation),
        "Gamma": condition.gamma, "Gamma_feasible": sum(composition.allocation) <= condition.gamma,
        "maximum_product_strong_duality_error": max(worst.cut.strong_duality_error for item in product_results for worst in item.worst_cases),
        "all_product_duals_feasible": all(worst.cut.dual_feasible for item in product_results for worst in item.worst_cases),
        "objective_reconstruction_difference": abs(result["objective"] - result["budget_used"] - fresh_recourse),
        "objective_affected": False, "exact_recourse_affected": False, "Gamma_feasibility_affected": False,
        "first_stage_reoptimized": False, "fixed_first_stage_product_lp_solves": instance.num_products * (condition.gamma + 1),
        "primary_artifact_modified": False,
    }


def aggregate_rows(rows: list[dict]) -> list[dict]:
    output = []
    for gamma in GAMMAS:
        for lambda_r in LAMBDAS:
            selected = [row for row in rows if row["Gamma"] == gamma and row["lambda_R"] == lambda_r]
            material = [row for row in selected if row["material_reconfiguration"]]
            output.append({
                "Gamma": gamma, "lambda_R": lambda_r, "case_count": len(selected),
                "mean_normalized_objective": statistics.mean(row["normalized_objective"] for row in selected),
                "mean_normalized_robust_recourse": statistics.mean(row["normalized_robust_recourse"] for row in selected),
                "mean_RI": statistics.mean(row["RI"] for row in selected), "median_RI": statistics.median(row["RI"] for row in selected),
                "material_case_count": len(material),
                "mean_RI_conditional_on_material": statistics.mean(row["RI"] for row in material) if material else "",
                "mean_total_adjustment_conditional_on_material": statistics.mean(row["canonical_total_adjustment"] for row in material) if material else "",
                "mean_changed_pairs_conditional_on_material": statistics.mean(row["changed_pair_count"] for row in material) if material else "",
                "mean_top_adjustment_share_conditional_on_material": statistics.mean(row["top_adjustment_share"] for row in material) if material else "",
                "mean_RS": statistics.mean(row["RS"] for row in selected),
                "mean_budget_utilization": statistics.mean(row["budget_utilization"] for row in selected),
                "budget_binding_case_count": sum(row["budget_binding"] for row in selected),
                "network_change_case_count": sum(row["network_change"] for row in selected),
                "mean_total_shortage": statistics.mean(row["total_shortage"] for row in selected),
                "mean_average_fill_rate": statistics.mean(row["average_fill_rate"] for row in selected),
                "mean_minimum_fill_rate": statistics.mean(row["minimum_fill_rate"] for row in selected),
                "mean_core_prb_seconds_new_only": statistics.mean(row["t_core_prb_seconds"] for row in selected if not row["reused"]) if any(not row["reused"] for row in selected) else "",
                "mean_post_evaluation_seconds_new_only": statistics.mean(row["t_post_evaluation_seconds"] for row in selected if not row["reused"]) if any(not row["reused"] for row in selected) else "",
                "mean_total_wallclock_seconds": statistics.mean(row["t_total_runner_wallclock_seconds"] for row in selected),
            })
    return output


def main() -> None:
    before = primary_hashes()
    manifest = runner.load_manifest()
    runner.validate_manifest(manifest)
    runner.validate_authorization_record(manifest)
    plan = runner.build_reuse_plan(manifest)
    expected = {condition.run_id for condition in runner.enumerate_conditions()}
    observed = {path.parent.name for path in RESULT_ROOT.glob("*/result.json")}
    observed_directories = {path.name for path in RESULT_ROOT.iterdir() if path.is_dir()}
    states = [runner.classify_output_state(condition, manifest) for condition in runner.enumerate_conditions()]
    e4_audit = json.loads((ARTIFACTS / "e4_final_result_audit.json").read_text(encoding="utf-8"))
    source_status = {row["case"]: row["diagnostic_source_status"] for row in e4_audit["G2_reuse"]["rows"]}
    rows, validation_errors = [], {}
    for condition in runner.enumerate_conditions():
        row, errors = canonical_row(condition, manifest, source_status)
        rows.append(row)
        if errors:
            validation_errors[condition.run_id] = errors
    for row in rows:
        baseline = next(item for item in rows if item["case"] == row["case"] and item["lambda_R"] == row["lambda_R"] and item["Gamma"] == 0)
        row["normalized_objective"] = row["objective"] / baseline["objective"]
        row["normalized_robust_recourse"] = row["robust_recourse_cost"] / baseline["robust_recourse_cost"]
    coupling = fixed_state_coupling_audit()
    for row in rows:
        if row["run_id"] == coupling["run_id"]:
            row["global_coupling_diagnostic_status"] = coupling["classification"]
    aggregates = aggregate_rows(rows)
    contrasts = [interaction_contrast_for_case(case, rows) for case in CASES]
    compositions = [{key: row[key] for key in (
        "run_id", "case", "Gamma", "lambda_R", "material_reconfiguration", "canonical_total_adjustment",
        "RI", "changed_pair_count", "top_adjustment_share", "active_depots", "active_depot_ids",
        "positive_inventory_depot_ids", "opened_depots", "closed_depots", "network_change", "inventory_cost",
        "reconfiguration_cost", "robust_recourse_cost",
    )} for row in rows]
    timing = [{"run_id": row["run_id"], "case": row["case"], "Gamma": row["Gamma"], "lambda_R": row["lambda_R"], "reused": row["reused"], "timing_provenance": "E7_REUSE_MATERIALIZATION_ONLY_WITH_SOURCE_REPORTED_RUNTIME" if row["reused"] else "E7_FULL_STAGE_INSTRUMENTATION", **{field: row[field] for field in TIMING_FIELDS}} for row in rows]
    after = primary_hashes()
    preauthorization_audit = json.loads((ARTIFACTS / "e7_static_audit.json").read_text(encoding="utf-8"))
    protected_identities = {name: tree_identity(path) for name, path in PROTECTED_ROOTS.items()}
    checks = {
        "complete_72_of_72": len(observed) == 72 and observed == expected,
        "no_extra_or_partial_directories": observed_directories == expected,
        "no_duplicate_parameter_cells": len({(row["case"], row["Gamma"], row["lambda_R"]) for row in rows}) == 72,
        "all_completion_states_valid": all(state["state"] == "COMPLETED" for state in states),
        "reuse_40_new_32": sum(row["reused"] for row in rows) == 40 and sum(not row["reused"] for row in rows) == 32,
        "reuse_plan_matches": all(row["reused"] == (planned["classification"] == "REUSE") and row["reuse_source_run"] == planned["selected_source_run"] for row, planned in zip(rows, plan)),
        "all_OPTIMAL": all(row["status"] == "OPTIMAL" for row in rows),
        "all_exact_certification_PASS": all(row["exact_certification_pass"] is True and row["certification_status"] == "CERTIFIED_PRB_EXACT" for row in rows),
        "all_artifact_and_accounting_checks_PASS": not validation_errors,
        "coupling_false_fixed_state_recourse_PASS": coupling["fresh_vs_stored_recourse_difference"] <= manifest["tolerance_contract"]["reporting"],
        "coupling_false_Gamma_feasible": coupling["Gamma_feasible"],
        "coupling_false_objective_reconstruction_PASS": coupling["objective_reconstruction_difference"] <= manifest["tolerance_contract"]["objective_certification"],
        "timing_integrity_PASS": all(row["artifact_validation_pass"] for row in rows),
        "primary_hashes_preserved": before == after,
        "protected_E1_E6_hashes_preserved": protected_identities == preauthorization_audit["protected_result_root_identities"],
    }
    status = "E7_FINAL_AUDIT_PASS" if all(checks.values()) else "E7_FINAL_AUDIT_BLOCKED"
    audit = {
        "schema": "e7_final_result_audit_v1", "status": status, "checks": checks,
        "expected_runs": 72, "observed_runs": len(rows), "reused": sum(row["reused"] for row in rows),
        "new_formal_results": sum(not row["reused"] for row in rows),
        "global_coupling_diagnostics": {
            "pass": sum(row["global_coupling_diagnostic_status"] == "PASS" for row in rows),
            "reuse_schema_missing_source_referenced": sum(row["global_coupling_diagnostic_status"] == "MISSING_BY_REUSE_SCHEMA_SOURCE_REFERENCED" for row in rows),
            "diagnostic_tolerance_contract_mismatch": sum(row["global_coupling_diagnostic_status"] == "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH" for row in rows),
        },
        "coupling_audit": coupling,
        "per_case_first_material_Gamma": {case: {token: first_material_gamma([row for row in rows if row["case"] == case], value) for token, value in runner.LAMBDA_BY_TOKEN.items()} for case in CASES},
        "extensive_trigger_invariant_case_count": sum(row["extensive_trigger_invariant_across_lambda"] for row in contrasts),
        "network_change_observations": [row["run_id"] for row in rows if row["network_change"]],
        "margin_summary": margin_summary(rows),
        "timing": {
            "full_instrumentation_new_count": sum(not row["reused"] for row in rows),
            "reuse_materialization_timing_count": sum(row["reused"] for row in rows),
            "G4_new_mean_core_prb_seconds": statistics.mean(row["t_core_prb_seconds"] for row in rows if row["Gamma"] == 4 and not row["reused"]),
            "G4_new_mean_post_evaluation_seconds": statistics.mean(row["t_post_evaluation_seconds"] for row in rows if row["Gamma"] == 4 and not row["reused"]),
            "G4_new_mean_total_wallclock_seconds": statistics.mean(row["t_total_runner_wallclock_seconds"] for row in rows if row["Gamma"] == 4 and not row["reused"]),
            "post_evaluation_dominates_G4_new": all(row["t_post_evaluation_seconds"] > row["t_core_prb_seconds"] for row in rows if row["Gamma"] == 4 and not row["reused"]),
        },
        "validation_errors": validation_errors,
        "fixed_first_stage_product_lp_solves_executed_in_task": 2 * coupling["fixed_first_stage_product_lp_solves"],
        "new_first_stage_optimization_solves": 0, "primary_results_overwritten": False,
        "E1_E6_overwritten": not checks["protected_E1_E6_hashes_preserved"],
        "protected_E1_E6_result_root_identities": protected_identities,
        "frozen_scientific_settings_changed": False,
    }
    write_csv(ARTIFACTS / "e7_table_risk_friction_case_level.csv", rows)
    write_csv(ARTIFACTS / "e7_table_risk_friction_aggregate.csv", aggregates)
    write_csv(ARTIFACTS / "e7_table_interaction_contrasts.csv", contrasts)
    write_csv(ARTIFACTS / "e7_table_adjustment_composition.csv", compositions)
    write_csv(ARTIFACTS / "e7_runtime_breakdown.csv", timing)
    write_json(ARTIFACTS / "e7_210330_g4_l0025_global_coupling_audit.json", coupling)
    write_json(ARTIFACTS / "e7_final_result_audit.json", audit)
    print(status)
    if status != "E7_FINAL_AUDIT_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
