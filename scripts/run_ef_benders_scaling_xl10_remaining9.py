from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_ef_benders_scaling as runner
from scripts.run_ef_benders_scaling_xl10_pilot import active_solver_workers


DEFAULT_CONFIG = ROOT / "experiments/configs/development/ef_benders_scaling_xl10_remaining9_v1.yaml"
PILOT_CONFIG = ROOT / "experiments/configs/development/ef_benders_scaling_xl10_pilot_v1.yaml"
PILOT_ROOT = ROOT / "experiments/results/ef_benders_scaling_xl10_pilot_v1"
L10_ROOT = ROOT / "experiments/results/ef_benders_scaling_development_v1"
EXPECTED = [f"EF_XL10_S{seed}" for seed in range(20260922, 20260931)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def pilot_audit() -> dict:
    condition_id = "EF_XL10_S20260921"
    attempt = PILOT_ROOT / "worker_logs" / condition_id / "attempt-001"
    canonical = PILOT_ROOT / "runs" / condition_id
    required = {
        "result.json", "provenance.json", "iteration_trajectory.json",
        "first_stage_solution.json", "resource_monitor.json", "outcome.json",
        "oracle_trace.jsonl", "solver.log", "stdout.log", "stderr.log",
    }
    attempt_files = {path.name for path in attempt.iterdir() if path.is_file()} if attempt.is_dir() else set()
    canonical_files = {path.name for path in canonical.iterdir() if path.is_file()} if canonical.is_dir() else set()
    result = json.loads((canonical / "result.json").read_text(encoding="utf-8")) if required <= canonical_files else {}
    provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8")) if required <= canonical_files else {}
    monitor = json.loads((canonical / "resource_monitor.json").read_text(encoding="utf-8")) if required <= canonical_files else {}
    outcome = json.loads((canonical / "outcome.json").read_text(encoding="utf-8")) if required <= canonical_files else {}
    pilot_config_sha = sha256(PILOT_CONFIG)
    pilot_config_identity = runner.direct_runner.canonical_hash(json.loads(PILOT_CONFIG.read_text(encoding="utf-8")))
    byte_checks = {
        name: sha256(attempt / name) == sha256(canonical / name)
        for name in sorted(required)
        if (attempt / name).is_file() and (canonical / name).is_file()
    }
    checks = {
        "complete_file_sets": required <= attempt_files and required <= canonical_files and attempt_files == canonical_files,
        "attempt_canonical_bytes": len(byte_checks) == len(required) and all(byte_checks.values()),
        "optimal": result.get("solver_status") == "OPTIMAL",
        "exact_certification": result.get("exact_certification") is True,
        "cut_validity": result.get("cut_validity") is True,
        "condition_identity": result.get("condition_id") == condition_id and result.get("attempt") == "attempt-001",
        "instance_hash": result.get("instance_hash") == "73732c6523ff154f1e5e7891641c25102345bc40c65bfb72630c817c78349695",
        "x0_hash": provenance.get("x0_hash") == "89d558ca9bee95e37b1e58408873847a450f1a2dc8b08a42e9b2e09d616d43c3",
        "config_sha256": provenance.get("config_sha256") == pilot_config_sha,
        "config_identity": result.get("config_hash") == pilot_config_identity == provenance.get("config_hash"),
        "result_hash": provenance.get("result_sha256") == sha256(canonical / "result.json"),
        "trajectory_hash": provenance.get("trajectory_sha256") == sha256(canonical / "iteration_trajectory.json"),
        "first_stage_hash": provenance.get("first_stage_sha256") == sha256(canonical / "first_stage_solution.json"),
        "resource_clean": monitor.get("stop_reason") is None and monitor.get("worker_return_code") == 0,
        "outcome_success": outcome.get("status") == "SUCCESS" and outcome.get("worker_return_code") == 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"PILOT_ACCEPTANCE_FAILURE: {checks}")
    engineering = result["oracle_engineering"]
    accounted_core = engineering["oracle_build_seconds"] + result["oracle_time"] + result["master_time"]
    return {
        "condition_id": condition_id,
        "attempt": "attempt-001",
        "checks": checks,
        "file_sha256": {name: sha256(canonical / name) for name in sorted(required)},
        "result": result,
        "provenance": provenance,
        "resource_monitor": monitor,
        "timing_accounting": {
            "algorithm_core_time_seconds": result["algorithm_core_time"],
            "oracle_build_seconds_in_core": engineering["oracle_build_seconds"],
            "oracle_optimize_seconds_in_core": result["oracle_time"],
            "master_optimize_seconds_in_core": result["master_time"],
            "other_core_seconds": result["algorithm_core_time"] - accounted_core,
            "independent_certification_seconds_outside_core": result["certification_time"],
            "total_time_seconds": result["total_time"],
        },
    }


def git_status_for_execution(output: Path) -> dict:
    entries = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True
    ).splitlines()
    allowed = (
        output.resolve().relative_to(ROOT.resolve()).as_posix() + "/",
        PILOT_ROOT.resolve().relative_to(ROOT.resolve()).as_posix() + "/",
        L10_ROOT.resolve().relative_to(ROOT.resolve()).as_posix() + "/",
        "experiments/results/basic_benders_scaling_development_v1/",
        "artifacts/ef_benders_scaling_xl10_remaining9_readiness_audit.json",
    )
    unexpected = [line for line in entries if not line[3:].replace("\\", "/").startswith(allowed)]
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "clean_for_execution": not unexpected,
        "unexpected": unexpected,
    }


