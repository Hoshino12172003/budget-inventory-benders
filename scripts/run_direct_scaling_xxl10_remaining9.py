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


DEFAULT_CONFIG = ROOT / "experiments/configs/development/direct_scaling_xxl10_remaining9_v1.yaml"
PILOT_CONFIG = ROOT / "experiments/configs/development/direct_scaling_xxl10_paired_pilot_v1.yaml"
PILOT_ROOT = ROOT / "experiments/results/direct_scaling_xxl10_paired_pilot_v1"
EXPECTED = [f"DIRECT_XXL10_S{seed}" for seed in range(20260922, 20260931)]
PROTOCOL_ID = "DIRECT_XXL10_REMAINING9_V1_METHOD2_THREADS2"
CORE_SHA256 = "fef8019f9aa9be1d2942a5d3aad363c2c3c28929e52cc02b359d1626a1880edd"
AUDIT_PATH = "artifacts/direct_scaling_xxl10_remaining9_readiness_audit.json"
HISTORICAL_PREFIXES = (
    "experiments/results/basic_benders_scaling_development_v1/",
    "experiments/results/direct_scaling_xxl10_paired_pilot_v1/",
    "experiments/results/ef_benders_scaling_development_v1/",
    "experiments/results/ef_benders_scaling_xl10_pilot_v1/",
    "experiments/results/ef_benders_scaling_xl10_remaining9_v1/",
    "experiments/results/ef_benders_scaling_xxl10_paired_pilot_v1/",
    "experiments/results/ef_benders_scaling_xxl10_remaining9_v1/",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def active_solver_workers(*, exclude_pid: int | None = None) -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if process.info["pid"] == exclude_pid:
                continue
            name = (process.info.get("name") or "").lower()
            command = " ".join(process.info.get("cmdline") or []).lower()
            worker = name.startswith("python") and "--worker" in command and any(
                script in command for script in ("run_direct_scaling.py", "run_direct_scaling_xxl10_remaining9.py")
            )
            if name.startswith("gurobi") or worker:
                found.append({"pid": process.info["pid"], "name": name, "cmdline": process.info.get("cmdline") or []})
        except psutil.Error:
            continue
    return found


def git_status_for_execution(output: Path) -> dict:
    entries = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True
    ).splitlines()
    output_prefix = output.resolve().relative_to(ROOT.resolve()).as_posix() + "/"
    unexpected = unexpected_git_entries(entries, output)
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "clean_for_execution": not unexpected,
        "unexpected": unexpected,
    }


def unexpected_git_entries(entries: list[str], output: Path) -> list[str]:
    output_prefix = output.resolve().relative_to(ROOT.resolve()).as_posix() + "/"
    unexpected = []
    for line in entries:
        path = line[3:].replace("\\", "/")
        if path == AUDIT_PATH or path.startswith((output_prefix, *HISTORICAL_PREFIXES)):
            continue
        unexpected.append(line)
    return unexpected


