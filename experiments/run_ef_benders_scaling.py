"""Fail-closed EF-BD scaling pilot launcher; dry-run never builds a Gurobi model."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter
import subprocess
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_basic_benders_scaling as base
from experiments import run_direct_scaling as direct_runner

DEFAULT_CONFIG = ROOT / "experiments/configs/development/ef_benders_scaling_l10_resource_v2_7gib.yaml"


def model_identity() -> dict:
    paths = (
        "experiments/run_ef_benders_scaling.py",
        "src/robust_inventory_reconfiguration/extensive_form_benders.py",
        "src/robust_inventory_reconfiguration/pure_benders.py",
        "src/robust_inventory_reconfiguration/reconfiguration_model.py",
        "src/robust_inventory_reconfiguration/solver_profile.py",
    )
    files = {path: direct_runner.file_sha256(ROOT / path) for path in paths}
    return {"sha256": direct_runner.canonical_hash(files), "files": files}


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "method": "extensive_form_single_cut_benders",
    }
    for key, value in required.items():
        if config.get(key) != value:
            raise RuntimeError(f"invalid frozen EF-BD pilot field: {key}")
    protocols = {
        "EF_BD_SCALING_L10_SINGLE_PILOT_V1": ("L10", 4, 7, "BLOCKED_RESOURCE_DESIGN"),
        "EF_BD_L10_RESOURCE_PROTOCOL_V2_7GIB": ("L10", 7, 11, "READY_FOR_AUTHORIZATION"),
        "EF_BD_SCALING_L10_REMAINING9_V1": ("L10", 7, 11, "READY_FOR_AUTHORIZATION"),
        "EF_BD_XL10_SINGLE_PILOT_V1": ("XL10", 8, 12, "READY_FOR_AUTHORIZATION"),
        "EF_BD_XL10_REMAINING9_V1": ("XL10", 8, 12, "READY_FOR_AUTHORIZATION"),
        "EF_BD_XXL10_PAIRED_PILOT_V1": ("XXL10", 13, 17, "READY_FOR_AUTHORIZATION"),
        "EF_BD_XXL10_REMAINING9_V1": ("XXL10", 13, 17, "READY_FOR_AUTHORIZATION"),
    }
    protocol = config.get("protocol_id")
    if protocol not in protocols:
        raise RuntimeError("unexpected EF-BD pilot protocol identity")
    size, cap, startup, decision = protocols[protocol]
    if protocol == "EF_BD_SCALING_L10_REMAINING9_V1":
        expected_scope = [f"EF_L10_S{seed}" for seed in range(20260922, 20260931)]
    elif protocol == "EF_BD_XL10_REMAINING9_V1":
        expected_scope = [f"EF_XL10_S{seed}" for seed in range(20260922, 20260931)]
    elif protocol == "EF_BD_XXL10_REMAINING9_V1":
        expected_scope = [f"EF_XXL10_S{seed}" for seed in range(20260922, 20260931)]
    else:
        expected_scope = [f"EF_{size}_S20260921"]
    if config.get("authorized_condition_ids") != expected_scope:
        raise RuntimeError("EF-BD protocol condition scope is inconsistent")
    policy = config["resource_policy"]
    if policy["maximum_process_tree_memory_gib_by_size"][size] != cap or policy["minimum_available_memory_gib_by_size"][size] != startup or config.get("readiness_decision") != decision:
        raise RuntimeError("EF-BD resource protocol fields are inconsistent")
    if not isinstance(config.get("formal_run_authorized"), bool):
        raise RuntimeError("formal_run_authorized must be boolean")
    return config


def candidate(config: dict, condition_id: str | None = None) -> dict:
    allowed = config["authorized_condition_ids"]
    selected = condition_id or (allowed[0] if len(allowed) == 1 else None)
    if selected is None:
        raise RuntimeError("condition_id is required for a multi-condition EF-BD protocol")
    if selected not in allowed:
        raise RuntimeError("condition is outside the EF-BD pilot allowlist")
    match = re.fullmatch(r"EF_(L10|XL10|XXL10)_S(\d{8})", selected)
    if match is None:
        raise RuntimeError("invalid EF-BD condition identity")
    return {"condition_id": selected, "size": match.group(1), "seed": int(match.group(2))}


def source_condition(config: dict, selected: dict) -> dict:
    size = selected["size"]
    return {"condition_id": f"DIRECT_{size}_S{selected['seed']}", "size": size, "seed": selected["seed"]}


def dry_run(config_path: Path = DEFAULT_CONFIG, condition_id: str | None = None) -> dict:
    config = load_config(config_path)
    selected = candidate(config, condition_id)
    # Reuse the audited non-optimization identity/resource path.
    original_authorized = config["formal_run_authorized"]
    instance, preparation, hashes = direct_runner.verified_input(config, source_condition(config, selected))
    import psutil, shutil
    output = ROOT / config["output_directory"]
    policy = config["resource_policy"]
    size = selected["size"]
    direct_result = ROOT / "experiments/results/direct_scaling_extension_v1/runs" / f"DIRECT_{size}_S{selected['seed']}" / "result.json"
    direct_identity = True
    if direct_result.is_file():
        direct_identity = json.loads(direct_result.read_text(encoding="utf-8"))["instance_hash"] == preparation["instance_hash"]
    paired = {}
    for method in ("PURE_BENDERS", "AGGREGATE_BENDERS_STRUCTURED_ORACLE", "PRB_BENDERS"):
        path = ROOT / config["source_output_root"] / "runs" / f"ASC_{size}_S{selected['seed']}_{method}" / "result.json"
        if path.is_file():
            row = json.loads(path.read_text(encoding="utf-8"))
            paired[method] = row.get("instance_hash") == preparation["instance_hash"]
        else:
            paired[method] = None
    return {
        "protocol_id": config["protocol_id"], "formal_run_authorized": original_authorized,
        "config_path": str(config_path.resolve()),
        "config_sha256": direct_runner.file_sha256(config_path.resolve()),
        "config_identity": direct_runner.canonical_hash(config),
        "readiness_decision": config["readiness_decision"], "condition": selected,
        "source_instance_id": preparation["instance_id"], "instance_hash": preparation["instance_hash"],
        "x0_hash": preparation["x0_hash"], **hashes,
        "paired_instance_identity": {"Direct": direct_identity, **paired},
        "resource_gate": {
            "available_memory_gib": psutil.virtual_memory().available / 2**30,
            "startup_required_gib": policy["minimum_available_memory_gib_by_size"][size],
            "process_tree_cap_gib": policy["maximum_process_tree_memory_gib_by_size"][size],
            "system_available_floor_gib": policy["minimum_system_available_memory_gib"],
            "free_disk_gib": shutil.disk_usage(output.parent).free / 2**30,
            "minimum_free_disk_gib": policy["minimum_free_disk_gib"],
            "time_limit_seconds": policy["condition_time_limit_seconds"],
            "monitor_interval_seconds": policy["memory_monitor_interval_seconds"],
        },
        "canonical_result_exists": (output / "runs" / selected["condition_id"]).exists(),
        "attempt_exists": (output / "worker_logs" / selected["condition_id"] / "attempt-001").exists(),
        "next_attempt": "attempt-001", "solver_parameters": config["solver_parameters"],
        "environment": direct_runner.current_environment(), "optimization_calls": 0,
    }


def validate_execution_gate(config_path: Path = DEFAULT_CONFIG, condition_id: str | None = None) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: EF-BD scaling pilot remains disabled")
    if config.get("readiness_decision") != "READY_FOR_AUTHORIZATION":
        raise RuntimeError("BLOCKED_RESOURCE_DESIGN: resource protocol requires independent revision")
    audit = dry_run(config_path, condition_id)
    gate = audit["resource_gate"]
    if gate["available_memory_gib"] < gate["startup_required_gib"]:
        raise RuntimeError("RESOURCE_START_MEMORY_GATE")
    if gate["free_disk_gib"] < gate["minimum_free_disk_gib"]:
        raise RuntimeError("RESOURCE_DISK_GATE")
    if audit["canonical_result_exists"]:
        raise FileExistsError("refusing to overwrite an existing EF-BD result")
    output = (ROOT / config["output_directory"]).resolve()
    selected = candidate(config, condition_id)
    if (output / "worker_logs" / selected["condition_id"] / "attempt-001").exists():
        raise FileExistsError("attempt-001 already exists; automatic retry is forbidden")
    return audit


def _worker(config_path: Path, attempt_dir: Path, condition_id: str) -> int:
    from robust_inventory_reconfiguration.extensive_form_benders import solve_extensive_form_benders
    config = json.loads(config_path.read_text(encoding="utf-8"))
    selected = candidate(config, condition_id)
    instance, preparation, hashes = direct_runner.verified_input(config, source_condition(config, selected))
    started = perf_counter()
    trace = attempt_dir / "oracle_trace.jsonl"
    solved, diagnostics = solve_extensive_form_benders(
        instance, instance.initial_inventory, float(preparation["budget"]), 2, 0.05,
        trace_path=trace, threads=2,
        relative_gap_tolerance=config["solver_tolerances"]["relative_gap"],
        cut_tolerance=config["solver_tolerances"]["cut_violation"],
        objective_certification_tolerance=config["solver_tolerances"]["objective_certification"],
        max_iterations=config["algorithm"]["max_iterations"],
        time_limit=config["resource_policy"]["condition_time_limit_seconds"],
        log_file=attempt_dir / "solver.log",
    )
    certification_started = perf_counter()
    certified_recourse = direct_runner.certify_solution(instance, solved.solution, 2)
    certification_seconds = perf_counter() - certification_started
    exact = bool(solved.status == "OPTIMAL" and solved.exact_certification_pass and solved.cut_validity_pass and abs(solved.solution.first_stage_expenditure + certified_recourse - solved.solution.objective) <= 1e-4)
    calls = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    trajectory = []
    for index, row in enumerate(solved.iterations):
        item = asdict(row)
        item["first_stage_x"] = calls[index]["first_stage_x"]
        item["oracle_lp_solves"] = calls[index]["optimizer_calls"]
        trajectory.append(item)
    result = {
        "schema": "ef_benders_scaling_result_v1", "experiment_id": config["experiment_id"],
        "condition_id": condition_id, "attempt": "attempt-001", "method": "EF-BD",
        "size": selected["size"], "seed": selected["seed"],
        "solver_status": solved.status, "exact_certification": exact, "cut_validity": solved.cut_validity_pass,
        "final_objective": solved.solution.objective, "final_lower_bound": solved.final_lower_bound,
        "final_upper_bound": solved.final_upper_bound, "final_gap": solved.final_relative_gap,
        "iterations": len(solved.iterations), "cuts_added": solved.aggregate_cut_count,
        "algorithm_core_time": solved.total_runtime, "master_time": solved.master_runtime,
        "oracle_time": solved.global_oracle_runtime, "certification_time": certification_seconds,
        "total_time": perf_counter() - started, "oracle_engineering": diagnostics,
        "solver_parameters": config["solver_parameters"], "solver_profile": config["solver_profile"],
        "environment": direct_runner.current_environment(),
        "config_hash": direct_runner.canonical_hash(config), "model_identity": model_identity(),
        "instance_hash": preparation["instance_hash"],
    }
    base._write_json(attempt_dir / "result.json", result)
    base._write_json(attempt_dir / "iteration_trajectory.json", trajectory)
    base._write_json(attempt_dir / "first_stage_solution.json", {"y": solved.solution.y, "x": solved.solution.x, "a_plus": solved.solution.a_plus, "a_minus": solved.solution.a_minus})
    provenance = {
        "condition_id": condition_id, "attempt": "attempt-001",
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "config_sha256": base._sha256(config_path), "config_hash": result["config_hash"],
        "model_identity": result["model_identity"], "environment": result["environment"],
        "instance_hash": preparation["instance_hash"], "x0_hash": preparation["x0_hash"],
        "instance_sha256": hashes["instance_sha256"], "preparation_sha256": hashes["preparation_sha256"],
    }
    provenance.update({f"{name}_sha256": base._sha256(attempt_dir / filename) for name, filename in (("result", "result.json"), ("trajectory", "iteration_trajectory.json"), ("first_stage", "first_stage_solution.json"))})
    base._write_json(attempt_dir / "provenance.json", provenance)
    return 0 if exact else 2


def _configure_base_launcher() -> None:
    """Install the EF callbacks only in an invoked launcher process."""
    base.DEFAULT_CONFIG = DEFAULT_CONFIG
    base.load_config = load_config
    base.candidate = candidate
    base.source_condition = source_condition
    base.dry_run = dry_run
    base.validate_execution_gate = validate_execution_gate
    base._worker = _worker
    base.__file__ = __file__


def run_condition(config_path: Path, condition_id: str) -> dict:
    _configure_base_launcher()
    return base.run_condition(config_path.resolve(), condition_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--attempt-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--condition-id", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return _worker(args.config.resolve(), args.attempt_dir.resolve(), args.condition_id)
    if args.execute:
        _configure_base_launcher()
        print(json.dumps(base.run_single_pilot(args.config.resolve()), indent=2))
    else:
        print(json.dumps(dry_run(args.config.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
