from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
from typing import Any

from robust_inventory_reconfiguration.exact_benchmark import solve_exact_benchmark
from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact, write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.renault_empirical import CASES, DATASET_ID, MAPPING_SHA256, sha256_file
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "experiments/configs/formal/e1_empirical_8case_authorization.json"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
METHODS = ("direct", "prb")


def _identity(case_id: str) -> dict[str, str]:
    with IDENTITY_TABLE.open(encoding="utf-8", newline="") as stream:
        rows = {row["case"]: row for row in csv.DictReader(stream)}
    if case_id not in rows:
        raise RuntimeError(f"paper-final identity is missing for {case_id}")
    return rows[case_id]


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def validate_execution_gate(
    case_id: str, method: str, output_root: Path, resume: bool = False
) -> tuple[dict[str, Any], dict[str, str]]:
    if case_id not in CASES or method not in METHODS:
        raise RuntimeError("run is outside the frozen E1 empirical contract")
    manifest = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != DATASET_ID or manifest.get("formal_run_authorized") is not True:
        raise PermissionError("E1_EMPIRICAL_8CASE_FORMAL_RUN_NOT_AUTHORIZED")
    run_id = f"E1-{case_id}-{method.upper()}"
    if run_id not in manifest.get("authorized_run_ids", []):
        raise PermissionError(f"run is not authorized: {run_id}")
    if manifest.get("e2_e7_authorization") is not False:
        raise RuntimeError("E2-E7 authorization changed")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E1 execution requires a clean committed worktree")
    target = output_root / run_id
    if resume:
        raise RuntimeError("resume is not supported by the immutable paper-final runner")
    if target.exists():
        raise FileExistsError(f"refusing to overwrite an existing run: {target}")
    identity = _identity(case_id)
    if identity["mapping_hash"] != MAPPING_SHA256:
        raise RuntimeError("mapping hash mismatch")
    base = ROOT / "artifacts" / DATASET_ID.lower()
    paths = {
        "instance_hash": ROOT / "data/formal_instances_v2" / f"{case_id}.json",
        "x0_hash": base / "x0" / f"{case_id}.json",
        "calibration_hash": base / "calibration" / f"{case_id}.json",
    }
    for key, path in paths.items():
        if sha256_file(path) != identity[key]:
            raise RuntimeError(f"{key} mismatch")
    return manifest, identity


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one authorized paper-final empirical E1 solve.")
    parser.add_argument("--case", required=True, choices=CASES)
    parser.add_argument("--method", required=True, choices=METHODS)
    parser.add_argument("--output-root", type=Path, default=ROOT / "experiments/results/e1_empirical_8case_v1")
    args = parser.parse_args()
    manifest, identity = validate_execution_gate(args.case, args.method, args.output_root)
    run_id = f"E1-{args.case}-{args.method.upper()}"
    target = args.output_root / run_id
    instance = load_instance(ROOT / "data/formal_instances_v2" / f"{args.case}.json")
    if instance.initial_inventory is None:
        raise RuntimeError("paper-final instance has no nominal incumbent x0")
    x0 = instance.initial_inventory
    calibration_path = ROOT / "artifacts" / DATASET_ID.lower() / "calibration" / f"{args.case}.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    budget = float(calibration["B_ref"])
    if args.method == "direct":
        solved = solve_exact_benchmark(instance, x0, budget, 2, 0.05)
        if solved.status != "OPTIMAL" or solved.solution is None:
            raise RuntimeError(f"Direct exact certification failed: {solved.status}")
        solution = solved.solution
        diagnostics = {
            "method": "direct_exact", "certification": "CERTIFIED_EXACT",
            "runtime_seconds": solved.runtime, "best_bound": solved.best_bound,
            "mip_gap": solved.mip_gap, "node_count": solved.node_count,
            "variable_count": solved.variable_count, "constraint_count": solved.constraint_count,
        }
    else:
        solved = solve_prb_benders(instance, x0, budget, 2, 0.05)
        if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
            raise RuntimeError("PRB exact final certification failed")
        solution = solved.solution
        diagnostics = {
            "method": "prb_benders", "certification": "CERTIFIED_PRB_EXACT",
            "runtime_seconds": solved.total_runtime, "iterations": len(solved.iterations),
            "lower_bound": solved.final_lower_bound, "upper_bound": solved.final_upper_bound,
            "relative_gap": solved.final_relative_gap, "unique_product_cuts": solved.unique_product_cuts,
            "global_coupling_pass": solved.global_risk_budget_coupling_pass,
        }
    service = evaluate_robust_service(instance, solution.x, 2)
    artifact_identity = {
        "config_hash": identity["calibration_hash"], "data_hash": identity["instance_hash"],
        "x0_hash": identity["x0_hash"], "git_commit": _git_commit(),
    }
    solution_path = target / "first_stage_solution.json"
    write_first_stage_solution_artifact(
        solution_path,
        build_first_stage_solution_artifact(
            instance, x0, solution, case_id=args.case, mode=diagnostics["method"],
            identity=artifact_identity, solver_profile=FORMAL_SOLVER_PROFILE_ID,
        ),
    )
    result = {
        "run_id": run_id, "dataset_id": DATASET_ID, "case": args.case,
        "Gamma": 2, "beta": 1.0, "B": budget, "lambda_R": 0.05,
        "objective": solution.objective, "first_stage_expenditure": solution.first_stage_expenditure,
        "robust_recourse_cost": solution.robust_recourse_cost,
        "FR_min_robust": service.minimum_fill_rate, "average_fill_rate": service.average_fill_rate,
        "worst_region": service.worst_region_id, "instance_hash": identity["instance_hash"],
        "x0_hash": identity["x0_hash"], "calibration_hash": identity["calibration_hash"],
        "mapping_hash": MAPPING_SHA256, "git_commit": _git_commit(),
        "solver_profile": FORMAL_SOLVER_PROFILE_ID, **diagnostics,
    }
    _write_json(target / "result.json", result)
    _write_json(target / "provenance.json", {
        "authorization_sha256": sha256_file(AUTHORIZATION),
        "identity_table_sha256": sha256_file(IDENTITY_TABLE),
        "first_stage_solution_sha256": sha256_file(solution_path),
        "formal_run_authorized": manifest["formal_run_authorized"],
    })


if __name__ == "__main__":
    main()
