from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.e4_reporting import evaluate_e4_service
from robust_inventory_reconfiguration.e5_reporting import (
    canonical_adjustment,
    maximum_adjustment_difference,
)
from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    load_first_stage_solution_artifact,
    matrix_from_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.reconfiguration_model import ReconfigurationSolution
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


MANIFEST = ROOT / "experiments/configs/formal/e5_reconfiguration_friction_authorization.json"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
RESULT_ROOT = ROOT / "experiments/results/e5_reconfiguration_friction_v1"
REUSE_ROOT = ROOT / "experiments/results/e4_gamma_sensitivity_v1"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
LAMBDA_BY_TOKEN = {
    "L0000": 0.0,
    "L0025": 0.0025,
    "L0100": 0.01,
    "L0500": 0.05,
    "L2000": 0.20,
}
BETA = 1.0
GAMMA = 2
REPORTING_TOLERANCE = 1e-6
MODEL_FILES = (
    "src/robust_inventory_reconfiguration/instance.py",
    "src/robust_inventory_reconfiguration/reconfiguration_model.py",
    "src/robust_inventory_reconfiguration/recourse.py",
    "src/robust_inventory_reconfiguration/scenarios.py",
    "src/robust_inventory_reconfiguration/product_risk_subproblem.py",
    "src/robust_inventory_reconfiguration/risk_budget_composition.py",
    "src/robust_inventory_reconfiguration/product_risk_budget_benders.py",
    "src/robust_inventory_reconfiguration/robust_service.py",
    "src/robust_inventory_reconfiguration/solver_profile.py",
)
PRB_FILE = ROOT / "src/robust_inventory_reconfiguration/product_risk_budget_benders.py"
REPORTING_FILE = ROOT / "src/robust_inventory_reconfiguration/e5_reporting.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_model_identity() -> str:
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in MODEL_FILES
    }
    return canonical_hash(hashes)


def parse_lambda_token(value: str) -> tuple[str, float]:
    token = value.upper()
    if token not in LAMBDA_BY_TOKEN:
        raise ValueError(f"lambda-r must be one of {list(LAMBDA_BY_TOKEN)}")
    return token, LAMBDA_BY_TOKEN[token]


def make_run_id(case: str, token: str) -> str:
    if case not in CASES:
        raise ValueError(f"unknown E5 case: {case}")
    if token not in LAMBDA_BY_TOKEN:
        raise ValueError(f"unknown E5 lambda token: {token}")
    return f"E5-{case}-{token}"


def expected_run_ids() -> list[str]:
    return [make_run_id(case, token) for case in CASES for token in LAMBDA_BY_TOKEN]


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_identities() -> dict[str, dict[str, str]]:
    with IDENTITY_TABLE.open(encoding="utf-8", newline="") as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


def validate_manifest(manifest: dict, *, require_authorized: bool = True) -> None:
    checks = {
        "dataset": manifest["dataset_id"] == "RENAULT_EMPIRICAL_8CASE_V1",
        "cases": manifest["cases"] == list(CASES),
        "lambda_grid": manifest["lambda_levels"] == [
            {"token": token, "value": value} for token, value in LAMBDA_BY_TOKEN.items()
        ],
        "run_ids": manifest["authorized_run_ids"] == expected_run_ids(),
        "beta": manifest["beta"] == BETA,
        "Gamma": manifest["Gamma"] == GAMMA,
        "solver_profile": manifest["solver_profile"] == FORMAL_SOLVER_PROFILE_ID,
        "result_root": manifest["result_root"] == "experiments/results/e5_reconfiguration_friction_v1",
        "model_files": manifest["model_files"] == list(MODEL_FILES),
        "identity_table": sha256(IDENTITY_TABLE) == manifest["identity_table_sha256"],
        "coverage": all(set(manifest[key]) == set(CASES) for key in ("B_ref_by_case", "instance_hashes", "x0_hashes", "calibration_hashes")),
        "authorization_history": manifest["authorization_transition"] in ([False], [False, True]),
        "authorization_state": manifest["authorization_transition"][-1] is manifest["formal_run_authorized"],
    }
    if require_authorized:
        checks["authorized"] = manifest["formal_run_authorized"] is True
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E5_MANIFEST_IDENTITY: {','.join(failed)}")


def validate_case_identity(case: str, manifest: dict, identity: dict[str, str]) -> None:
    paths = {
        "instance_hash": ROOT / f"data/formal_instances_v2/{case}.json",
        "x0_hash": ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json",
        "calibration_hash": ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json",
    }
    checks = {
        key: sha256(path) == identity[key] == manifest[
            f"{key.replace('_hash', '')}_hashes" if key != "calibration_hash" else "calibration_hashes"
        ][case]
        for key, path in paths.items()
    }
    calibration = json.loads(paths["calibration_hash"].read_text(encoding="utf-8"))
    checks["B_ref"] = calibration["B_ref"] == manifest["B_ref_by_case"][case]
    checks["mapping"] = identity["mapping_hash"] == manifest["mapping_sha256"]
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E5_CASE_IDENTITY: {case}: {','.join(failed)}")