def validate_protocol(config: dict) -> None:
    resource = config["resource_policy"]
    checks = {
        "protocol": config.get("protocol_id") == "EF_BD_XL10_REMAINING9_V1",
        "scope": config.get("authorized_condition_ids") == EXPECTED,
        "authorization_boolean": isinstance(config.get("formal_run_authorized"), bool),
        "dimensions": config.get("sizes") == [{"label": "XL10", "I": 30, "R": 30, "J": 14}],
        "science": config.get("fixed_scientific_parameters") == {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "SL": 0.90, "phi_multiplier": 1.85},
        "solver": config.get("solver_parameters") == {"Threads": 2},
        "resource": (
            resource["maximum_process_tree_memory_gib_by_size"] == {"XL10": 8}
            and resource["minimum_available_memory_gib_by_size"] == {"XL10": 12}
            and resource["minimum_system_available_memory_gib"] == 3
            and resource["condition_time_limit_seconds"] == 900
            and resource["minimum_free_disk_gib"] == 20
            and resource["memory_monitor_interval_seconds"] == 0.25
            and resource["parallel_workers"] == 1
            and resource["retry_policy"] == "no_automatic_retry"
        ),
        "failure_policy": resource["fail_closed"] is True and config["failure_policy"]["require_worker_exit_before_continue"] is True,
        "denominator": len(config.get("frozen_input_identity", {})) == 9,
    }
    if not all(checks.values()):
        raise RuntimeError(f"EF-BD XL10 remaining-nine protocol mismatch: {checks}")


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
        row.update({
            "attempt_exists": (output / "worker_logs" / condition_id / "attempt-001").exists(),
            "expected_attempt": "attempt-001",
            "identity_checks": identity,
            "identity_status": "PASS" if all(identity.values()) and all(row["paired_instance_identity"].values()) else "FAIL",
        })
        conditions.append(row)
    environment = conditions[0]["environment"]
    required_environment = config["required_environment"]
    environment_checks = {
        "python_version": environment["python_version"] == required_environment["python_version"],
        "gurobipy_version": environment["gurobipy_version"] == required_environment["gurobipy_version"],
        "gurobi_native_version": environment["gurobi_native_version"] == required_environment["gurobi_native_version"],
    }
    current_model_files = runner.model_identity()["files"]
    algorithm_checks = {
        path: current_model_files.get(path) == expected
        for path, expected in config["frozen_algorithm_files"].items()
    }
    resources = conditions[0]["resource_gate"]
    git = git_status_for_execution(output)
    active = active_solver_workers()
    gates = {
        "pilot_accepted": all(pilot["checks"].values()),
        "frozen_algorithm": all(algorithm_checks.values()),
        "environment": all(environment_checks.values()),
        "all_nine_identities": all(row["identity_status"] == "PASS" for row in conditions),
        "all_attempts_absent": all(not row["attempt_exists"] for row in conditions),
        "all_canonical_absent": all(not row["canonical_result_exists"] for row in conditions),
        "startup_memory": resources["available_memory_gib"] >= 12,
        "disk": resources["free_disk_gib"] >= 20,
        "git_identity": git["clean_for_execution"],
        "no_active_solver_worker": not active,
    }
    ready = all(gates.values())
    decision = ("AUTHORIZED_READY" if config["formal_run_authorized"] else "READY_FOR_AUTHORIZATION") if ready else "BLOCKED"
    return {
        "schema": "ef_benders_xl10_remaining9_dry_run_v1",
        "protocol_id": config["protocol_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "fixed_denominator_remaining": 9,
        "fixed_denominator_total_xl10": 10,
        "conditions": conditions,
        "pilot": pilot,
        "environment_checks": environment_checks,
        "algorithm_identity_checks": algorithm_checks,
        "resource_policy": config["resource_policy"],
        "failure_policy": config["failure_policy"],
        "git": git,
        "active_solver_workers": active,
        "gates": gates,
        "decision": decision,
        "optimization_calls": 0,
    }


def verify_success(config: dict, condition_id: str) -> dict:
    output = ROOT / config["output_directory"]
    attempt = output / "worker_logs" / condition_id / "attempt-001"
    canonical = output / "runs" / condition_id
    required = ("result.json", "provenance.json", "iteration_trajectory.json", "first_stage_solution.json", "resource_monitor.json", "outcome.json")
    if not all((attempt / name).is_file() and (canonical / name).is_file() for name in required):
        raise RuntimeError(f"ARCHIVE_FAILURE {condition_id}")
    result = json.loads((canonical / "result.json").read_text(encoding="utf-8"))
    provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8"))
    monitor = json.loads((canonical / "resource_monitor.json").read_text(encoding="utf-8"))
    checks = {
        "optimal": result.get("solver_status") == "OPTIMAL",
        "exact": result.get("exact_certification") is True,
        "cut_validity": result.get("cut_validity") is True,
        "result_hash": sha256(canonical / "result.json") == provenance.get("result_sha256"),
        "trajectory_hash": sha256(canonical / "iteration_trajectory.json") == provenance.get("trajectory_sha256"),
        "first_stage_hash": sha256(canonical / "first_stage_solution.json") == provenance.get("first_stage_sha256"),
        "resource_clean": monitor.get("stop_reason") is None and monitor.get("worker_return_code") == 0,
        "canonical_attempt_match": all(sha256(canonical / name) == sha256(attempt / name) for name in required),
    }
    if not all(checks.values()):
        raise RuntimeError(f"INTEGRITY_FAILURE {condition_id}: {checks}")
    return checks


def classify_monitor(config: dict, condition_id: str, monitor: dict, workers: list[dict] | None = None) -> str:
    if monitor.get("worker_return_code") == 0 and monitor.get("stop_reason") is None:
        verify_success(config, condition_id)
        return "SUCCESS"
    active = active_solver_workers() if workers is None else workers
    if monitor.get("stop_reason") in config["failure_policy"]["continue_after"] and not active:
        return "RESOURCE_OR_TIME_FAILURE"
    return "INTEGRITY_FAILURE"


def execute_batch(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: EF-BD XL10 remaining-nine batch remains disabled")
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
        classification = classify_monitor(config, condition_id, monitor)
        report["records"].append({
            "condition_id": condition_id,
            "attempt": "attempt-001",
            "classification": classification,
            "stop_reason": monitor.get("stop_reason"),
            "worker_return_code": monitor.get("worker_return_code"),
            "peak_process_tree_memory_gib": monitor.get("peak_process_tree_memory_gib"),
            "preflight": preflight,
        })
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
