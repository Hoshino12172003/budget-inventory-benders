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

from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.reconfiguration_model import reconfiguration_index
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service_detailed
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


MANIFEST = ROOT / "experiments/configs/formal/e4_gamma_sensitivity_authorization.json"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
RESULT_ROOT = ROOT / "experiments/results/e4_gamma_sensitivity_v1"
E2_ROOT = ROOT / "experiments/results/e2_existing_nominal_robust_v1"
E2_MANIFEST = ROOT / "experiments/configs/formal/e2_existing_nominal_robust_authorization.json"
E3_ROOT = ROOT / "experiments/results/e3_budget_sensitivity_v1"
E3_MANIFEST = ROOT / "experiments/configs/formal/e3_budget_sensitivity_authorization.json"
E1_ROOT = ROOT / "experiments/results/e1_empirical_8case_v1"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
GAMMA_GRID = (0, 1, 2, 3, 4)
BETA = 1.0
LAMBDA_R = 0.05
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_model_identity(revision: str | None = None) -> str:
    hashes = {}
    for name in MODEL_FILES:
        if revision is None:
            content = (ROOT / name).read_bytes()
        else:
            content = subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=ROOT)
        hashes[name] = hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()
    return canonical_hash(hashes)


def parse_gamma(value: str | int) -> int:
    try:
        gamma = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"gamma must be one of {list(GAMMA_GRID)}") from error
    if str(value) != str(gamma) or gamma not in GAMMA_GRID:
        raise ValueError(f"gamma must be one of {list(GAMMA_GRID)}")
    return gamma


def make_run_id(case: str, gamma: int) -> str:
    return f"E4-{case}-G{gamma}"


def expected_run_ids() -> list[str]:
    return [make_run_id(case, gamma) for case in CASES for gamma in GAMMA_GRID]


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_identities() -> dict[str, dict[str, str]]:
    with IDENTITY_TABLE.open(encoding="utf-8", newline="") as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


