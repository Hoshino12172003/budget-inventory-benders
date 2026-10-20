from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_ef_benders_scaling as runner


DEFAULT_CONFIG = ROOT / "experiments/configs/development/ef_benders_scaling_xl10_pilot_v1.yaml"
CONDITION_ID = "EF_XL10_S20260921"
L10_ROOT = ROOT / "experiments/results/ef_benders_scaling_development_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_solver_workers() -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (process.info.get("name") or "").lower()
            command = " ".join(process.info.get("cmdline") or []).lower()
            if name.startswith("gurobi") or ("run_ef_benders_scaling.py" in command and "--worker" in command):
                found.append({"pid": process.info["pid"], "name": process.info.get("name"), "cmdline": process.info.get("cmdline") or []})
        except psutil.Error:
            continue
    return found


def git_status_for_execution(output: Path) -> dict:
    entries = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    allowed = (
        output.resolve().relative_to(ROOT.resolve()).as_posix() + "/",
        L10_ROOT.resolve().relative_to(ROOT.resolve()).as_posix() + "/",
        "experiments/results/basic_benders_scaling_development_v1/",
    )
    unexpected = [line for line in entries if not line[3:].replace("\\", "/").startswith(allowed)]
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "clean_for_execution": not unexpected,
        "unexpected": unexpected,
    }


def verify_archive(output: Path, condition_id: str, attempt_name: str = "attempt-001") -> dict:
    attempt = output / "worker_logs" / condition_id / attempt_name
    canonical = output / "runs" / condition_id
    required = (
        "result.json", "provenance.json", "iteration_trajectory.json",
        "first_stage_solution.json", "resource_monitor.json", "outcome.json",
    )
    if not all((attempt / name).is_file() and (canonical / name).is_file() for name in required):
        raise RuntimeError(f"ARCHIVE_INCOMPLETE: {condition_id}")
    result = json.loads((canonical / "result.json").read_text(encoding="utf-8"))
    provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8"))
    monitor = json.loads((canonical / "resource_monitor.json").read_text(encoding="utf-8"))
    outcome = json.loads((canonical / "outcome.json").read_text(encoding="utf-8"))
    canonical_files = sorted(path.name for path in canonical.iterdir() if path.is_file())
    checks = {
        "optimal": result.get("solver_status") == "OPTIMAL",
        "exact_certification": result.get("exact_certification") is True,
        "cut_validity": result.get("cut_validity") is True,
        "resource_monitor": monitor.get("stop_reason") is None and monitor.get("worker_return_code") == 0,
        "outcome": outcome.get("status") == "SUCCESS",
        "result_hash": provenance.get("result_sha256") == sha256(canonical / "result.json"),
        "trajectory_hash": provenance.get("trajectory_sha256") == sha256(canonical / "iteration_trajectory.json"),
        "first_stage_hash": provenance.get("first_stage_sha256") == sha256(canonical / "first_stage_solution.json"),
        "attempt_canonical_bytes": all(
            (attempt / name).is_file() and sha256(attempt / name) == sha256(canonical / name)
            for name in canonical_files
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"ARCHIVE_OR_CERTIFICATION_FAILURE {condition_id}: {checks}")
    return {
        "condition_id": condition_id,
        "attempt": attempt_name,
        "checks": checks,
        "result_sha256": sha256(canonical / "result.json"),
        "provenance_sha256": sha256(canonical / "provenance.json"),
        "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"],
    }


def l10_frozen_audit() -> dict:
    rows = []
    for seed in range(20260921, 20260931):
        condition_id = f"EF_L10_S{seed}"
        audit = verify_archive(L10_ROOT, condition_id)
        result = json.loads((L10_ROOT / "runs" / condition_id / "result.json").read_text(encoding="utf-8"))
        rows.append({
            **audit,
            "algorithm_core_time": result["algorithm_core_time"],
            "iterations": result["iterations"],
        })
    return {
        "status": "PASS",
        "certified": len(rows),
        "expected": 10,
        "mean_algorithm_core_time": sum(row["algorithm_core_time"] for row in rows) / len(rows),
        "maximum_peak_process_tree_memory_gib": max(row["peak_process_tree_memory_gib"] for row in rows),
        "conditions": rows,
    }


