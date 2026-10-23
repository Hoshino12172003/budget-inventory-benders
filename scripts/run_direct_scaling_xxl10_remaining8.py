from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_direct_scaling_xxl10_remaining9 as base


runner = base.runner
DEFAULT_CONFIG = ROOT / "experiments/configs/development/direct_scaling_xxl10_remaining8_v1.yaml"
REFERENCE_CONFIG = base.DEFAULT_CONFIG
HISTORICAL_ROOT = ROOT / "experiments/results/direct_scaling_xxl10_remaining9_v1"
EXPECTED = [f"DIRECT_XXL10_S{seed}" for seed in range(20260923, 20260931)]
PROTOCOL_ID = "DIRECT_XXL10_REMAINING8_RECOVERY_V1_METHOD2_THREADS2"
AUDIT_PATH = "artifacts/direct_scaling_xxl10_remaining8_readiness_audit.json"
CORE_SHA256 = base.CORE_SHA256
HISTORICAL_SHA256 = {
    "batch_reports/DIRECT_XXL10_REMAINING9_V1_METHOD2_THREADS2.json": "47206b4790f12666ba536ccdd7ab56906dfdf24669eb6a838ebbd07bf01ca1c8",
    "runs/DIRECT_XXL10_S20260922/provenance.json": "19a3279b422582c60b9b18871ccadf9cc8267560c0b364f303931ed98d38d066",
    "runs/DIRECT_XXL10_S20260922/result.json": "68cfaf2858ef997dc19c380eeec2df05f40ea3f45a477339c80595f25c0e28fb",
    "runs/DIRECT_XXL10_S20260922/solver.log": "56aa1118100975945dfcd72394005ec6c43b245b5b0d862f82c787d93dc81746",
    "runs/DIRECT_XXL10_S20260922/solver_progress.json": "c0e82056b914a1219b5f9dc1f8fa8f8b96b7593beca2e599dd44a65ba6df2954",
    "worker_logs/DIRECT_XXL10_S20260922/attempt-001/resource_monitor.json": "2c2caebd9740dc56687de14a56555a57f8ac79418d21e59e93cb1d23feae8778",
    "worker_logs/DIRECT_XXL10_S20260922/attempt-001/stderr.log": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "worker_logs/DIRECT_XXL10_S20260922/attempt-001/stdout.log": "e2091a472b586d488765d32880d10982c05d7cc1dbbf2d3d58c49e7acdcf37bf",
}