def validate_l0500_reuse(case: str, manifest: dict, identity: dict[str, str]) -> dict:
    source_dir = REUSE_ROOT / f"E4-{case}-G2"
    result_path = source_dir / "result.json"
    solution_path = source_dir / "first_stage_solution.json"
    provenance_path = source_dir / "provenance.json"
    source = json.loads(result_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    checks = {
        "source_files": solution_path.is_file() and provenance_path.is_file(),
        "source_hashes": provenance["result_sha256"] == sha256(result_path) and provenance["first_stage_solution_sha256"] == sha256(solution_path),
        "dataset": source["dataset_id"] == manifest["dataset_id"],
        "case": source["case"] == case,
        "condition": source["beta"] == BETA and source["Gamma"] == GAMMA and source["lambda_R"] == LAMBDA_BY_TOKEN["L0500"],
        "budget": source["B"] == source["B_ref"] == manifest["B_ref_by_case"][case],
        "instance": source["instance_hash"] == identity["instance_hash"] == manifest["instance_hashes"][case],
        "x0": source["x0_hash"] == identity["x0_hash"] == manifest["x0_hashes"][case],
        "calibration": source["calibration_hash"] == identity["calibration_hash"] == manifest["calibration_hashes"][case],
        "mapping": source["mapping_hash"] == manifest["mapping_sha256"],
        "solver_profile": source["solver_profile"] == manifest["solver_profile"],
        "model": source["model_identity_sha256"] == manifest["model_identity_sha256"] == source_model_identity(),
        "prb": source["prb_identity_sha256"] == manifest["prb_identity_sha256"] == sha256(PRB_FILE),
        "tolerance": manifest["tolerance_contract"] == {"budget_feasibility": 1e-6, "objective_certification": 1e-4, "reporting": 1e-6},
        "objective": abs(source["objective"] - source["budget_used"] - source["robust_recourse_cost"]) <= manifest["tolerance_contract"]["objective_certification"],
        "certification": source["status"] == "OPTIMAL" and source["certification_status"] == "CERTIFIED_PRB_EXACT" and source["exact_certification_pass"] is True,
        "objective_definition": manifest["objective_definition"] == "first-stage economic expenditure plus exact robust recourse",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E5_L0500_REUSE: {case}: {','.join(failed)}")
    return {"result": source, "solution_path": solution_path, "checks": checks}


def incumbent_feasibility(case: str, manifest: dict) -> dict:
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    baseline = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8"))
    x0, y0 = baseline["x0"], baseline["y0"]
    capacity_excess = max(
        sum(instance.product_volume[j] * x0[i][j] for j in range(instance.num_products)) - instance.capacity[i] * y0[i]
        for i in range(instance.num_depots)
    )
    ub_excess = max(
        x0[i][j] - instance.inventory_upper_bound[i][j] * y0[i]
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    base_spending = sum(instance.fixed_depot_cost[i] * y0[i] for i in range(instance.num_depots)) + sum(
        instance.inventory_cost[i][j] * x0[i][j]
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    budget_excess = base_spending - manifest["B_ref_by_case"][case]
    return {
        "case": case,
        "capacity_excess": capacity_excess,
        "UB_excess": ub_excess,
        "base_spending": base_spending,
        "B_ref": manifest["B_ref_by_case"][case],
        "budget_excess": budget_excess,
        "feasible": capacity_excess <= 1e-6 and ub_excess <= 1e-6 and budget_excess <= 1e-6,
        "backstop": "incumbent stay-put solution",
    }


def ensure_output_absent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path.name}")


def validate_gate(case: str, token: str, output_root: Path = RESULT_ROOT) -> tuple[dict, dict[str, str]]:
    manifest = load_manifest()
    validate_manifest(manifest)
    run_id = make_run_id(case, token)
    if run_id not in manifest["authorized_run_ids"]:
        raise PermissionError("E5_FORMAL_RUN_NOT_AUTHORIZED")
    if sha256(Path(__file__)) != manifest["runner_sha256"]:
        raise RuntimeError("E5 runner hash mismatch")
    if sha256(REPORTING_FILE) != manifest["reporting_contract_sha256"]:
        raise RuntimeError("E5 reporting identity mismatch")
    if source_model_identity() != manifest["model_identity_sha256"] or sha256(PRB_FILE) != manifest["prb_identity_sha256"]:
        raise RuntimeError("E5 implementation identity mismatch")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E5 requires a clean committed worktree")
    ensure_output_absent(output_root / run_id)
    identity = load_identities()[case]
    validate_case_identity(case, manifest, identity)
    return manifest, identity


def cost_components(instance, y, x, adjustment, lambda_r: float) -> tuple[float, float, float]:
    fixed = sum(instance.fixed_depot_cost[i] * y[i] for i in range(instance.num_depots))
    inventory = sum(instance.inventory_cost[i][j] * x[i][j] for i in range(instance.num_depots) for j in range(instance.num_products))
    reconfiguration = lambda_r * sum(
        instance.inventory_cost[i][j] * (adjustment.a_plus[i][j] + adjustment.a_minus[i][j])
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    return fixed, inventory, reconfiguration


def canonical_solution(instance, x0, solution, lambda_r: float) -> tuple[ReconfigurationSolution, object, str]:
    adjustment = canonical_adjustment(solution.x, x0, material_tolerance=REPORTING_TOLERANCE)
    if lambda_r > 0:
        difference = maximum_adjustment_difference(adjustment, solution.a_plus, solution.a_minus)
        if difference > REPORTING_TOLERANCE:
            raise RuntimeError("positive-friction adjustment variables are not canonical")
        status = "CANONICAL_X_BASED_MATCHES_POSITIVE_FRICTION_SOLUTION"
    else:
        status = "CANONICAL_X_BASED_ZERO_FRICTION_RECOVERY"
    canonical = ReconfigurationSolution(
        objective=solution.objective,
        first_stage_expenditure=solution.first_stage_expenditure,
        robust_recourse_cost=solution.robust_recourse_cost,
        y=solution.y,
        x=solution.x,
        a_plus=adjustment.a_plus,
        a_minus=adjustment.a_minus,
        reconfiguration_cost=solution.reconfiguration_cost,
    )
    return canonical, adjustment, status


def reuse_result(case: str, manifest: dict, identity: dict[str, str]) -> tuple[dict, Path]:
    reuse = validate_l0500_reuse(case, manifest, identity)
    source = reuse["result"]
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    artifact = load_first_stage_solution_artifact(reuse["solution_path"], instance)
    x = matrix_from_artifact(artifact, instance)
    x0 = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8"))["x0"]
    adjustment = canonical_adjustment(x, x0, material_tolerance=REPORTING_TOLERANCE)
    result = dict(source)
    result.update({
        "run_id": make_run_id(case, "L0500"),
        "experiment_id": manifest["experiment_id"],
        "lambda_token": "L0500",
        "normalized_objective_vs_L0500": 1.0,
        "canonical_total_adjustment": adjustment.total_adjustment,
        "canonical_RI": adjustment.reconfiguration_index,
        "total_adjustment": adjustment.total_adjustment,
        "RI": adjustment.reconfiguration_index,
        "shortage_cost": source["worst_recourse_shortage_cost"],
        "transportation_cost": source["transport_cost"],
        "service_penalty": source["worst_recourse_service_penalty_cost"],
        "total_shortage": source["worst_recourse_total_shortage"],
        "subproblem_evaluations": source["product_subproblem_evaluations"],
        "cuts": source["cuts_added"],
        "reused": True,
        "reuse_source_run": source["run_id"],
        "reporting_canonicalization_status": "CANONICAL_X_BASED_MATCHES_POSITIVE_FRICTION_SOLUTION",
    })
    return result, reuse["solution_path"]


def solved_result(case: str, token: str, lambda_r: float, manifest: dict, identity: dict[str, str]):
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    baseline = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8"))
    x0, y0 = baseline["x0"], baseline["y0"]
    budget = manifest["B_ref_by_case"][case]
    solved = solve_prb_benders(instance, x0, budget, GAMMA, lambda_r)
    if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
        raise RuntimeError("E5 PRB solve is not exactly certified")
    solution, adjustment, canonical_status = canonical_solution(instance, x0, solved.solution, lambda_r)
    service, reporting_diagnostic = evaluate_e4_service(instance, solution.x, GAMMA)
    if abs(service.robust_recourse_cost - solved.solution.robust_recourse_cost) > manifest["tolerance_contract"]["objective_certification"]:
        raise RuntimeError("E5 reporting recourse differs from exact certification")
    fixed, inventory, reconfiguration = cost_components(instance, solution.y, solution.x, adjustment, lambda_r)
    budget_used = fixed + inventory + reconfiguration
    if abs(budget_used - solution.first_stage_expenditure) > REPORTING_TOLERANCE or budget_used - budget > manifest["tolerance_contract"]["budget_feasibility"]:
        raise RuntimeError("E5 first-stage accounting failed")
    baseline_objective = validate_l0500_reuse(case, manifest, identity)["result"]["objective"]
    opened = [instance.depot_ids[i] for i in range(instance.num_depots) if solution.y[i] and not y0[i]]
    closed = [instance.depot_ids[i] for i in range(instance.num_depots) if y0[i] and not solution.y[i]]
    result = {
        "run_id": make_run_id(case, token), "experiment_id": manifest["experiment_id"],
        "case": case, "lambda_token": token, "lambda_R": lambda_r,
        "beta": BETA, "Gamma": GAMMA, "B": budget, "B_ref": budget,
        "dataset_id": manifest["dataset_id"], "mapping_hash": manifest["mapping_sha256"],
        "instance_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"],
        "calibration_hash": identity["calibration_hash"],
        "model_identity_sha256": manifest["model_identity_sha256"], "prb_identity_sha256": manifest["prb_identity_sha256"],
        "solver_profile": manifest["solver_profile"], "reused": False,
        "objective": budget_used + service.robust_recourse_cost,
        "normalized_objective_vs_L0500": (budget_used + service.robust_recourse_cost) / baseline_objective,
        "fixed_cost": fixed, "inventory_cost": inventory, "reconfiguration_cost": reconfiguration,
        "robust_recourse_cost": service.robust_recourse_cost,
        "budget_used": budget_used, "budget_utilization": budget_used / budget,
        "budget_slack": budget - budget_used,
        "total_a_plus": adjustment.total_a_plus, "total_a_minus": adjustment.total_a_minus,
        "total_adjustment": adjustment.total_adjustment,
        "canonical_total_adjustment": adjustment.total_adjustment,
        "RI": adjustment.reconfiguration_index, "canonical_RI": adjustment.reconfiguration_index,
        "RS": 0.0 if lambda_r == 0 else reconfiguration / budget,
        "active_depots": sum(solution.y), "opened_depots": opened, "closed_depots": closed,
        "changed_pair_count": adjustment.changed_pair_count,
        "shortage_cost": service.worst_recourse_scenario.shortage_cost,
        "transportation_cost": service.worst_recourse_scenario.transportation_cost,
        "service_penalty": service.worst_recourse_scenario.service_penalty_cost,
        "total_shortage": service.worst_recourse_scenario.total_shortage,
        "minimum_fill_rate": service.worst_service_scenario.minimum_fill_rate,
        "average_fill_rate": service.worst_service_scenario.average_fill_rate,
        "runtime_seconds": solved.total_runtime, "iterations": len(solved.iterations),
        "master_solves": solved.master_solve_count,
        "subproblem_evaluations": solved.product_subproblem_evaluations,
        "cuts": solved.unique_product_cuts,
        "lower_bound": solved.final_lower_bound, "upper_bound": solved.final_upper_bound,
        "relative_gap": solved.final_relative_gap,
        "exact_certification_pass": True, "certification_status": "CERTIFIED_PRB_EXACT",
        "global_coupling_pass": solved.global_risk_budget_coupling_pass,
        "reporting_tiebreak_diagnostic": reporting_diagnostic,
        "reporting_canonicalization_status": canonical_status,
        "status": "OPTIMAL",
    }
    artifact = build_first_stage_solution_artifact(
        instance, x0, solution, case_id=case, mode="E5_PRB",
        identity={
            "config_hash": sha256(MANIFEST), "data_hash": identity["instance_hash"],
            "x0_hash": identity["x0_hash"],
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        },
        solver_profile=manifest["solver_profile"],
    )
    return result, artifact


def write_run(result: dict, first_stage, output_root: Path) -> None:
    target = output_root / result["run_id"]
    temporary = output_root / f".{result['run_id']}.{uuid4().hex}.tmp"
    temporary.mkdir(parents=True)
    try:
        result_path = temporary / "result.json"
        solution_path = temporary / "first_stage_solution.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if isinstance(first_stage, Path):
            shutil.copy2(first_stage, solution_path)
        else:
            write_first_stage_solution_artifact(solution_path, first_stage)
        provenance = {
            "run_id": result["run_id"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "runner_sha256": sha256(Path(__file__)), "manifest_sha256": sha256(MANIFEST),
            "reporting_contract_sha256": sha256(REPORTING_FILE),
            "result_sha256": sha256(result_path), "first_stage_solution_sha256": sha256(solution_path),
            "reused": result["reused"], "reuse_source_run": result.get("reuse_source_run"),
        }
        (temporary / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ensure_output_absent(target)
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--lambda-r", required=True, help="one canonical token: L0000, L0025, L0100, L0500, L2000")
    parser.add_argument("--output-root", type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    token, lambda_r = parse_lambda_token(args.lambda_r)
    manifest, identity = validate_gate(args.case, token, args.output_root)
    if token == "L0500":
        result, first_stage = reuse_result(args.case, manifest, identity)
    else:
        result, first_stage = solved_result(args.case, token, lambda_r, manifest, identity)
    write_run(result, first_stage, args.output_root)


if __name__ == "__main__":
    main()
