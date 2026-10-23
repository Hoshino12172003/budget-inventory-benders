from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_ef_benders_scaling as runner

DEFAULT_CONFIG = ROOT / "experiments/configs/development/ef_benders_scaling_l10_remaining9_v1.yaml"
PILOT_ROOT = ROOT / "experiments/results/ef_benders_scaling_development_v1"
EXPECTED = [f"EF_L10_S{seed}" for seed in range(20260922, 20260931)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
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
            if name.startswith("gurobi") or ("run_ef_benders_scaling.py" in command and "--worker" in command):
                found.append({"pid": process.info["pid"], "name": process.info.get("name")})
        except psutil.Error:
            continue
    return found


def pilot_audit() -> dict:
    attempt = PILOT_ROOT / "worker_logs/EF_L10_S20260921/attempt-001"
    canonical = PILOT_ROOT / "runs/EF_L10_S20260921"
    required = ("result.json", "provenance.json", "iteration_trajectory.json", "resource_monitor.json", "outcome.json")
    if not all((attempt / name).is_file() and (canonical / name).is_file() for name in required):
        raise RuntimeError("PILOT_ARCHIVE_INCOMPLETE")
    all_files = sorted(path.name for path in attempt.iterdir() if path.is_file())
    byte_checks = {name: sha256(attempt / name) == sha256(canonical / name) for name in all_files}
    result = json.loads((canonical / "result.json").read_text(encoding="utf-8"))
    provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8"))
    monitor = json.loads((canonical / "resource_monitor.json").read_text(encoding="utf-8"))
    outcome = json.loads((canonical / "outcome.json").read_text(encoding="utf-8"))
    content_checks = {
        "optimal": result.get("solver_status") == "OPTIMAL",
        "exact": result.get("exact_certification") is True,
        "cut_validity": result.get("cut_validity") is True,
        "result_hash": sha256(canonical / "result.json") == provenance.get("result_sha256"),
        "trajectory_hash": sha256(canonical / "iteration_trajectory.json") == provenance.get("trajectory_sha256"),
        "first_stage_hash": sha256(canonical / "first_stage_solution.json") == provenance.get("first_stage_sha256"),
        "resource_clean": monitor.get("stop_reason") is None and monitor.get("worker_return_code") == 0,
        "outcome_success": outcome.get("status") == "SUCCESS",
        "all_attempt_canonical_bytes": all(byte_checks.values()),
    }
    if not all(content_checks.values()):
        raise RuntimeError(f"PILOT_ACCEPTANCE_FAILURE: {content_checks}")
    return {"result": result, "provenance": provenance, "resource_monitor": monitor, "checks": content_checks, "file_sha256": {name: sha256(canonical / name) for name in all_files}}


def git_status_for_execution(output: Path) -> dict:
    entries = subprocess.check_output(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True).splitlines()
    allowed = (
        output.resolve().relative_to(ROOT.resolve()).as_posix() + "/",
        "experiments/results/basic_benders_scaling_development_v1/",
    )
    unexpected = [line for line in entries if not line[3:].replace("\\", "/").startswith(allowed)]
    return {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "clean_for_execution": not unexpected, "unexpected": unexpected}


def validate_protocol(config: dict) -> None:
    resource = config["resource_policy"]
    checks = {
        "protocol": config.get("protocol_id") == "EF_BD_SCALING_L10_REMAINING9_V1",
        "scope": config.get("authorized_condition_ids") == EXPECTED,
        "authorization_boolean": isinstance(config.get("formal_run_authorized"), bool),
        "science": config.get("fixed_scientific_parameters") == {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "SL": 0.90, "phi_multiplier": 1.85},
        "solver": config.get("solver_parameters") == {"Threads": 2},
        "resource": resource["maximum_process_tree_memory_gib_by_size"] == {"L10": 7} and resource["minimum_available_memory_gib_by_size"] == {"L10": 11} and resource["minimum_system_available_memory_gib"] == 3 and resource["condition_time_limit_seconds"] == 900 and resource["minimum_free_disk_gib"] == 20 and resource["memory_monitor_interval_seconds"] == 0.25 and resource["parallel_workers"] == 1 and resource["retry_policy"] == "no_automatic_retry",
        "denominator": len(config.get("frozen_input_identity", {})) == 9,
    }
    if not all(checks.values()):
        raise RuntimeError(f"EF remaining-nine protocol mismatch: {checks}")


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    pilot = pilot_audit()
    output = ROOT / config["output_directory"]
    conditions = []
    for condition_id in EXPECTED:
        row = runner.dry_run(config_path, condition_id)
        frozen = config["frozen_input_identity"][condition_id]
        identity = {key: row[key] == frozen[key] for key in ("instance_sha256", "preparation_sha256", "instance_hash", "x0_hash")}
        row.update({"attempt_exists": (output / "worker_logs" / condition_id / "attempt-001").exists(), "expected_attempt": "attempt-001", "identity_checks": identity, "identity_status": "PASS" if all(identity.values()) else "FAIL"})
        conditions.append(row)
    resources = conditions[0]["resource_gate"]
    git = git_status_for_execution(output)
    active = active_solver_workers()
    gates = {
        "pilot_accepted": all(pilot["checks"].values()),
        "all_nine_identities": all(row["identity_status"] == "PASS" for row in conditions),
        "all_attempts_absent": all(not row["attempt_exists"] for row in conditions),
        "all_canonical_absent": all(not row["canonical_result_exists"] for row in conditions),
        "startup_memory": resources["available_memory_gib"] >= 11,
        "disk": resources["free_disk_gib"] >= 20,
        "git_identity": git["clean_for_execution"],
        "no_active_solver_worker": not active,
    }
    ready = all(gates.values())
    decision = ("AUTHORIZED_READY" if config["formal_run_authorized"] else "READY_FOR_AUTHORIZATION") if ready else "BLOCKED"
    return {"schema": "ef_benders_l10_remaining9_dry_run_v1", "protocol_id": config["protocol_id"], "formal_run_authorized": config["formal_run_authorized"], "fixed_denominator_remaining": 9, "fixed_denominator_total_l10": 10, "conditions": conditions, "pilot": pilot, "resource_policy": config["resource_policy"], "failure_policy": config["failure_policy"], "git": git, "active_solver_workers": active, "gates": gates, "decision": decision, "optimization_calls": 0}


def verify_success(config: dict, condition_id: str) -> dict:
    canonical = ROOT / config["output_directory"] / "runs" / condition_id
    attempt = ROOT / config["output_directory"] / "worker_logs" / condition_id / "attempt-001"
    result = json.loads((canonical / "result.json").read_text(encoding="utf-8"))
    provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8"))
    monitor = json.loads((canonical / "resource_monitor.json").read_text(encoding="utf-8"))
    checks = {
        "optimal": result.get("solver_status") == "OPTIMAL", "exact": result.get("exact_certification") is True,
        "cut_validity": result.get("cut_validity") is True, "result_hash": sha256(canonical / "result.json") == provenance.get("result_sha256"),
        "trajectory_hash": sha256(canonical / "iteration_trajectory.json") == provenance.get("trajectory_sha256"),
        "resource_clean": monitor.get("stop_reason") is None and monitor.get("worker_return_code") == 0,
        "canonical_attempt_match": all(sha256(path) == sha256(attempt / path.name) for path in canonical.iterdir() if path.is_file()),
    }
    if not all(checks.values()):
        raise RuntimeError(f"INTEGRITY_FAILURE {condition_id}: {checks}")
    return checks


def execute_batch(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: EF-BD remaining-nine batch remains disabled")
    initial = build_dry_run(config_path)
    if initial["decision"] != "AUTHORIZED_READY":
        raise RuntimeError(f"BATCH_PREFLIGHT_BLOCKED: {initial['gates']}")
    report_path = ROOT / config["output_directory"] / "batch_reports" / f"{config['protocol_id']}.json"
    report = {"protocol_id": config["protocol_id"], "fixed_denominator": 9, "status": "RUNNING", "records": []}
    write_json(report_path, report)
    for condition_id in EXPECTED:
        preflight = runner.validate_execution_gate(config_path, condition_id)
        frozen = config["frozen_input_identity"][condition_id]
        if not all(preflight[key] == frozen[key] for key in ("instance_sha256", "preparation_sha256", "instance_hash", "x0_hash")):
            raise RuntimeError(f"IDENTITY_FAILURE: {condition_id}")
        if not git_status_for_execution(ROOT / config["output_directory"])["clean_for_execution"] or active_solver_workers():
            raise RuntimeError(f"INTEGRITY_FAILURE before {condition_id}")
        monitor = runner.run_condition(config_path, condition_id)
        stop = monitor["stop_reason"]
        if monitor["worker_return_code"] == 0 and stop is None:
            verify_success(config, condition_id)
            classification = "SUCCESS"
        elif stop in config["failure_policy"]["continue_after"] and not active_solver_workers():
            classification = "RESOURCE_OR_TIME_FAILURE"
        else:
            classification = "INTEGRITY_FAILURE"
        report["records"].append({"condition_id": condition_id, "attempt": "attempt-001", "classification": classification, "stop_reason": stop, "worker_return_code": monitor["worker_return_code"], "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"], "preflight": preflight})
        report["status"] = "STOPPED_INTEGRITY_FAILURE" if classification == "INTEGRITY_FAILURE" else "RUNNING"
        write_json(report_path, report)
        if classification == "INTEGRITY_FAILURE":
            raise RuntimeError(f"INTEGRITY_FAILURE stops batch: {condition_id}")
    report["status"] = "COMPLETE"
    write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = execute_batch(args.config.resolve()) if args.execute else build_dry_run(args.config.resolve())
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
