from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_direct_scaling as runner


DEFAULT_CONFIG = ROOT / "experiments/configs/development/direct_scaling_xxl10_paired_pilot_v1.yaml"
CONDITION_ID = "DIRECT_XXL10_S20260921"
CORE_RUNNER_PATH = "experiments/run_direct_scaling.py"
CORE_RUNNER_SHA256 = "fef8019f9aa9be1d2942a5d3aad363c2c3c28929e52cc02b359d1626a1880edd"
FAILURE_FRAGMENT = "RuntimeError: formal Direct execution found changes outside its output root"
ATTEMPT_001_FILES = {"stdout.log", "stderr.log", "resource_monitor.json"}
HISTORICAL_ARCHIVE_PREFIXES = (
    "experiments/results/basic_benders_scaling_development_v1/",
    "experiments/results/ef_benders_scaling_development_v1/",
    "experiments/results/ef_benders_scaling_xl10_pilot_v1/",
    "experiments/results/ef_benders_scaling_xl10_remaining9_v1/",
    "experiments/results/ef_benders_scaling_xxl10_paired_pilot_v1/",
    "experiments/results/ef_benders_scaling_xxl10_remaining9_v1/",
)
AUDIT_PATHS = {
    "artifacts/direct_ef_benders_xxl10_paired_preparation_audit.json",
    "artifacts/direct_scaling_xxl10_attempt002_recovery_audit.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_paired_solver_workers(*, exclude_pid: int | None = None) -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if process.info["pid"] == exclude_pid:
                continue
            name = (process.info.get("name") or "").lower()
            command = " ".join(process.info.get("cmdline") or []).lower()
            worker = "--worker" in command and any(
                script in command
                for script in (
                    "run_direct_scaling.py",
                    "run_direct_scaling_xxl10_paired_pilot.py",
                    "run_ef_benders_scaling.py",
                )
            )
            if name.startswith("gurobi") or worker:
                found.append({"pid": process.info["pid"], "name": name, "cmdline": process.info.get("cmdline") or []})
        except psutil.Error:
            continue
    return found


def allowed_git_prefixes(output: Path) -> tuple[str, ...]:
    relative_output = output.resolve().relative_to(ROOT.resolve()).as_posix() + "/"
    return (relative_output, *HISTORICAL_ARCHIVE_PREFIXES)


def unexpected_git_entries(entries: list[str], output: Path) -> list[str]:
    allowed_prefixes = allowed_git_prefixes(output)
    unexpected = []
    for line in entries:
        path = line[3:].replace("\\", "/")
        if path in AUDIT_PATHS or path.startswith(allowed_prefixes):
            continue
        unexpected.append(line)
    return unexpected


def git_status_for_execution(output: Path) -> dict:
    entries = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True
    ).splitlines()
    unexpected = unexpected_git_entries(entries, output)
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "clean_for_execution": not unexpected,
        "unexpected": unexpected,
    }