def validate_protocol(config: dict) -> None:
    policy = config["resource_policy"]
    checks = {
        "protocol": config.get("protocol_id") == "EF_BD_XL10_SINGLE_PILOT_V1",
        "scope": config.get("authorized_condition_ids") == [CONDITION_ID],
        "authorization_boolean": isinstance(config.get("formal_run_authorized"), bool),
        "dimensions": config.get("sizes") == [{"label": "XL10", "I": 30, "R": 30, "J": 14}],
        "science": config.get("fixed_scientific_parameters") == {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "SL": 0.90, "phi_multiplier": 1.85},
        "solver": config.get("solver_parameters") == {"Threads": 2},
        "resource": (
            policy["maximum_process_tree_memory_gib_by_size"] == {"XL10": 8}
            and policy["minimum_available_memory_gib_by_size"] == {"XL10": 12}
            and policy["minimum_system_available_memory_gib"] == 3
            and policy["minimum_free_disk_gib"] == 20
            and policy["condition_time_limit_seconds"] == 900
            and policy["memory_monitor_interval_seconds"] == 0.25
            and policy["parallel_workers"] == 1
            and policy["retry_policy"] == "no_automatic_retry"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"XL10 EF-BD protocol mismatch: {checks}")


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    row = runner.dry_run(config_path, CONDITION_ID)
    output = ROOT / config["output_directory"]
    frozen = config["frozen_input_identity"]
    identity_checks = {
        "condition_id": row["condition"]["condition_id"] == frozen["condition_id"],
        "source_instance_id": row["source_instance_id"] == frozen["source_instance_id"],
        "instance_hash": row["instance_hash"] == frozen["instance_hash"],
        "x0_hash": row["x0_hash"] == frozen["x0_hash"],
        "instance_sha256": row["instance_sha256"] == frozen["instance_sha256"],
        "preparation_sha256": row["preparation_sha256"] == frozen["preparation_sha256"],
        "paired_methods": all(row["paired_instance_identity"].values()),
    }
    environment = row["environment"]
    required_environment = config["required_environment"]
    environment_checks = {
        "python_version": environment["python_version"] == required_environment["python_version"],
        "gurobipy_version": environment["gurobipy_version"] == required_environment["gurobipy_version"],
        "gurobi_native_version": environment["gurobi_native_version"] == required_environment["gurobi_native_version"],
    }
    git = git_status_for_execution(output)
    active = active_solver_workers()
    gate = row["resource_gate"]
    gates = {
        "frozen_identity": all(identity_checks.values()),
        "environment": all(environment_checks.values()),
        "attempt_absent": not row["attempt_exists"],
        "canonical_absent": not row["canonical_result_exists"],
        "startup_memory": gate["available_memory_gib"] >= gate["startup_required_gib"],
        "disk": gate["free_disk_gib"] >= gate["minimum_free_disk_gib"],
        "git_identity": git["clean_for_execution"],
        "no_active_solver_worker": not active,
    }
    ready = all(gates.values())
    decision = ("AUTHORIZED_READY" if config["formal_run_authorized"] else "READY_FOR_AUTHORIZATION") if ready else "BLOCKED"
    return {
        "schema": "ef_benders_xl10_pilot_dry_run_v1",
        "decision": decision,
        "formal_run_authorized": config["formal_run_authorized"],
        "condition": row,
        "identity_checks": identity_checks,
        "environment_checks": environment_checks,
        "model_identity": runner.model_identity(),
        "git": git,
        "active_solver_workers": active,
        "gates": gates,
        "next_attempt": "attempt-001",
        "optimization_calls": 0,
    }


def execute(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: EF-BD XL10 pilot remains disabled")
    dry = build_dry_run(config_path)
    if dry["decision"] != "AUTHORIZED_READY":
        raise RuntimeError(f"PILOT_PREFLIGHT_BLOCKED: {dry['gates']}")
    monitor = runner.run_condition(config_path, CONDITION_ID)
    if monitor.get("worker_return_code") == 0 and monitor.get("stop_reason") is None:
        verify_archive(ROOT / config["output_directory"], CONDITION_ID)
    return monitor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    value = execute(args.config.resolve()) if args.execute else build_dry_run(args.config.resolve())
    print(json.dumps(value, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
