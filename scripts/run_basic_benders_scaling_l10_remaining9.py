from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_basic_benders_scaling as runner


DEFAULT_CONFIG = ROOT / "experiments/configs/development/basic_benders_scaling_l10_remaining9_v1.yaml"
PILOT_CONFIG = ROOT / "experiments/configs/development/basic_benders_scaling_l10_pilot_v1.yaml"
EXPECTED = [f"BASIC_L10_S{seed}" for seed in range(20260922, 20260931)]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def active_solver_workers() -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (process.info.get("name") or "").lower()
            command = " ".join(process.info.get("cmdline") or []).lower()
            if name.startswith("gurobi") or (
                "run_basic_benders_scaling.py" in command and "--worker" in command
            ):
                found.append({"pid": process.info["pid"], "name": process.info.get("name")})
        except psutil.Error:
            continue
    return found


def validate_protocol(config: dict) -> None:
    pilot = runner.load_config(PILOT_CONFIG)
    checks = {
        "protocol_id": config.get("protocol_id") == "BASIC_BD_SCALING_L10_REMAINING9_V1",
        "scope": config.get("authorized_condition_ids") == EXPECTED,
        "scientific_parameters": config.get("fixed_scientific_parameters") == pilot["fixed_scientific_parameters"],
        "solver_profile": config.get("solver_profile") == pilot["solver_profile"],
        "solver_tolerances": config.get("solver_tolerances") == pilot["solver_tolerances"],
        "algorithm": config.get("algorithm") == pilot["algorithm"],
        "resource_policy": {
            key: config["resource_policy"][key]
            for key in (
                "parallel_workers",
                "minimum_available_memory_gib_by_size",
                "maximum_process_tree_memory_gib_by_size",
                "minimum_system_available_memory_gib",
                "minimum_free_disk_gib",
                "condition_time_limit_seconds",
                "memory_monitor_interval_seconds",
                "fail_closed",
                "retry_policy",
            )
        } == {
            key: pilot["resource_policy"][key]
            for key in (
                "parallel_workers",
                "minimum_available_memory_gib_by_size",
                "maximum_process_tree_memory_gib_by_size",
                "minimum_system_available_memory_gib",
                "minimum_free_disk_gib",
                "condition_time_limit_seconds",
                "memory_monitor_interval_seconds",
                "fail_closed",
                "retry_policy",
            )
        },
        "fixed_denominator": len(config.get("frozen_input_identity", {})) == 9,
    }
    if not all(checks.values()):
        raise RuntimeError(f"remaining-nine protocol mismatch: {checks}")


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    conditions = []
    for condition_id in EXPECTED:
        row = runner.dry_run(config_path, condition_id)
        frozen = config["frozen_input_identity"][condition_id]
        identity_checks = {
            "instance_sha256": row["instance_sha256"] == frozen["instance_sha256"],
            "preparation_sha256": row["preparation_sha256"] == frozen["preparation_sha256"],
            "instance_hash": row["instance_hash"] == frozen["instance_hash"],
            "x0_hash": row["x0_hash"] == frozen["x0_hash"],
        }
        output = ROOT / config["output_directory"]
        attempt = output / "worker_logs" / condition_id / "attempt-001"
        row.update({
            "expected_attempt": "attempt-001",
            "attempt_exists": attempt.exists(),
            "identity_checks": identity_checks,
            "identity_status": "PASS" if all(identity_checks.values()) else "FAIL",
        })
        conditions.append(row)
    common = conditions[0]
    solver_processes = active_solver_workers()
    gates = {
        "all_nine_identities": all(row["identity_status"] == "PASS" for row in conditions),
        "all_attempts_absent": all(not row["attempt_exists"] for row in conditions),
        "all_canonical_results_absent": all(not row["canonical_result_exists"] for row in conditions),
        "startup_memory": common["resource_gate"]["available_memory_gib"] >= 7,
        "disk": common["resource_gate"]["free_disk_gib"] >= 20,
        "git_status": common["git_status_clean_for_execution"],
        "no_active_solver_worker": not solver_processes,
    }
    return {
        "schema": "basic_benders_l10_remaining9_dry_run_v1",
        "protocol_id": config["protocol_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "fixed_denominator": 9,
        "conditions": conditions,
        "resource_policy": config["resource_policy"],
        "failure_policy": config["failure_policy"],
        "active_solver_workers": solver_processes,
        "gates": gates,
        "decision": "READY_FOR_AUTHORIZATION" if all(gates.values()) else "BLOCKED",
        "optimization_calls": 0,
    }


def _verify_success(config: dict, condition_id: str) -> dict:
    root = ROOT / config["output_directory"] / "runs" / condition_id
    result_path = root / "result.json"
    provenance_path = root / "provenance.json"
    trajectory_path = root / "iteration_trajectory.json"
    if not all(path.is_file() for path in (result_path, provenance_path, trajectory_path)):
        raise RuntimeError(f"INTEGRITY_FAILURE incomplete canonical archive: {condition_id}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    checks = {
        "condition": result.get("condition_id") == condition_id,
        "exact": result.get("exact_certification") is True,
        "optimal": result.get("solver_status") == "OPTIMAL",
        "cut_validity": result.get("cut_validity") is True,
        "result_hash": runner._sha256(result_path) == provenance.get("result_sha256"),
        "trajectory_hash": runner._sha256(trajectory_path) == provenance.get("trajectory_sha256"),
    }
    if not all(checks.values()):
        raise RuntimeError(f"INTEGRITY_FAILURE {condition_id}: {checks}")
    return {"classification": "SUCCESS", "checks": checks}


def _verify_frozen_identity(config: dict, condition_id: str, preflight: dict) -> None:
    frozen = config["frozen_input_identity"][condition_id]
    checks = {
        "instance_sha256": preflight["instance_sha256"] == frozen["instance_sha256"],
        "preparation_sha256": preflight["preparation_sha256"] == frozen["preparation_sha256"],
        "instance_hash": preflight["instance_hash"] == frozen["instance_hash"],
        "x0_hash": preflight["x0_hash"] == frozen["x0_hash"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"IDENTITY_FAILURE {condition_id}: {checks}")


def execute_batch(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: remaining-nine Basic-BD batch remains disabled")
    initial = build_dry_run(config_path)
    if not all(initial["gates"].values()):
        raise RuntimeError(f"BATCH_PREFLIGHT_BLOCKED: {initial['gates']}")
    output = ROOT / config["output_directory"]
    report_path = output / "batch_reports" / f"{config['protocol_id']}.json"
    records = []
    report = {
        "protocol_id": config["protocol_id"],
        "fixed_denominator": 9,
        "status": "RUNNING",
        "records": records,
    }
    _write_json(report_path, report)
    for condition_id in EXPECTED:
        preflight = runner.validate_execution_gate(config_path, condition_id)
        _verify_frozen_identity(config, condition_id, preflight)
        if active_solver_workers():
            raise RuntimeError(f"INTEGRITY_FAILURE active worker before {condition_id}")
        monitor = runner.run_condition(config_path, condition_id)
        stop_reason = monitor["stop_reason"]
        if monitor["worker_return_code"] == 0 and stop_reason is None:
            verification = _verify_success(config, condition_id)
            classification = verification["classification"]
        elif stop_reason in config["failure_policy"]["continue_after"]:
            if active_solver_workers():
                raise RuntimeError(f"INTEGRITY_FAILURE worker survived stop: {condition_id}")
            verification = {"classification": "RESOURCE_OR_TIME_FAILURE", "checks": {}}
            classification = verification["classification"]
        else:
            verification = {"classification": "INTEGRITY_FAILURE", "checks": {}}
            classification = verification["classification"]
        records.append({
            "condition_id": condition_id,
            "attempt": "attempt-001",
            "classification": classification,
            "stop_reason": stop_reason,
            "worker_return_code": monitor["worker_return_code"],
            "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"],
            "verification": verification,
            "preflight": preflight,
        })
        report["status"] = "RUNNING" if classification != "INTEGRITY_FAILURE" else "STOPPED_INTEGRITY_FAILURE"
        _write_json(report_path, report)
        if classification == "INTEGRITY_FAILURE":
            raise RuntimeError(f"INTEGRITY_FAILURE stops batch: {condition_id}")
    report["status"] = "COMPLETE"
    _write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config_path = args.config.resolve()
    result = execute_batch(config_path) if args.execute else build_dry_run(config_path)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
