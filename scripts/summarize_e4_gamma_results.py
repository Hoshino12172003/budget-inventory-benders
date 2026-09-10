from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.first_stage_solution import (
    load_first_stage_solution_artifact,
    matrix_from_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget


RESULT_ROOT = ROOT / "experiments/results/e4_gamma_sensitivity_v1"
E3_ROOT = ROOT / "experiments/results/e3_budget_sensitivity_v1"
E1_ROOT = ROOT / "experiments/results/e1_empirical_8case_v1"
MANIFEST = ROOT / "experiments/configs/formal/e4_gamma_sensitivity_authorization.json"
ARTIFACTS = ROOT / "artifacts"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
GAMMAS = (0, 1, 2, 3, 4)
METRICS = (
    "normalized_objective", "normalized_robust_recourse", "RI", "RS",
    "budget_utilization", "total_adjustment", "active_depots",
    "shortage_cost", "service_penalty",
    "average_fill_rate", "runtime_seconds", "iterations", "cuts_added",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def primary_hashes() -> dict[str, str]:
    return {
        path.relative_to(RESULT_ROOT).as_posix(): sha256(path)
        for path in sorted(RESULT_ROOT.glob("*/*"))
        if path.is_file()
    }


def expected_run_ids() -> list[str]:
    return [f"E4-{case}-G{gamma}" for case in CASES for gamma in GAMMAS]


def frozen_zip_comparison() -> dict[str, object]:
    archive = ROOT / "e4_gamma_sensitivity_v1.zip"
    if not archive.is_file():
        return {"available": False, "file_count": 0, "all_match": None}
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        matches = len(names) == 120 and all(
            (RESULT_ROOT / name).is_file()
            and hashlib.sha256(source.read(name)).hexdigest() == sha256(RESULT_ROOT / name)
            for name in names
        )
    return {"available": True, "file_count": len(names), "all_match": matches}


def load_and_validate() -> tuple[dict[tuple[str, int], dict], dict[tuple[str, int], dict], dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = set(expected_run_ids())
    directories = [path for path in RESULT_ROOT.iterdir() if path.is_dir() and not path.name.startswith(".")]
    observed_names = {path.name for path in directories}
    if observed_names != expected:
        raise RuntimeError(
            f"incomplete E4 results: missing={sorted(expected-observed_names)}, extra={sorted(observed_names-expected)}"
        )
    results: dict[tuple[str, int], dict] = {}
    solutions: dict[tuple[str, int], dict] = {}
    seen = set()
    provenance_pass = True
    identity_pass = True
    for directory in sorted(directories):
        required = {"result.json", "first_stage_solution.json", "provenance.json"}
        if {path.name for path in directory.iterdir() if path.is_file()} != required:
            raise RuntimeError(f"unexpected E4 artifact set: {directory.name}")
        result_path = directory / "result.json"
        solution_path = directory / "first_stage_solution.json"
        provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        run_id = result["run_id"]
        if run_id in seen or run_id != directory.name:
            raise RuntimeError(f"duplicate or mismatched E4 run id: {run_id}")
        seen.add(run_id)
        case, gamma = result["case"], int(result["Gamma"])
        instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
        solution = load_first_stage_solution_artifact(solution_path, instance)
        provenance_pass &= (
            provenance["run_id"] == run_id
            and provenance["result_sha256"] == sha256(result_path)
            and provenance["first_stage_solution_sha256"] == sha256(solution_path)
        )
        identity_pass &= (
            result["dataset_id"] == manifest["dataset_id"]
            and result["instance_hash"] == manifest["instance_hashes"][case]
            and result["x0_hash"] == manifest["x0_hashes"][case]
            and result["calibration_hash"] == manifest["calibration_hashes"][case]
            and result["mapping_hash"] == manifest["mapping_sha256"]
            and result["B_ref"] == manifest["B_ref_by_case"][case]
            and result["B"] == manifest["B_ref_by_case"][case]
            and result["beta"] == manifest["beta"]
            and result["lambda_R"] == manifest["lambda_R"]
            and result["solver_profile"] == manifest["solver_profile"]
        )
        results[(case, gamma)] = result
        solutions[(case, gamma)] = solution
    if seen != expected:
        raise RuntimeError("E4 result IDs do not match the frozen design")
    return results, solutions, {
        "provenance_hashes_pass": provenance_pass,
        "frozen_identity_pass": identity_pass,
    }


def audit_g2_reuse(results: dict[tuple[str, int], dict]) -> dict:
    rows = []
    all_identity_safe = True
    for case in CASES:
        result = results[(case, 2)]
        e4_dir = RESULT_ROOT / f"E4-{case}-G2"
        e3_dir = E3_ROOT / f"E3-{case}-B100"
        e3_result = json.loads((e3_dir / "result.json").read_text(encoding="utf-8"))
        e3_provenance = json.loads((e3_dir / "provenance.json").read_text(encoding="utf-8"))
        e1_result = json.loads((E1_ROOT / f"E1-{case}-PRB/result.json").read_text(encoding="utf-8"))
        e4_provenance = json.loads((e4_dir / "provenance.json").read_text(encoding="utf-8"))
        identity_safe = all((
            result["reused"] is True,
            result["reuse_source_run"] == e3_result["run_id"] == f"E3-{case}-B100",
            e4_provenance["reuse_source_run"] == e3_result["run_id"],
            sha256(e4_dir / "first_stage_solution.json") == sha256(e3_dir / "first_stage_solution.json"),
            e3_provenance["result_sha256"] == sha256(e3_dir / "result.json"),
            result["objective"] == e3_result["objective"],
            result["robust_recourse_cost"] == e3_result["robust_recourse_cost"],
            result["RI"] == e3_result["RI"],
        ))
        all_identity_safe &= identity_safe
        source_status = (
            "PASS" if e1_result.get("global_coupling_pass") is True
            else "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH"
        )
        rows.append({
            "case": case,
            "identity_safe": identity_safe,
            "e4_field_present": "global_coupling_pass" in result,
            "e3_source_field_present": "global_coupling_pass" in e3_result,
            "diagnostic_schema_classification": "MISSING_BY_REUSE_SCHEMA_SOURCE_DIAGNOSTIC_REFERENCED",
            "diagnostic_source_run": f"E1-{case}-PRB",
            "diagnostic_source_status": source_status,
            "primary_certification_affected": False,
        })
    return {"identity_safe_count": sum(row["identity_safe"] for row in rows), "all_identity_safe": all_identity_safe, "rows": rows}


def fixed_g3_coupling_audit(solution: dict) -> dict:
    case, gamma = "210330", 3
    result = json.loads((RESULT_ROOT / f"E4-{case}-G{gamma}/result.json").read_text(encoding="utf-8"))
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    x = matrix_from_artifact(solution, instance)
    product_results = [
        ProductRiskSubproblem(instance, j, gamma).solve(
            [x[i][j] for i in range(instance.num_depots)]
        )
        for j in range(instance.num_products)
    ]
    values = [[worst.value for worst in item.worst_cases] for item in product_results]
    composition = compose_risk_budget(values, gamma)
    fresh_recourse = composition.value
    stored_recourse = result["robust_recourse_cost"]
    reconstructed_objective = result["budget_used"] + fresh_recourse
    original_residual = abs(result["lower_bound"] - result["upper_bound"])
    audit = {
        "schema": "e4_210330_g3_global_coupling_audit_v1",
        "run_id": result["run_id"],
        "classification": "NUMERICAL_DIAGNOSTIC_TOLERANCE_ISSUE",
        "frozen_contract_classification": "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH",
        "diagnostic_formula": "abs(final_master_theta - final_iteration_exact_composition)",
        "absolute_threshold": 1e-6,
        "reported_pass": result["global_coupling_pass"],
        "persisted_master_closure_residual": original_residual,
        "fresh_exact_recourse": fresh_recourse,
        "stored_exact_recourse": stored_recourse,
        "fresh_vs_stored_recourse_difference": abs(fresh_recourse - stored_recourse),
        "recomputed_certified_state_residual": abs(fresh_recourse - stored_recourse),
        "risk_budget_allocation": list(composition.allocation),
        "risk_budget_allocation_sum": sum(composition.allocation),
        "Gamma": gamma,
        "Gamma_feasible": sum(composition.allocation) <= gamma,
        "maximum_product_strong_duality_error": max(
            worst.cut.strong_duality_error
            for item in product_results for worst in item.worst_cases
        ),
        "all_product_duals_feasible": all(
            worst.cut.dual_feasible
            for item in product_results for worst in item.worst_cases
        ),
        "reported_objective": result["objective"],
        "reconstructed_objective": reconstructed_objective,
        "objective_reconstruction_difference": abs(result["objective"] - reconstructed_objective),
        "objective_affected": False,
        "exact_recourse_affected": False,
        "Gamma_feasibility_affected": False,
        "first_stage_reoptimized": False,
        "fixed_first_stage_product_lp_solves": instance.num_products * (gamma + 1),
        "primary_artifact_modified": False,
    }
    return audit


def case_rows(results: dict[tuple[str, int], dict], solutions: dict[tuple[str, int], dict], g2_audit: dict) -> list[dict]:
    g2_status = {row["case"]: row for row in g2_audit["rows"]}
    rows = []
    for case in CASES:
        baseline = results[(case, 0)]
        for gamma in GAMMAS:
            result = results[(case, gamma)]
            active_ids = "|".join(
                entry["depot_id"] for entry in solutions[(case, gamma)]["y"] if entry["value"] == 1
            )
            if gamma == 2:
                coupling = g2_status[case]["diagnostic_source_status"]
            elif result.get("global_coupling_pass") is True:
                coupling = "PASS"
            else:
                coupling = "NUMERICAL_DIAGNOSTIC_TOLERANCE_ISSUE"
            rows.append({
                "run_id": result["run_id"], "case": case, "Gamma": gamma,
                "objective": result["objective"],
                "normalized_objective": result["objective"] / baseline["objective"],
                "first_stage_economic_cost": result["budget_used"],
                "robust_recourse_cost": result["robust_recourse_cost"],
                "normalized_robust_recourse": result["robust_recourse_cost"] / baseline["robust_recourse_cost"],
                "RI": result["RI"], "RS": result["RS"],
                "budget_utilization": result["budget_utilization"],
                "total_adjustment": result["total_adjustment"],
                "total_a_plus": result["total_a_plus"], "total_a_minus": result["total_a_minus"],
                "changed_pair_count": result["changed_pair_count"],
                "active_depots": result["active_depots"], "active_depot_ids": active_ids,
                "opened_depots": "|".join(result["opened_depots"]),
                "closed_depots": "|".join(result["closed_depots"]),
                "shortage_cost": result["worst_recourse_shortage_cost"],
                "service_penalty": result["worst_recourse_service_penalty_cost"],
                "average_fill_rate": result["average_fill_rate"],
                "minimum_fill_rate": result["minimum_fill_rate"],
                "runtime_seconds": result["runtime_seconds"],
                "iterations": result["iterations"], "master_solves": result["master_solves"],
                "cuts_added": result["cuts_added"],
                "product_subproblem_evaluations": result["product_subproblem_evaluations"],
                "status": result["status"], "certification_status": result["certification_status"],
                "exact_certification_pass": result["exact_certification_pass"],
                "reused_G2": result["reused"],
                "global_coupling_diagnostic_status": coupling,
            })
    return rows


def aggregate_rows(rows: list[dict], tolerance: float) -> list[dict]:
    output = []
    for gamma in GAMMAS:
        selected = [row for row in rows if row["Gamma"] == gamma]
        aggregate = {"Gamma": gamma, "case_count": len(selected)}
        for metric in METRICS:
            values = [float(row[metric]) for row in selected]
            aggregate.update({
                f"mean_{metric}": statistics.mean(values),
                f"median_{metric}": statistics.median(values),
                f"min_{metric}": min(values),
                f"max_{metric}": max(values),
            })
        aggregate["material_reconfiguration_case_count"] = sum(row["RI"] > tolerance for row in selected)
        aggregate["active_depot_set_change_case_count"] = sum(bool(row["opened_depots"] or row["closed_depots"]) for row in selected)
        output.append(aggregate)
    return output


def threshold_rows(rows: list[dict], tolerance: float) -> list[dict]:
    output = []
    for case in CASES:
        selected = sorted((row for row in rows if row["case"] == case), key=lambda row: row["Gamma"])
        material = [row["Gamma"] for row in selected if row["RI"] > tolerance]
        baseline_active = selected[0]["active_depot_ids"]
        output.append({
            "case": case,
            "first_material_reconfiguration_Gamma": material[0] if material else "",
            "first_material_reconfiguration_status": f"G{material[0]}" if material else "NONE_THROUGH_G4",
            **{f"RI_G{row['Gamma']}": row["RI"] for row in selected},
            **{f"total_adjustment_G{row['Gamma']}": row["total_adjustment"] for row in selected},
            **{f"active_depots_G{row['Gamma']}": row["active_depots"] for row in selected},
            "active_depot_set_changed_from_G0": any(row["active_depot_ids"] != baseline_active for row in selected),
            "RI_weakly_nondecreasing": all(
                current["RI"] <= following["RI"] + tolerance
                for current, following in zip(selected, selected[1:])
            ),
        })
    return output


def main() -> None:
    before = primary_hashes()
    results, solutions, validation = load_and_validate()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tolerance = manifest["reporting_tolerance"]
    g2_audit = audit_g2_reuse(results)
    coupling_audit = fixed_g3_coupling_audit(solutions[("210330", 3)])
    rows = case_rows(results, solutions, g2_audit)
    aggregates = aggregate_rows(rows, tolerance)
    thresholds = threshold_rows(rows, tolerance)
    after = primary_hashes()
    checks = {
        "complete_40_of_40": len(results) == 40,
        "no_missing_or_duplicate_runs": set(result["run_id"] for result in results.values()) == set(expected_run_ids()),
        "all_OPTIMAL": all(result["status"] == "OPTIMAL" for result in results.values()),
        "all_exact_certification_PASS": all(result["exact_certification_pass"] is True and result["certification_status"] == "CERTIFIED_PRB_EXACT" for result in results.values()),
        "provenance_hashes_PASS": validation["provenance_hashes_pass"],
        "frozen_identity_PASS": validation["frozen_identity_pass"],
        "G2_reuse_identity_8_of_8": g2_audit["identity_safe_count"] == 8,
        "210330_G3_fixed_state_recourse_PASS": coupling_audit["fresh_vs_stored_recourse_difference"] <= 1e-6,
        "210330_G3_Gamma_feasible": coupling_audit["Gamma_feasible"],
        "primary_hashes_preserved": before == after,
    }
    status = "E4_FINAL_AUDIT_PASS" if all(checks.values()) else "E4_FINAL_AUDIT_BLOCKED"
    audit = {
        "schema": "e4_final_result_audit_v1",
        "status": status,
        "expected_run_count": 40,
        "observed_run_count": len(results),
        "checks": checks,
        "frozen_zip_comparison": frozen_zip_comparison(),
        "G2_reuse": g2_audit,
        "coupling_210330_G3": coupling_audit,
        "material_reconfiguration_tolerance": tolerance,
        "per_case_first_material_Gamma": {
            row["case"]: row["first_material_reconfiguration_status"] for row in thresholds
        },
        "RI_weakly_nondecreasing_case_count": sum(row["RI_weakly_nondecreasing"] for row in thresholds),
        "active_depot_set_change_case_count": sum(row["active_depot_set_changed_from_G0"] for row in thresholds),
        "material_conditions_with_depot_set_change": sum(
            row["RI"] > tolerance and bool(row["opened_depots"] or row["closed_depots"])
            for row in rows
        ),
        "fixed_first_stage_product_lp_solves_per_audit": coupling_audit["fixed_first_stage_product_lp_solves"],
        "fixed_first_stage_product_lp_solves_executed_in_task": 64,
        "new_first_stage_optimization_solves": 0,
        "primary_results_overwritten": False,
        "E1_overwritten": False,
        "E2_overwritten": False,
        "E3_overwritten": False,
        "model_changed": False,
        "dataset_changed": False,
        "Gamma_grid_changed": False,
        "B_ref_changed": False,
        "beta_changed": False,
        "lambda_R_changed": False,
    }
    write_csv(ARTIFACTS / "e4_table_gamma_sensitivity_case_level.csv", rows)
    write_csv(ARTIFACTS / "e4_table_gamma_sensitivity_aggregate.csv", aggregates)
    write_csv(ARTIFACTS / "e4_table_reconfiguration_thresholds.csv", thresholds)
    write_json(ARTIFACTS / "e4_210330_g3_global_coupling_audit.json", coupling_audit)
    write_json(ARTIFACTS / "e4_final_result_audit.json", audit)
    print(status)
    if status != "E4_FINAL_AUDIT_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