def validate_protocol(config: dict) -> None:
    policy = config["resource_policy"]
    pilot = runner.load_config(PILOT_CONFIG)
    checks = {
        "protocol": config.get("resource_protocol_id") == PROTOCOL_ID,
        "scope": config.get("authorized_condition_ids") == EXPECTED,
        "authorization_boolean": isinstance(config.get("formal_run_authorized"), bool),
        "dimensions": config.get("sizes") == [{"label": "XXL10", "I": 36, "R": 36, "J": 16}],
        "science": config.get("fixed_scientific_parameters") == pilot.get("fixed_scientific_parameters"),
        "solver_profile": config.get("solver_profile") == pilot.get("solver_profile"),
        "solver_parameters": config.get("solver_parameters") == pilot.get("solver_parameters"),
        "model_files": config.get("frozen_model_files") == pilot.get("frozen_model_files"),
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
        "denominator": len(config.get("frozen_input_identity", {})) == 9,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Direct XXL10 remaining-nine protocol mismatch: {checks}")


def pilot_audit() -> dict:
    condition = "DIRECT_XXL10_S20260921"
    attempt_1 = PILOT_ROOT / "worker_logs" / condition / "attempt-001"
    attempt_2 = PILOT_ROOT / "worker_logs" / condition / "attempt-002"
    canonical = PILOT_ROOT / "runs" / condition
    result_path = canonical / "result.json"
    provenance_path = canonical / "provenance.json"
    monitor_1 = json.loads((attempt_1 / "resource_monitor.json").read_text(encoding="utf-8"))
    monitor_2 = json.loads((attempt_2 / "resource_monitor.json").read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    required_attempt = {"stdout.log", "stderr.log", "resource_monitor.json"}
    required_canonical = {"result.json", "provenance.json", "first_stage_solution.json", "solver.log", "solver_progress.json"}
    pilot_config = runner.load_config(PILOT_CONFIG)
    checks = {
        "attempt_001_complete": {path.name for path in attempt_1.iterdir() if path.is_file()} == required_attempt,
        "attempt_001_known_gate_failure": monitor_1.get("worker_return_code") == 1 and monitor_1.get("stop_reason") is None and "formal Direct execution found changes outside its output root" in (attempt_1 / "stderr.log").read_text(encoding="utf-8"),
        "attempt_002_complete": {path.name for path in attempt_2.iterdir() if path.is_file()} == required_attempt,
        "canonical_complete": required_canonical == {path.name for path in canonical.iterdir() if path.is_file()},
        "attempt_002_monitor": monitor_2.get("attempt") == "attempt-002" and monitor_2.get("worker_return_code") == 0 and monitor_2.get("stop_reason") is None,
        "time_limit": result.get("solver_status") == "TIME_LIMIT",
        "not_certified": result.get("exact_certification") is False and result.get("certification_status") == "NOT_ATTEMPTED",
        "feasible_progress": all(result.get(key) is not None for key in ("objective", "best_bound", "mip_gap")),
        "identity": result.get("condition_id") == condition and result.get("instance_hash") == pilot_config["frozen_input_identity"]["instance_hash"],
        "config": result.get("config_hash") == runner.canonical_hash(pilot_config),
        "model": provenance.get("model_identity", {}).get("files") == pilot_config["frozen_model_files"],
        "result_hash": provenance.get("result_sha256") == sha256(result_path),
        "first_stage_hash": provenance.get("first_stage_solution_sha256") == sha256(canonical / "first_stage_solution.json"),
        "solver_log_hash": provenance.get("solver_log_sha256") == sha256(canonical / "solver.log"),
        "progress_hash": provenance.get("solver_progress_sha256") == sha256(canonical / "solver_progress.json"),
        "archive_complete": provenance.get("archive_complete") is True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Direct XXL10 pilot acceptance failed: {checks}")
    paths = [*(attempt_1 / name for name in sorted(required_attempt)), *(attempt_2 / name for name in sorted(required_attempt)), *(canonical / name for name in sorted(required_canonical))]
    return {
        "condition_id": condition,
        "checks": checks,
        "result": result,
        "attempt_001_monitor": monitor_1,
        "attempt_002_monitor": monitor_2,
        "file_sha256": {path.relative_to(PILOT_ROOT).as_posix(): sha256(path) for path in paths},
    }


def paired_identity(seed: int, instance_hash: str) -> dict:
    checks = {}
    paths = {
        "EF_BD": ROOT / f"experiments/results/ef_benders_scaling_xxl10_remaining9_v1/runs/EF_XXL10_S{seed}/result.json",
        "AGGREGATE_BD": ROOT / f"experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard/runs/ASC_XXL10_S{seed}_AGGREGATE_BENDERS_STRUCTURED_ORACLE/result.json",
        "PRB_BD": ROOT / f"experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard/runs/ASC_XXL10_S{seed}_PRB_BENDERS/result.json",
    }
    for method, path in paths.items():
        checks[method] = path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("instance_hash") == instance_hash
    return checks


def baseline_archive_audit() -> dict:
    records = []
    for seed in range(20260921, 20260931):
        paths = {
            "EF_BD": ROOT / (
                f"experiments/results/ef_benders_scaling_xxl10_paired_pilot_v1/runs/EF_XXL10_S{seed}/result.json"
                if seed == 20260921 else
                f"experiments/results/ef_benders_scaling_xxl10_remaining9_v1/runs/EF_XXL10_S{seed}/result.json"
            ),
            "AGGREGATE_BD": ROOT / f"experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard/runs/ASC_XXL10_S{seed}_AGGREGATE_BENDERS_STRUCTURED_ORACLE/result.json",
            "PRB_BD": ROOT / f"experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard/runs/ASC_XXL10_S{seed}_PRB_BENDERS/result.json",
        }
        for method, path in paths.items():
            row = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            exact = row.get("exact_certification") is True
            cut = row.get("cut_validity", True) is True
            records.append({
                "method": method, "seed": seed, "path": path.relative_to(ROOT).as_posix(),
                "exists": path.is_file(), "exact_certification": exact, "cut_validity": cut,
                "instance_hash": row.get("instance_hash"), "sha256": sha256(path) if path.is_file() else None,
                "pass": path.is_file() and exact and cut,
            })
    return {"records": records, "pass": len(records) == 30 and all(row["pass"] for row in records)}


def condition_audit(config: dict, condition: dict, output: Path, *, expect_worker_started: bool = False) -> dict:
    instance, preparation, hashes = runner.verified_input(config, condition)
    frozen = config["frozen_input_identity"][condition["condition_id"]]
    identity = {
        "condition": condition["condition_id"] in EXPECTED,
        "dimensions": (instance.num_depots, instance.num_regions, instance.num_products) == (36, 36, 16),
        "instance_sha256": hashes["instance_sha256"] == frozen["instance_sha256"],
        "preparation_sha256": hashes["preparation_sha256"] == frozen["preparation_sha256"],
        "instance_hash": preparation["instance_hash"] == frozen["instance_hash"],
        "x0_hash": preparation["x0_hash"] == frozen["x0_hash"],
    }
    attempt = output / "worker_logs" / condition["condition_id"] / "attempt-001"
    if expect_worker_started:
        attempt_state = attempt.is_dir() and {path.name for path in attempt.iterdir()} <= {"stdout.log", "stderr.log"}
    else:
        attempt_state = not attempt.exists()
    paired = paired_identity(condition["seed"], preparation["instance_hash"])
    return {
        "condition_id": condition["condition_id"], "seed": condition["seed"],
        "identity_checks": identity, "paired_identity_checks": paired,
        "attempt_state_valid": attempt_state,
        "canonical_absent": not (output / "runs" / condition["condition_id"]).exists(),
        "next_attempt": "attempt-001", **hashes,
        "instance_hash": preparation["instance_hash"], "x0_hash": preparation["x0_hash"],
    }


def live_gates(config_path: Path, condition_id: str, *, expect_worker_started: bool, require_authorization: bool) -> dict:
    config = runner.load_config(config_path)
    if require_authorization and config.get("formal_run_authorized") is not True:
        raise RuntimeError("FORMAL_DIRECT_EXECUTION_NOT_AUTHORIZED")
    condition = next((row for row in runner.authorized_conditions(config) if row["condition_id"] == condition_id), None)
    if condition is None:
        raise RuntimeError(f"DIRECT_CONDITION_NOT_AUTHORIZED: {condition_id}")
    output = (ROOT / config["output_directory"]).resolve()
    row = condition_audit(config, condition, output, expect_worker_started=expect_worker_started)
    model = runner.model_identity()
    environment = runner.validate_environment(config)
    policy = config["resource_policy"]
    available = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output.parent).free / 2**30
    git = git_status_for_execution(output)
    workers = active_solver_workers(exclude_pid=os.getpid())
    gates = {
        "identity": all(row["identity_checks"].values()),
        "paired_identity": all(row["paired_identity_checks"].values()),
        "attempt": row["attempt_state_valid"],
        "canonical_absent": row["canonical_absent"],
        "model": model["files"] == config["frozen_model_files"],
        "environment": environment["pass"],
        "git": git["clean_for_execution"],
        "startup_memory": available >= policy["minimum_available_memory_gib_by_size"]["XXL10"],
        "disk": free_disk >= policy["minimum_free_disk_gib"],
        "no_other_worker": not workers,
    }
    return {
        "pass": all(gates.values()), "gates": gates, "condition": row,
        "model_identity": model, "environment": environment, "git": git,
        "active_workers": workers,
        "resource_gate": {
            "available_memory_gib": available, "startup_required_gib": 16,
            "process_tree_cap_gib": 13, "system_available_floor_gib": 3,
            "free_disk_gib": free_disk, "minimum_free_disk_gib": 20,
            "time_limit_seconds": 900, "monitor_interval_seconds": 0.25,
        },
        "optimization_calls": 0,
    }


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    pilot = pilot_audit()
    baselines = baseline_archive_audit()
    output = (ROOT / config["output_directory"]).resolve()
    conditions = [condition_audit(config, row, output) for row in runner.authorized_conditions(config)]
    model = runner.model_identity()
    environment = runner.validate_environment(config)
    policy = config["resource_policy"]
    available = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output.parent).free / 2**30
    git = git_status_for_execution(output)
    workers = active_solver_workers(exclude_pid=os.getpid())
    gates = {
        "pilot_accepted": all(pilot["checks"].values()),
        "baseline_archives": baselines["pass"],
        "all_nine_identities": all(all(row["identity_checks"].values()) for row in conditions),
        "all_nine_paired": all(all(row["paired_identity_checks"].values()) for row in conditions),
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
        "schema": "direct_xxl10_remaining9_dry_run_v1", "decision": decision,
        "formal_run_authorized": config["formal_run_authorized"], "protocol_id": PROTOCOL_ID,
        "fixed_denominator": 9, "conditions": conditions, "pilot": pilot, "baseline_archives": baselines,
        "model_identity": model, "environment": environment,
        "resource_policy": policy, "resource_gate": {
            "available_memory_gib": available, "startup_required_gib": 16,
            "process_tree_cap_gib": 13, "system_available_floor_gib": 3,
            "free_disk_gib": free_disk, "minimum_free_disk_gib": 20,
            "time_limit_seconds": 900, "monitor_interval_seconds": 0.25,
        },
        "git": git, "active_workers": workers, "gates": gates,
        "config_sha256": sha256(config_path.resolve()), "config_identity": runner.canonical_hash(config),
        "optimization_calls": 0,
    }


def audit_canonical(config: dict, condition: dict, output: Path) -> dict:
    canonical = output / "runs" / condition["condition_id"]
    attempt = output / "worker_logs" / condition["condition_id"] / "attempt-001"
    result_path = canonical / "result.json"
    provenance_path = canonical / "provenance.json"
    monitor_path = attempt / "resource_monitor.json"
    if not all(path.is_file() for path in (result_path, provenance_path, monitor_path, attempt / "stdout.log", attempt / "stderr.log", canonical / "solver.log")):
        raise RuntimeError("ARCHIVE_FAILURE: required Direct artifacts are missing")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    monitor = json.loads(monitor_path.read_text(encoding="utf-8"))
    _, preparation, hashes = runner.verified_input(config, condition)
    checks = {
        "condition": result.get("condition_id") == condition["condition_id"],
        "seed": result.get("seed") == condition["seed"],
        "config": result.get("config_hash") == runner.canonical_hash(config),
        "instance": result.get("instance_hash") == preparation["instance_hash"],
        "input_files": provenance.get("instance_sha256") == hashes["instance_sha256"] and provenance.get("preparation_sha256") == hashes["preparation_sha256"],
        "model": provenance.get("model_identity", {}).get("files") == config["frozen_model_files"],
        "archive_complete": provenance.get("archive_complete") is True,
        "result_hash": provenance.get("result_sha256") == sha256(result_path),
        "solver_log_hash": provenance.get("solver_log_sha256") == sha256(canonical / "solver.log"),
        "monitor_clean": monitor.get("worker_return_code") == 0 and monitor.get("stop_reason") is None,
    }
    if "first_stage_solution_sha256" in provenance:
        checks["first_stage_hash"] = provenance["first_stage_solution_sha256"] == sha256(canonical / "first_stage_solution.json")
    if "solver_progress_sha256" in provenance:
        checks["progress_hash"] = provenance["solver_progress_sha256"] == sha256(canonical / "solver_progress.json")
    if not all(checks.values()):
        raise RuntimeError(f"INTEGRITY_FAILURE: {checks}")
    return {"result": result, "monitor": monitor, "checks": checks}


def classify_condition(config: dict, condition: dict, output: Path) -> dict:
    attempt = output / "worker_logs" / condition["condition_id"] / "attempt-001"
    monitor_path = attempt / "resource_monitor.json"
    canonical = output / "runs" / condition["condition_id"]
    if canonical.exists():
        audited = audit_canonical(config, condition, output)
        result, monitor = audited["result"], audited["monitor"]
        classification = classify_completed_result(result, monitor)
    elif monitor_path.is_file():
        monitor = json.loads(monitor_path.read_text(encoding="utf-8"))
        result = {}
        if monitor.get("stop_reason") in {"RESOURCE_PROCESS_CAP", "RESOURCE_SYSTEM_CAP"} and monitor.get("worker_return_code") != 0:
            classification = "RESOURCE_LIMIT"
        elif monitor.get("stop_reason") == "MONITOR_HARD_TIME_LIMIT" and monitor.get("worker_return_code") != 0:
            classification = "TIME_LIMIT"
        else:
            classification = "INTEGRITY_FAILURE"
    else:
        return {"condition_id": condition["condition_id"], "attempt": "attempt-001", "classification": "INTEGRITY_FAILURE", "detail": "missing monitor and canonical"}
    return {
        "condition_id": condition["condition_id"], "attempt": "attempt-001",
        "classification": classification, "solver_status": result.get("solver_status"),
        "exact_certification": result.get("exact_certification"),
        "certification_status": result.get("certification_status"),
        "objective": result.get("objective"), "best_bound": result.get("best_bound"),
        "mip_gap": result.get("mip_gap"), "T_core_seconds": result.get("T_core_seconds"),
        "stop_reason": monitor.get("stop_reason"), "worker_return_code": monitor.get("worker_return_code"),
        "peak_process_tree_memory_gib": monitor.get("peak_process_tree_memory_gib"),
        "wall_clock_seconds": monitor.get("wall_clock_seconds"), "detail": "",
    }


def classify_completed_result(result: dict, monitor: dict) -> str:
    if monitor.get("worker_return_code") != 0 or monitor.get("stop_reason") is not None:
        return "INTEGRITY_FAILURE"
    status = result.get("solver_status")
    if status == "OPTIMAL" and result.get("exact_certification") is True and result.get("certification_status") == "PASS":
        return "CERTIFIED_SUCCESS"
    if status == "TIME_LIMIT" and result.get("exact_certification") is False and result.get("certification_status") == "NOT_ATTEMPTED" and all(result.get(key) is not None for key in ("objective", "best_bound", "mip_gap")):
        return "TIME_LIMIT"
    if status == "MEMORY_LIMIT" and result.get("exact_certification") is False:
        return "RESOURCE_LIMIT"
    return "INTEGRITY_FAILURE"


def worker_solve(config_path: Path, output_root: Path, condition_id: str) -> None:
    config = runner.load_config(config_path)
    validate_protocol({**config, "formal_run_authorized": False})
    configured_output = (ROOT / config["output_directory"]).resolve()
    if output_root.resolve() != configured_output:
        raise RuntimeError("DIRECT_OUTPUT_ROOT_MISMATCH")
    state = live_gates(config_path, condition_id, expect_worker_started=True, require_authorization=True)
    if not state["pass"]:
        raise RuntimeError(f"DIRECT_XXL10_REMAINING9_WORKER_BLOCKED: {state['gates']}")
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
        raise RuntimeError(f"DIRECT_XXL10_REMAINING9_PREFLIGHT_BLOCKED: {state['gates']}")
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
        raise RuntimeError(f"DIRECT_XXL10_REMAINING9_BLOCKED: {initial['gates']}")
    output = (ROOT / config["output_directory"]).resolve()
    report_path = output / "batch_reports" / f"{PROTOCOL_ID}.json"
    records = [{"condition_id": condition_id, "attempt": "attempt-001", "classification": "NOT_RUN"} for condition_id in EXPECTED]
    report = {"protocol_id": PROTOCOL_ID, "fixed_denominator": 9, "status": "RUNNING", "records": records}
    write_json(report_path, report)
    for index, condition in enumerate(runner.authorized_conditions(config)):
        error = None
        try:
            run_one(config_path, config, condition, output)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        if active_solver_workers():
            raise RuntimeError("INTEGRITY_FAILURE: worker did not exit")
        row = classify_condition(config, condition, output)
        if error:
            row["detail"] = error
        records[index] = row
        report["status"] = "STOPPED_INTEGRITY_FAILURE" if row["classification"] == "INTEGRITY_FAILURE" else "RUNNING"
        write_json(report_path, report)
        if row["classification"] == "INTEGRITY_FAILURE":
            raise RuntimeError(f"INTEGRITY_FAILURE stops batch: {row}")
    report["status"] = "COMPLETE"
    write_json(report_path, report)
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