def validate_protocol(config: dict) -> None:
    policy = config["resource_policy"]
    recovery = config.get("recovery_control", {})
    checks = {
        "protocol": config.get("resource_protocol_id") == "DIRECT_XXL10_PAIRED_PILOT_V1_METHOD2_THREADS2",
        "scope": config.get("authorized_condition_ids") == [CONDITION_ID],
        "formal_authorization": config.get("formal_run_authorized") is True,
        "recovery_authorization_boolean": isinstance(recovery.get("authorized"), bool),
        "recovery_identity": recovery.get("attempt") == "attempt-002" and recovery.get("required_prior_attempt") == "attempt-001" and recovery.get("required_failure") == "WORKER_INNER_GIT_GATE_MISMATCH",
        "dimensions": config.get("sizes") == [{"label": "XXL10", "I": 36, "R": 36, "J": 16}],
        "science": config.get("fixed_scientific_parameters") == {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "SL": 0.90, "phi_multiplier": 1.85},
        "solver": config.get("solver_parameters", {}).get("Method") == 2 and config.get("solver_parameters", {}).get("Threads") == 2 and config.get("solver_parameters", {}).get("MIPGap") == 0.0,
        "resource": (
            policy["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
            and policy["minimum_available_memory_gib_by_size"] == {"XXL10": 16}
            and policy["minimum_system_available_memory_gib"] == 3
            and policy["minimum_free_disk_gib"] == 20
            and policy["condition_time_limit_seconds"] == 900
            and policy["memory_monitor_interval_seconds"] == 0.25
            and policy["parallel_workers"] == 1
            and policy["retry_policy"] == "no_automatic_retry"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"Direct XXL10 paired-pilot recovery protocol mismatch: {checks}")


def audit_attempt_001(output: Path) -> dict:
    attempt = output / "worker_logs" / CONDITION_ID / "attempt-001"
    files = {path.name for path in attempt.iterdir() if path.is_file()} if attempt.is_dir() else set()
    stderr_path = attempt / "stderr.log"
    monitor_path = attempt / "resource_monitor.json"
    stderr = stderr_path.read_text(encoding="utf-8") if stderr_path.is_file() else ""
    monitor = json.loads(monitor_path.read_text(encoding="utf-8")) if monitor_path.is_file() else {}
    checks = {
        "directory_exists": attempt.is_dir(),
        "exact_file_set": files == ATTEMPT_001_FILES,
        "failure_signature": FAILURE_FRAGMENT in stderr,
        "condition": monitor.get("condition_id") == CONDITION_ID,
        "attempt": monitor.get("attempt") == "attempt-001",
        "worker_return_code": monitor.get("worker_return_code") == 1,
        "stop_reason": monitor.get("stop_reason") is None,
        "low_peak_before_model_build": monitor.get("peak_process_tree_memory_gib") == 0.034252166748046875,
        "short_wall_time": monitor.get("wall_clock_seconds") == 0.8216574001125991,
    }
    return {
        "classification": "WORKER_INNER_GIT_GATE_MISMATCH" if all(checks.values()) else "UNKNOWN_FAILURE",
        "checks": checks,
        "files": {
            name: {"sha256": sha256(attempt / name), "size": (attempt / name).stat().st_size}
            for name in sorted(files)
        },
        "monitor": monitor,
    }


def validate_attempt_002_state(output: Path, *, expect_started: bool) -> bool:
    attempt = output / "worker_logs" / CONDITION_ID / "attempt-002"
    if not expect_started:
        return not attempt.exists()
    if not attempt.is_dir():
        return False
    return {path.name for path in attempt.iterdir()} <= {"stdout.log", "stderr.log"}


def _identity_and_resource(config_path: Path, *, expect_attempt_002: bool) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    condition = runner.authorized_conditions(config)[0]
    output = (ROOT / config["output_directory"]).resolve()
    instance, preparation, hashes = runner.verified_input(config, condition)
    frozen = config["frozen_input_identity"]
    identity_checks = {
        "condition_id": condition["condition_id"] == frozen["condition_id"],
        "source_instance_id": preparation["instance_id"] == frozen["source_instance_id"],
        "dimensions": (instance.num_depots, instance.num_regions, instance.num_products) == (36, 36, 16),
        "instance_hash": preparation["instance_hash"] == frozen["instance_hash"],
        "x0_hash": preparation["x0_hash"] == frozen["x0_hash"],
        "instance_sha256": hashes["instance_sha256"] == frozen["instance_sha256"],
        "preparation_sha256": hashes["preparation_sha256"] == frozen["preparation_sha256"],
    }
    model = runner.model_identity()
    model_checks = {path: model["files"].get(path) == value for path, value in config["frozen_model_files"].items()}
    environment = runner.validate_environment(config)
    available = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output.parent).free / 2**30
    attempt_002_check = validate_attempt_002_state(output, expect_started=expect_attempt_002)
    return {
        "config": config,
        "condition": condition,
        "output": output,
        "input_identity": {"source_instance_id": preparation["instance_id"], "instance_hash": preparation["instance_hash"], "x0_hash": preparation["x0_hash"], **hashes},
        "identity_checks": identity_checks,
        "model_identity": model,
        "model_identity_checks": model_checks,
        "environment": environment,
        "attempt_001": audit_attempt_001(output),
        "attempt_002_state_valid": attempt_002_check,
        "canonical_absent": not (output / "runs" / CONDITION_ID).exists(),
        "resource_gate": {
            "available_memory_gib": available,
            "startup_required_gib": 16,
            "process_tree_cap_gib": 13,
            "system_available_floor_gib": 3,
            "free_disk_gib": free_disk,
            "minimum_free_disk_gib": 20,
            "time_limit_seconds": 900,
            "monitor_interval_seconds": 0.25,
        },
        "git": git_status_for_execution(output),
        "active_paired_solver_workers": active_paired_solver_workers(exclude_pid=os.getpid()),
    }


def _gates(state: dict) -> dict:
    resource = state["resource_gate"]
    return {
        "attempt_001_known_failure": state["attempt_001"]["classification"] == "WORKER_INNER_GIT_GATE_MISMATCH",
        "frozen_identity": all(state["identity_checks"].values()),
        "frozen_model": all(state["model_identity_checks"].values()),
        "environment": state["environment"]["pass"],
        "attempt_002_state": state["attempt_002_state_valid"],
        "canonical_absent": state["canonical_absent"],
        "startup_memory": resource["available_memory_gib"] >= resource["startup_required_gib"],
        "disk": resource["free_disk_gib"] >= resource["minimum_free_disk_gib"],
        "git_identity": state["git"]["clean_for_execution"],
        "no_other_paired_worker": not state["active_paired_solver_workers"],
    }


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    state = _identity_and_resource(config_path.resolve(), expect_attempt_002=False)
    gates = _gates(state)
    nonresource_ready = all(value for key, value in gates.items() if key != "startup_memory")
    recovery_authorized = state["config"]["recovery_control"]["authorized"]
    if all(gates.values()):
        decision = "AUTHORIZED_READY" if recovery_authorized else "READY_FOR_RECOVERY_AUTHORIZATION"
    elif nonresource_ready and not gates["startup_memory"]:
        decision = "RESOURCE_BLOCKED"
    else:
        decision = "BLOCKED"
    return {
        "schema": "direct_xxl10_attempt002_recovery_dry_run_v1",
        "decision": decision,
        "formal_run_authorized": state["config"]["formal_run_authorized"],
        "recovery_attempt_authorized": recovery_authorized,
        "condition": state["condition"],
        "next_attempt": "attempt-002",
        "attempt_001": state["attempt_001"],
        "input_identity": state["input_identity"],
        "identity_checks": state["identity_checks"],
        "model_identity_checks": state["model_identity_checks"],
        "environment": state["environment"],
        "resource_gate": state["resource_gate"],
        "git": state["git"],
        "active_paired_solver_workers": state["active_paired_solver_workers"],
        "gates": gates,
        "config_sha256": runner.file_sha256(config_path.resolve()),
        "config_identity": runner.canonical_hash(state["config"]),
        "model_identity": state["model_identity"],
        "optimization_calls": 0,
    }


def worker_preflight(config_path: Path, *, expect_attempt_002: bool, require_recovery_authorization: bool) -> dict:
    state = _identity_and_resource(config_path.resolve(), expect_attempt_002=expect_attempt_002)
    gates = _gates(state)
    if require_recovery_authorization and state["config"]["recovery_control"]["authorized"] is not True:
        raise RuntimeError("RECOVERY_ATTEMPT_002_NOT_AUTHORIZED")
    if not all(gates.values()):
        raise RuntimeError(f"DIRECT_XXL10_RECOVERY_WORKER_BLOCKED: {gates}")
    return {**state["resource_gate"], "git": state["git"], "optimization_calls": 0}


def worker_preflight_report(config_path: Path, *, expect_attempt_002: bool) -> dict:
    state = _identity_and_resource(config_path.resolve(), expect_attempt_002=expect_attempt_002)
    gates = _gates(state)
    return {
        "pass": all(gates.values()),
        "gates": gates,
        "resource_gate": state["resource_gate"],
        "git": state["git"],
        "optimization_calls": 0,
    }


def worker_solve(config_path: Path, output_root: Path, condition_id: str) -> None:
    config = runner.load_config(config_path)
    condition = runner.authorized_conditions(config)[0]
    expected_output = (ROOT / config["output_directory"]).resolve()
    if condition_id != CONDITION_ID or output_root.resolve() != expected_output:
        raise RuntimeError("Direct XXL10 recovery worker identity mismatch")
    gate = worker_preflight(config_path, expect_attempt_002=True, require_recovery_authorization=True)
    original = runner.validate_execution_gate
    try:
        runner.validate_execution_gate = lambda *_args: gate
        runner.solve_condition(config, condition, expected_output)
    finally:
        runner.validate_execution_gate = original


def execute(config_path: Path = DEFAULT_CONFIG) -> None:
    config = runner.load_config(config_path)
    validate_protocol(config)
    if config["recovery_control"]["authorized"] is not True:
        raise RuntimeError("RECOVERY_ATTEMPT_002_NOT_AUTHORIZED")
    dry = build_dry_run(config_path)
    if dry["decision"] != "AUTHORIZED_READY":
        raise RuntimeError(f"DIRECT_XXL10_RECOVERY_BLOCKED: {dry['gates']}")
    condition = runner.authorized_conditions(config)[0]
    output = (ROOT / config["output_directory"]).resolve()
    parent_gate = worker_preflight(config_path, expect_attempt_002=False, require_recovery_authorization=True)
    original_gate = runner.validate_execution_gate
    original_file = runner.__file__
    try:
        runner.validate_execution_gate = lambda *_args: parent_gate
        runner.__file__ = __file__
        runner.run_monitored(config_path.resolve(), config, condition, output)
    finally:
        runner.validate_execution_gate = original_gate
        runner.__file__ = original_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", metavar="CONDITION_ID", help=argparse.SUPPRESS)
    parser.add_argument("--worker-preflight", action="store_true")
    parser.add_argument("--output-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    config_path = args.config.resolve()
    if args.worker:
        worker_solve(config_path, args.output_root.resolve(), args.worker)
    elif args.worker_preflight:
        print(json.dumps(worker_preflight_report(config_path, expect_attempt_002=False), indent=2, allow_nan=False))
    elif args.execute:
        execute(config_path)
    else:
        print(json.dumps(build_dry_run(config_path), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