def validate_protocol(config: dict) -> None:
    reference = runner.load_config(REFERENCE_CONFIG)
    policy = config["resource_policy"]
    checks = {
        "protocol": config.get("resource_protocol_id") == PROTOCOL_ID,
        "scope": config.get("authorized_condition_ids") == EXPECTED,
        "authorization_boolean": isinstance(config.get("formal_run_authorized"), bool),
        "dimensions": config.get("sizes") == [{"label": "XXL10", "I": 36, "R": 36, "J": 16}],
        "science": config.get("fixed_scientific_parameters") == reference.get("fixed_scientific_parameters"),
        "solver_profile": config.get("solver_profile") == reference.get("solver_profile"),
        "solver_parameters": config.get("solver_parameters") == reference.get("solver_parameters"),
        "model_files": config.get("frozen_model_files") == reference.get("frozen_model_files"),
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
        "denominator": len(config.get("frozen_input_identity", {})) == 8,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Direct XXL10 remaining-eight protocol mismatch: {checks}")


def historical_seed22_audit() -> dict:
    paths = {name: HISTORICAL_ROOT / name for name in HISTORICAL_SHA256}
    actual = {name: base.sha256(path) if path.is_file() else None for name, path in paths.items()}
    result = json.loads(paths["runs/DIRECT_XXL10_S20260922/result.json"].read_text(encoding="utf-8"))
    provenance = json.loads(paths["runs/DIRECT_XXL10_S20260922/provenance.json"].read_text(encoding="utf-8"))
    monitor = json.loads(paths["worker_logs/DIRECT_XXL10_S20260922/attempt-001/resource_monitor.json"].read_text(encoding="utf-8"))
    report = json.loads(paths["batch_reports/DIRECT_XXL10_REMAINING9_V1_METHOD2_THREADS2.json"].read_text(encoding="utf-8"))
    log = paths["runs/DIRECT_XXL10_S20260922/solver.log"].read_text(encoding="utf-8", errors="replace")
    checks = {
        "hashes_unchanged": actual == HISTORICAL_SHA256,
        "solver_status": result.get("solver_status") == "TIME_LIMIT",
        "no_incumbent_fields": all(result.get(key) is None for key in ("objective", "best_bound", "mip_gap")),
        "not_certified": result.get("exact_certification") is False and result.get("certification_status") == "NOT_ATTEMPTED",
        "worker_clean": monitor.get("worker_return_code") == 0 and monitor.get("stop_reason") is None,
        "archive_complete": provenance.get("archive_complete") is True,
        "result_hash": provenance.get("result_sha256") == actual["runs/DIRECT_XXL10_S20260922/result.json"],
        "log_hash": provenance.get("solver_log_sha256") == actual["runs/DIRECT_XXL10_S20260922/solver.log"],
        "log_solution_count_zero": "Solution count 0" in log,
        "log_time_limit": "Time limit reached" in log,
        "historical_report_preserved": report.get("status") == "STOPPED_INTEGRITY_FAILURE",
        "posthoc_classification": base.classify_completed_result(result, monitor) == "TIME_LIMIT_NO_INCUMBENT",
    }
    if not all(checks.values()):
        raise RuntimeError(f"Historical seed-20260922 acceptance failed: {checks}")
    return {
        "condition_id": "DIRECT_XXL10_S20260922",
        "historical_batch_status": report["status"],
        "historical_classification": "INTEGRITY_FAILURE",
        "posthoc_classification": "TIME_LIMIT_NO_INCUMBENT",
        "checks": checks,
        "result": result,
        "monitor": monitor,
        "file_sha256": actual,
    }


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    history = historical_seed22_audit()
    output = (ROOT / config["output_directory"]).resolve()
    conditions = [base.condition_audit(config, row, output) for row in runner.authorized_conditions(config)]
    model = runner.model_identity()
    environment = runner.validate_environment(config)
    available = base.psutil.virtual_memory().available / 2**30
    free_disk = base.shutil.disk_usage(output.parent).free / 2**30
    git = base.git_status_for_execution(output)
    workers = base.active_solver_workers(exclude_pid=os.getpid())
    gates = {
        "historical_seed22": all(history["checks"].values()),
        "all_eight_identities": all(all(row["identity_checks"].values()) for row in conditions),
        "all_eight_paired": all(all(row["paired_identity_checks"].values()) for row in conditions),
        "all_attempts_absent": all(row["attempt_state_valid"] for row in conditions),
        "all_canonical_absent": all(row["canonical_absent"] for row in conditions),
        "model": model["files"] == config["frozen_model_files"],
        "environment": environment["pass"],
        "git": git["clean_for_execution"],
        "startup_memory": available >= 16,
        "disk": free_disk >= 20,
        "no_other_worker": not workers,
    }
    nonresource = all(value for name, value in gates.items() if name != "startup_memory")
    if all(gates.values()):
        decision = "AUTHORIZED_READY" if config["formal_run_authorized"] else "READY_FOR_AUTHORIZATION"
    elif nonresource and not gates["startup_memory"]:
        decision = "RESOURCE_BLOCKED"
    else:
        decision = "BLOCKED"
    return {
        "schema": "direct_xxl10_remaining8_recovery_dry_run_v1",
        "decision": decision,
        "formal_run_authorized": config["formal_run_authorized"],
        "protocol_id": PROTOCOL_ID,
        "fixed_denominator": 8,
        "conditions": conditions,
        "historical_seed22": history,
        "model_identity": model,
        "environment": environment,
        "resource_policy": config["resource_policy"],
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
        "git": git,
        "active_workers": workers,
        "gates": gates,
        "config_sha256": base.sha256(config_path.resolve()),
        "config_identity": runner.canonical_hash(config),
        "optimization_calls": 0,
    }


def live_gates(config_path: Path, condition_id: str, *, expect_worker_started: bool, require_authorization: bool) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    state = base.live_gates(
        config_path,
        condition_id,
        expect_worker_started=expect_worker_started,
        require_authorization=require_authorization,
    )
    state["historical_seed22"] = historical_seed22_audit()
    state["gates"]["historical_seed22"] = all(state["historical_seed22"]["checks"].values())
    state["pass"] = all(state["gates"].values())
    return state


def worker_solve(config_path: Path, output_root: Path, condition_id: str) -> None:
    config = runner.load_config(config_path)
    validate_protocol({**config, "formal_run_authorized": False})
    configured_output = (ROOT / config["output_directory"]).resolve()
    if output_root.resolve() != configured_output:
        raise RuntimeError("DIRECT_OUTPUT_ROOT_MISMATCH")
    state = live_gates(config_path, condition_id, expect_worker_started=True, require_authorization=True)
    if not state["pass"]:
        raise RuntimeError(f"DIRECT_XXL10_REMAINING8_WORKER_BLOCKED: {state['gates']}")
    condition = next(row for row in runner.authorized_conditions(config) if row["condition_id"] == condition_id)
    original = runner.validate_execution_gate
    try:
        runner.validate_execution_gate = lambda *_args: state["resource_gate"]
        runner.solve_condition(config, condition, configured_output)
    finally:
        runner.validate_execution_gate = original


def run_one(config_path: Path, config: dict, condition: dict, output: Path) -> None:
    state = live_gates(config_path, condition["condition_id"], expect_worker_started=False, require_authorization=True)
    if not state["pass"]:
        raise RuntimeError(f"DIRECT_XXL10_REMAINING8_PREFLIGHT_BLOCKED: {state['gates']}")
    original_gate, original_file = runner.validate_execution_gate, runner.__file__
    try:
        runner.validate_execution_gate = lambda *_args: state["resource_gate"]
        runner.__file__ = __file__
        runner.run_monitored(config_path, config, condition, output)
    finally:
        runner.validate_execution_gate, runner.__file__ = original_gate, original_file


def execute_batch(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("FORMAL_DIRECT_EXECUTION_NOT_AUTHORIZED")
    initial = build_dry_run(config_path)
    if initial["decision"] != "AUTHORIZED_READY":
        raise RuntimeError(f"DIRECT_XXL10_REMAINING8_BLOCKED: {initial['gates']}")
    output = (ROOT / config["output_directory"]).resolve()
    report_path = output / "batch_reports" / f"{PROTOCOL_ID}.json"
    records = [{"condition_id": value, "attempt": "attempt-001", "classification": "NOT_RUN"} for value in EXPECTED]
    report = {"protocol_id": PROTOCOL_ID, "fixed_denominator": 8, "status": "RUNNING", "records": records}
    base.write_json(report_path, report)
    for index, condition in enumerate(runner.authorized_conditions(config)):
        error = None
        try:
            run_one(config_path, config, condition, output)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        if base.active_solver_workers():
            raise RuntimeError("INTEGRITY_FAILURE: worker did not exit")
        row = base.classify_condition(config, condition, output)
        if error:
            row["detail"] = error
        records[index] = row
        report["status"] = "STOPPED_INTEGRITY_FAILURE" if row["classification"] == "INTEGRITY_FAILURE" else "RUNNING"
        base.write_json(report_path, report)
        if row["classification"] == "INTEGRITY_FAILURE":
            raise RuntimeError(f"INTEGRITY_FAILURE stops batch: {row}")
    report["status"] = "COMPLETE"
    base.write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", metavar="CONDITION_ID", help=argparse.SUPPRESS)
    parser.add_argument("--worker-preflight", metavar="CONDITION_ID")
    parser.add_argument("--output-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    config_path = args.config.resolve()
    if args.worker:
        worker_solve(config_path, args.output_root.resolve(), args.worker)
        result = None
    elif args.worker_preflight:
        result = live_gates(config_path, args.worker_preflight, expect_worker_started=False, require_authorization=False)
    elif args.execute:
        result = execute_batch(config_path)
    else:
        result = build_dry_run(config_path)
    if result is not None:
        print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
