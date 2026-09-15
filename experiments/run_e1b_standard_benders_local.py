from __future__ import annotations

import argparse
from dataclasses import asdict
import csv
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from time import perf_counter
from typing import Any

from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.renault_empirical import (
    CASES,
    DATASET_ID,
    MAPPING_SHA256,
    sha256_file,
)
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID
from robust_inventory_reconfiguration.standard_benders import solve_standard_benders


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "experiments/configs/formal/e1b_standard_vs_prb_authorization.json"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
DATASET_SUMMARY = ROOT / "artifacts/renault_empirical_8case_v1/dataset_summary.json"
DEFAULT_OUTPUT_ROOT = ROOT / "experiments/results/e1b_standard_vs_prb_v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _hardware_info() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
    }


def _identity(case_id: str) -> dict[str, str]:
    with IDENTITY_TABLE.open(encoding="utf-8", newline="") as stream:
        rows = {row["case"]: row for row in csv.DictReader(stream)}
    if case_id not in rows:
        raise RuntimeError(f"paper-final identity is missing for {case_id}")
    return rows[case_id]


def validate_execution_gate(
    case_id: str, output_root: Path = DEFAULT_OUTPUT_ROOT
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    if case_id not in CASES:
        raise RuntimeError("run is outside the frozen E1b empirical contract")
    manifest = _read_json(AUTHORIZATION)
    if manifest.get("formal_run_authorized") is not True:
        raise PermissionError("E1B_STANDARD_BENDERS_FORMAL_RUN_NOT_AUTHORIZED")
    if manifest.get("dataset_id") != DATASET_ID:
        raise RuntimeError("E1b dataset identity mismatch")
    run_id = f"E1B-{case_id}-STANDARD"
    if run_id not in manifest.get("authorized_standard_run_ids", []):
        raise PermissionError(f"run is not authorized: {run_id}")
    if manifest.get("controlled_scaling_authorized") is not False:
        raise RuntimeError("controlled scaling authorization changed")
    if manifest.get("e2_e7_modification_authorized") is not False:
        raise RuntimeError("E2-E7 protection changed")
    if manifest.get("mapping_sha256") != MAPPING_SHA256:
        raise RuntimeError("authorization mapping hash mismatch")
    if sha256_file(IDENTITY_TABLE) != manifest.get("identity_table_sha256"):
        raise RuntimeError("identity table hash mismatch")
    if _read_json(DATASET_SUMMARY).get("status") != "RENAULT_EMPIRICAL_8CASE_V1_READY":
        raise RuntimeError("paper-final empirical dataset is not ready")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E1b execution requires a clean committed worktree")

    protected = manifest["protected_identity"]
    protected_paths = {
        "standard_implementation_sha256": ROOT / "src/robust_inventory_reconfiguration/standard_benders.py",
        "runner_sha256": Path(__file__).resolve(),
        "result_schema_sha256": ROOT / "experiments/schemas/e1b_standard_result.schema.json",
        "protocol_sha256": ROOT / "docs/e1b_standard_benders_protocol.md",
        "baseline_audit_sha256": ROOT / "docs/e1b_standard_benders_baseline_audit.md",
    }
    for key, path in protected_paths.items():
        if sha256_file(path) != protected.get(key):
            raise RuntimeError(f"E1b protected identity mismatch: {key}")

    target = output_root / run_id
    partial = output_root / f".{run_id}.partial"
    if target.exists() or partial.exists():
        raise FileExistsError(f"refusing to overwrite or resume an existing E1b run: {run_id}")

    identity = _identity(case_id)
    base = ROOT / "artifacts" / DATASET_ID.lower()
    identity_paths = {
        "instance_hash": ROOT / "data/formal_instances_v2" / f"{case_id}.json",
        "x0_hash": base / "x0" / f"{case_id}.json",
        "calibration_hash": base / "calibration" / f"{case_id}.json",
    }
    expected = manifest["case_identities"][case_id]
    for key, path in identity_paths.items():
        actual_hash = sha256_file(path)
        if actual_hash != identity[key] or actual_hash != expected[key]:
            raise RuntimeError(f"{case_id} {key} mismatch")

    prb_reference = manifest["prb_e1a_references"][case_id]
    prb_path = ROOT / prb_reference["result_path"]
    if sha256_file(prb_path) != prb_reference["result_sha256"]:
        raise RuntimeError("immutable E1a PRB result hash mismatch")
    prb = _read_json(prb_path)
    if (
        prb.get("status") != "OPTIMAL"
        or prb.get("exact_certification_status") != "CERTIFIED_PRB_EXACT"
        or prb.get("Gamma") != 2
        or prb.get("beta") != 1.0
        or prb.get("lambda_R") != 0.05
    ):
        raise RuntimeError("referenced E1a PRB result violates the E1b fairness contract")
    current_solver = ".".join(map(str, __import__("gurobipy").gurobi.version()))
    if current_solver != manifest["solver_version"] or current_solver != prb["solver_version"]:
        raise RuntimeError("E1b solver version differs from immutable E1a PRB timing source")
    hardware = _hardware_info()
    for key in ("machine", "processor", "logical_cpu_count"):
        if hardware[key] != prb["hardware"][key]:
            raise RuntimeError(f"E1b hardware differs from E1a PRB timing source: {key}")
    return manifest, identity, prb


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one authorized E1b Standard Benders solve.")
    parser.add_argument("--case", required=True, choices=CASES)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    manifest, identity, prb = validate_execution_gate(args.case, args.output_root)
    run_id = f"E1B-{args.case}-STANDARD"
    target = args.output_root / run_id
    partial = args.output_root / f".{run_id}.partial"
    partial.mkdir(parents=True)

    instance = load_instance(ROOT / "data/formal_instances_v2" / f"{args.case}.json")
    if instance.initial_inventory is None:
        raise RuntimeError("paper-final instance has no nominal incumbent x0")
    calibration = _read_json(
        ROOT / "artifacts" / DATASET_ID.lower() / "calibration" / f"{args.case}.json"
    )
    budget = float(calibration["B_ref"])
    solved = solve_standard_benders(
        instance,
        instance.initial_inventory,
        budget,
        gamma=2,
        lambda_r=0.05,
        relative_gap_tolerance=manifest["tolerances"]["relative_gap"],
        cut_tolerance=manifest["tolerances"]["cut_violation"],
        objective_certification_tolerance=manifest["tolerances"]["objective_absolute_certification"],
        max_iterations=manifest["max_iterations"],
        time_limit=manifest["time_limit_seconds"],
        log_file=partial / "solver.log",
    )
    if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
        raise RuntimeError("E1b Standard Benders exact certification failed")

    post_started = perf_counter()
    artifact_identity = {
        "config_hash": identity["calibration_hash"],
        "data_hash": identity["instance_hash"],
        "x0_hash": identity["x0_hash"],
        "git_commit": _git_commit(),
    }
    solution_path = partial / "first_stage_solution.json"
    write_first_stage_solution_artifact(
        solution_path,
        build_first_stage_solution_artifact(
            instance,
            instance.initial_inventory,
            solved.solution,
            case_id=args.case,
            mode="standard_benders",
            identity=artifact_identity,
            solver_profile=FORMAL_SOLVER_PROFILE_ID,
        ),
    )
    _write_json(partial / "iteration_log.json", [asdict(item) for item in solved.iterations])
    _write_json(partial / "aggregate_cuts.json", [asdict(cut) for cut in solved.cuts])
    post_runtime = perf_counter() - post_started
    objective_difference = abs(solved.solution.objective - float(prb["objective"]))
    tolerance = manifest["tolerances"]["objective_absolute_certification"]
    result = {
        "run_id": run_id,
        "dataset_id": DATASET_ID,
        "case": args.case,
        "method": "standard_benders",
        "status": "OPTIMAL",
        "exact_certification_status": "CERTIFIED_STANDARD_BENDERS_EXACT",
        "Gamma": 2,
        "beta": 1.0,
        "B": budget,
        "lambda_R": 0.05,
        "objective": solved.solution.objective,
        "first_stage_expenditure": solved.solution.first_stage_expenditure,
        "robust_recourse_cost": solved.solution.robust_recourse_cost,
        "reconfiguration_cost": solved.solution.reconfiguration_cost,
        "core_runtime_seconds": solved.total_runtime,
        "post_evaluation_runtime_seconds": post_runtime,
        "master_runtime_seconds": solved.master_runtime,
        "oracle_runtime_seconds": solved.oracle_runtime,
        "cut_construction_runtime_seconds": solved.cut_construction_runtime,
        "certification_runtime_seconds": solved.certification_runtime,
        "iteration_count": len(solved.iterations),
        "aggregate_cut_count": solved.aggregate_cut_count,
        "cuts_per_iteration": solved.aggregate_cut_count / len(solved.iterations),
        "product_subproblem_evaluations": solved.product_subproblem_evaluations,
        "lower_bound": solved.final_lower_bound,
        "upper_bound": solved.final_upper_bound,
        "absolute_gap": solved.final_absolute_gap,
        "relative_gap": solved.final_relative_gap,
        "cut_validity_pass": solved.cut_validity_pass,
        "prb_e1a_result_path": manifest["prb_e1a_references"][args.case]["result_path"],
        "prb_core_runtime_seconds": prb["runtime_seconds"],
        "standard_over_prb_core_runtime": solved.total_runtime / prb["runtime_seconds"],
        "objective_difference_vs_prb": objective_difference,
        "objective_consistency_pass": objective_difference <= tolerance,
        "peak_memory_gb": None,
        "instance_hash": identity["instance_hash"],
        "x0_hash": identity["x0_hash"],
        "calibration_hash": identity["calibration_hash"],
        "mapping_hash": MAPPING_SHA256,
        "git_commit": _git_commit(),
        "solver_profile": FORMAL_SOLVER_PROFILE_ID,
        "solver_version": ".".join(map(str, __import__("gurobipy").gurobi.version())),
        "hardware": _hardware_info(),
    }
    _write_json(partial / "result.json", result)
    _write_json(partial / "provenance.json", {
        "authorization_sha256": sha256_file(AUTHORIZATION),
        "identity_table_sha256": sha256_file(IDENTITY_TABLE),
        "first_stage_solution_sha256": sha256_file(solution_path),
        "iteration_log_sha256": sha256_file(partial / "iteration_log.json"),
        "aggregate_cuts_sha256": sha256_file(partial / "aggregate_cuts.json"),
        "formal_run_authorized": manifest["formal_run_authorized"],
        "prb_e1a_result_sha256": manifest["prb_e1a_references"][args.case]["result_sha256"],
    })
    if objective_difference > tolerance:
        raise RuntimeError(f"E1B_OBJECTIVE_MISMATCH_{args.case}")
    shutil.move(str(partial), str(target))


if __name__ == "__main__":
    main()