def validate_manifest(manifest: dict) -> None:
    checks = {
        "dataset": manifest["dataset_id"] == "RENAULT_EMPIRICAL_8CASE_V1",
        "cases": manifest["cases"] == list(CASES),
        "gamma_grid": manifest["Gamma_grid"] == list(GAMMA_GRID),
        "run_ids": manifest["authorized_run_ids"] == expected_run_ids(),
        "beta": manifest["beta"] == BETA,
        "lambda_R": manifest["lambda_R"] == LAMBDA_R,
        "solver_profile": manifest["solver_profile"] == FORMAL_SOLVER_PROFILE_ID,
        "result_root": manifest["result_root"] == "experiments/results/e4_gamma_sensitivity_v1",
        "model_files": manifest["model_files"] == list(MODEL_FILES),
        "identity_table": sha256(IDENTITY_TABLE) == manifest["identity_table_sha256"],
        "coverage": all(set(manifest[key]) == set(CASES) for key in ("B_ref_by_case", "instance_hashes", "x0_hashes", "calibration_hashes")),
        "authorization_history": manifest["authorization_transition"] in ([False], [False, True]),
        "authorization_state": manifest["authorization_transition"][-1] is manifest["formal_run_authorized"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E4_MANIFEST_IDENTITY: {','.join(failed)}")


def validate_case_identity(case: str, manifest: dict, identity: dict[str, str]) -> None:
    paths = {
        "instance_hash": ROOT / f"data/formal_instances_v2/{case}.json",
        "x0_hash": ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json",
        "calibration_hash": ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json",
    }
    checks = {
        key: sha256(path) == identity[key] == manifest[f"{key.replace('_hash', '')}_hashes" if key != "calibration_hash" else "calibration_hashes"][case]
        for key, path in paths.items()
    }
    calibration = json.loads(paths["calibration_hash"].read_text(encoding="utf-8"))
    checks["B_ref"] = calibration["B_ref"] == manifest["B_ref_by_case"][case]
    checks["mapping"] = identity["mapping_hash"] == manifest["mapping_sha256"]
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E4_CASE_IDENTITY: {case}: {','.join(failed)}")


def validate_g2_reuse(case: str, manifest: dict, identity: dict[str, str]) -> dict:
    source_dir = E3_ROOT / f"E3-{case}-B100"
    result_path = source_dir / "result.json"
    solution_path = source_dir / "first_stage_solution.json"
    provenance_path = source_dir / "provenance.json"
    source = json.loads(result_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    e3_manifest = json.loads(E3_MANIFEST.read_text(encoding="utf-8"))
    checks = {
        "source_files": solution_path.is_file() and provenance_path.is_file(),
        "source_hashes": provenance["result_sha256"] == sha256(result_path) and provenance["first_stage_solution_sha256"] == sha256(solution_path),
        "dataset": source["dataset_id"] == e3_manifest["dataset_id"] == manifest["dataset_id"],
        "case": source["case"] == case,
        "condition": source["beta"] == BETA and source["Gamma"] == 2 and source["lambda_R"] == LAMBDA_R,
        "budget": source["B"] == source["B_ref"] == manifest["B_ref_by_case"][case],
        "instance": source["instance_hash"] == identity["instance_hash"] == manifest["instance_hashes"][case],
        "x0": source["x0_hash"] == identity["x0_hash"] == manifest["x0_hashes"][case],
        "calibration": source["calibration_hash"] == identity["calibration_hash"] == manifest["calibration_hashes"][case],
        "mapping": source["mapping_hash"] == manifest["mapping_sha256"],
        "solver_profile": source["solver_profile"] == manifest["solver_profile"],
        "model": source["model_identity_sha256"] == manifest["model_identity_sha256"] == source_model_identity(),
        "prb": manifest["prb_identity_sha256"] == sha256(PRB_FILE),
        "tolerance": e3_manifest["budget_feasibility_tolerance"] == manifest["budget_feasibility_tolerance"],
        "objective": abs(source["objective"] - source["budget_used"] - source["robust_recourse_cost"]) <= manifest["objective_certification_tolerance"],
        "certification": source["status"] == "OPTIMAL" and source["certification_status"] == "CERTIFIED_PRB_EXACT",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E4_G2_REUSE_IDENTITY: {case}: {','.join(failed)}")
    return {"result": source, "solution_path": solution_path, "checks": checks}


def classify_g0_reuse(case: str, manifest: dict, identity: dict[str, str]) -> dict:
    result_path = E2_ROOT / f"E2-{case}-NOMINAL/result.json"
    source = json.loads(result_path.read_text(encoding="utf-8"))
    e2_manifest = json.loads(E2_MANIFEST.read_text(encoding="utf-8"))
    source_dir = result_path.parent
    checks = {
        "dataset": e2_manifest["dataset_id"] == manifest["dataset_id"],
        "case_policy": source["case"] == case and source["policy"] == "NOMINAL",
        "Gamma_plan": source["Gamma_plan"] == 0,
        "lambda_R": e2_manifest["lambda_R"] == manifest["lambda_R"],
        "budget": abs(source["budget_used"] - manifest["B_ref_by_case"][case]) <= manifest["budget_feasibility_tolerance"],
        "instance": source["instance_hash"] == identity["instance_hash"],
        "x0": source["x0_hash"] == identity["x0_hash"],
        "mapping": source["mapping_hash"] == manifest["mapping_sha256"],
        "solver_profile": source["solver_profile"] == manifest["solver_profile"],
        "status": source["status"] == "OPTIMAL",
        "full_first_stage_artifact": (source_dir / "first_stage_solution.json").is_file(),
        "run_provenance": (source_dir / "provenance.json").is_file(),
        "model_identity_recorded": "model_identity_sha256" in source,
        "calibration_identity_recorded": "calibration_hash" in source,
        "Gamma0_objective_recorded": source.get("Gamma_eval") == 0,
        "exact_certification_recorded": source.get("certification_status") == "CERTIFIED_PRB_EXACT",
    }
    eligible = all(checks.values())
    return {
        "classification": "IDENTITY_SAFE_E2_NOMINAL_REUSE" if eligible else "E4_G0_REUSE_NOT_IDENTITY_SAFE",
        "eligible": eligible,
        "checks": checks,
        "failed_identity_evidence": [name for name, passed in checks.items() if not passed],
    }


def validate_gate(case: str, gamma: int, output_root: Path = RESULT_ROOT) -> tuple[dict, dict[str, str]]:
    manifest = load_manifest()
    validate_manifest(manifest)
    if case not in CASES:
        raise ValueError(f"unknown E4 case: {case}")
    run_id = make_run_id(case, gamma)
    if manifest.get("formal_run_authorized") is not True or run_id not in manifest["authorized_run_ids"]:
        raise PermissionError("E4_FORMAL_RUN_NOT_AUTHORIZED")
    if sha256(Path(__file__)) != manifest["runner_sha256"]:
        raise RuntimeError("E4 runner hash mismatch")
    if source_model_identity() != manifest["model_identity_sha256"] or sha256(PRB_FILE) != manifest["prb_identity_sha256"]:
        raise RuntimeError("E4 implementation identity mismatch")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E4 requires a clean committed worktree")
    if (output_root / run_id).exists():
        raise FileExistsError(f"refusing to overwrite {run_id}")
    identity = load_identities()[case]
    validate_case_identity(case, manifest, identity)
    return manifest, identity


def cost_components(instance, solution) -> tuple[float, float, float]:
    fixed = sum(instance.fixed_depot_cost[i] * solution.y[i] for i in range(instance.num_depots))
    inventory = sum(instance.inventory_cost[i][j] * solution.x[i][j] for i in range(instance.num_depots) for j in range(instance.num_products))
    reconfiguration = LAMBDA_R * sum(
        instance.inventory_cost[i][j] * (solution.a_plus[i][j] + solution.a_minus[i][j])
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    return fixed, inventory, reconfiguration


def reused_g2_result(case: str, manifest: dict, identity: dict[str, str]) -> tuple[dict, Path]:
    reuse = validate_g2_reuse(case, manifest, identity)
    source = reuse["result"]
    e1 = json.loads((E1_ROOT / f"E1-{case}-PRB/result.json").read_text(encoding="utf-8"))
    result = dict(source)
    result.update({
        "run_id": make_run_id(case, 2), "experiment_id": manifest["experiment_id"],
        "Gamma": 2, "beta": BETA, "reused": True, "reuse_source_run": source["run_id"],
        "prb_identity_sha256": manifest["prb_identity_sha256"],
        "transport_cost": source["robust_recourse_cost"] - source["worst_recourse_shortage_cost"] - source["worst_recourse_service_penalty_cost"],
        "exact_certification_pass": True, "lower_bound": e1["lower_bound"],
        "upper_bound": e1["upper_bound"], "relative_gap": e1["relative_gap"],
    })
    return result, reuse["solution_path"]


def solved_result(case: str, gamma: int, manifest: dict, identity: dict[str, str]):
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    x0_artifact = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8"))
    x0, y0 = x0_artifact["x0"], x0_artifact["y0"]
    budget = manifest["B_ref_by_case"][case]
    solved = solve_prb_benders(instance, x0, budget, gamma, LAMBDA_R)
    if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
        raise RuntimeError("E4 PRB solve is not exactly certified")
    service = evaluate_robust_service_detailed(instance, solved.solution.x, gamma)
    fixed, inventory, reconfiguration = cost_components(instance, solved.solution)
    budget_used = fixed + inventory + reconfiguration
    if budget_used - budget > manifest["budget_feasibility_tolerance"]:
        raise RuntimeError("E4 financial budget violation")
    direct_ri, represented_ri = reconfiguration_index(
        solved.solution.x, x0, solved.solution.a_plus, solved.solution.a_minus
    )
    if abs(direct_ri - represented_ri) > manifest["reporting_tolerance"]:
        raise RuntimeError("E4 reconfiguration index mismatch")
    opened = [instance.depot_ids[i] for i in range(instance.num_depots) if solved.solution.y[i] and not y0[i]]
    closed = [instance.depot_ids[i] for i in range(instance.num_depots) if y0[i] and not solved.solution.y[i]]
    recourse = service.robust_recourse_cost
    result = {
        "run_id": make_run_id(case, gamma), "experiment_id": manifest["experiment_id"],
        "case": case, "Gamma": gamma, "beta": BETA, "B": budget, "B_ref": budget,
        "lambda_R": LAMBDA_R, "dataset_id": manifest["dataset_id"],
        "instance_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"],
        "calibration_hash": identity["calibration_hash"], "mapping_hash": manifest["mapping_sha256"],
        "model_identity_sha256": manifest["model_identity_sha256"], "prb_identity_sha256": manifest["prb_identity_sha256"],
        "solver_profile": manifest["solver_profile"], "reused": False,
        "objective": budget_used + recourse, "fixed_cost": fixed, "inventory_cost": inventory,
        "reconfiguration_cost": reconfiguration, "robust_recourse_cost": recourse,
        "budget_used": budget_used, "budget_utilization": budget_used / budget,
        "budget_slack": budget - budget_used,
        "total_a_plus": sum(map(sum, solved.solution.a_plus)),
        "total_a_minus": sum(map(sum, solved.solution.a_minus)),
        "total_adjustment": sum(map(sum, solved.solution.a_plus)) + sum(map(sum, solved.solution.a_minus)),
        "changed_pair_count": sum(abs(solved.solution.x[i][j] - x0[i][j]) > manifest["reporting_tolerance"] for i in range(instance.num_depots) for j in range(instance.num_products)),
        "RI": direct_ri, "RS": reconfiguration / budget, "active_depots": sum(solved.solution.y),
        "opened_depots": opened, "closed_depots": closed,
        "worst_recourse_shortage_cost": service.worst_recourse_scenario.shortage_cost,
        "transport_cost": service.worst_recourse_scenario.transportation_cost,
        "worst_recourse_service_penalty_cost": service.worst_recourse_scenario.service_penalty_cost,
        "worst_recourse_total_shortage": service.worst_recourse_scenario.total_shortage,
        "minimum_fill_rate": service.worst_service_scenario.minimum_fill_rate,
        "average_fill_rate": service.worst_service_scenario.average_fill_rate,
        "worst_region": service.worst_service_scenario.worst_region_id,
        "runtime_seconds": solved.total_runtime, "iterations": len(solved.iterations),
        "master_solves": solved.master_solve_count,
        "product_subproblem_evaluations": solved.product_subproblem_evaluations,
        "cuts_added": solved.unique_product_cuts, "lower_bound": solved.final_lower_bound,
        "upper_bound": solved.final_upper_bound, "relative_gap": solved.final_relative_gap,
        "certification_status": "CERTIFIED_PRB_EXACT", "exact_certification_pass": True,
        "global_coupling_pass": solved.global_risk_budget_coupling_pass, "status": "OPTIMAL",
    }
    artifact = build_first_stage_solution_artifact(
        instance, x0, solved.solution, case_id=case, mode="E4_PRB",
        identity={
            "config_hash": sha256(MANIFEST), "data_hash": identity["instance_hash"],
            "x0_hash": identity["x0_hash"],
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        },
        solver_profile=manifest["solver_profile"],
    )
    return result, artifact


def write_run(result: dict, first_stage, output_root: Path, manifest: dict) -> None:
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
            "result_sha256": sha256(result_path), "first_stage_solution_sha256": sha256(solution_path),
            "reused": result["reused"],
            "reuse_source_run": result.get("reuse_source_run"),
        }
        (temporary / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if target.exists():
            raise FileExistsError(f"refusing to overwrite {result['run_id']}")
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--gamma", required=True)
    parser.add_argument("--output-root", type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    gamma = parse_gamma(args.gamma)
    manifest, identity = validate_gate(args.case, gamma, args.output_root)
    if gamma == 2:
        result, first_stage = reused_g2_result(args.case, manifest, identity)
    else:
        result, first_stage = solved_result(args.case, gamma, manifest, identity)
    write_run(result, first_stage, args.output_root, manifest)


if __name__ == "__main__":
    main()
