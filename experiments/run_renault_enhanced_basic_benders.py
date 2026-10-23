from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from time import perf_counter, sleep
import traceback
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from experiments.run_renault_vanilla_bd_pilot import load_frozen_renault_case
from robust_inventory_reconfiguration.enhanced_basic_benders import (
    EnhancedGlobalEnumeratedLPOracle,
    solve_enhanced_basic_benders,
)


DEFAULT_CONFIG = ROOT / "experiments/configs/development/renault_enhanced_basic_benders_v1.yaml"
EXPECTED_CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
EXPECTED_CONDITIONS = tuple(f"EB_RENAULT_{case}" for case in EXPECTED_CASES)
ALLOWED_PREEXISTING_STATUS_PREFIX = "?? experiments/results/basic_benders_scaling_development_v1/"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("protocol_id") != "RENAULT_EB_BD_8CASE_V1":
        raise RuntimeError("unexpected EB-BD protocol identity")
    if tuple(config.get("case_ids", ())) != EXPECTED_CASES:
        raise RuntimeError("EB-BD case scope differs from the frozen Renault order")
    if tuple(config.get("authorized_condition_ids", ())) != EXPECTED_CONDITIONS:
        raise RuntimeError("EB-BD condition allowlist differs from the frozen scope")
    if config.get("fixed_scientific_parameters") != {"Gamma": 2, "lambda_R": 0.05}:
        raise RuntimeError("EB-BD scientific parameters differ from Basic-BD")
    expected_resources = {
        "execution": "sequential_single_process",
        "parallel_workers": 1,
        "minimum_available_memory_gib": 8,
        "maximum_process_tree_memory_gib": 4,
        "minimum_system_available_memory_gib": 3,
        "minimum_free_disk_gib": 20,
        "condition_time_limit_seconds": 300,
        "memory_monitor_interval_seconds": 0.25,
        "fail_closed": True,
        "retry_policy": "no_automatic_retry",
    }
    if config.get("resource_policy") != expected_resources:
        raise RuntimeError("EB-BD resource contract differs from the frozen development protocol")
    return config


def active_workers() -> list[dict[str, Any]]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or []).lower()
            name = (process.info.get("name") or "").lower()
            if name.startswith("gurobi") or (
                "run_renault_enhanced_basic_benders.py" in command and "--worker" in command
            ):
                found.append({"pid": process.info["pid"], "name": process.info.get("name")})
        except psutil.Error:
            continue
    return found


def git_status_for_execution(output_root: Path) -> dict[str, Any]:
    lines = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).splitlines()
    output_prefix = f"?? {output_root.relative_to(ROOT).as_posix()}/"
    unexpected = [
        line
        for line in lines
        if not line.startswith(ALLOWED_PREEXISTING_STATUS_PREFIX)
        and not line.startswith(output_prefix)
    ]
    return {"entries": lines, "unexpected_entries": unexpected, "pass": not unexpected}


def condition_identity(config: dict[str, Any], case_id: str) -> dict[str, Any]:
    loaded = load_frozen_renault_case(case_id)
    instance = loaded["instance"]
    scenario_count = sum(
        math.comb(instance.num_regions * instance.num_products, size)
        for size in range(loaded["gamma"] + 1)
    )
    expected = config["frozen_case_identity"][case_id]
    checks = {
        key: loaded["identity"][key] == expected[key]
        for key in ("instance_hash", "x0_hash", "calibration_hash", "mapping_hash")
    }
    checks.update({
        "Gamma": loaded["gamma"] == 2,
        "lambda_R": loaded["lambda_r"] == 0.05,
        "scenario_count": scenario_count == 4657,
        "scenario_cap": scenario_count <= config["algorithm"]["maximum_global_scenarios"],
    })
    return {
        "case_id": case_id,
        "condition_id": f"EB_RENAULT_{case_id}",
        "dimensions": [instance.num_depots, instance.num_regions, instance.num_products],
        "budget": loaded["budget"],
        "Gamma": loaded["gamma"],
        "lambda_R": loaded["lambda_r"],
        "scenario_count": scenario_count,
        "identity": loaded["identity"],
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    import gurobipy as gp

    config_path = config_path.resolve()
    config = load_config(config_path)
    output_root = ROOT / config["output_directory"]
    cases = []
    for case_id in EXPECTED_CASES:
        identity = condition_identity(config, case_id)
        condition_id = identity["condition_id"]
        attempt = output_root / "worker_logs" / condition_id / "attempt-001"
        canonical = output_root / "runs" / condition_id
        identity.update({
            "expected_attempt": "attempt-001",
            "attempt_exists": attempt.exists(),
            "canonical_exists": canonical.exists(),
        })
        cases.append(identity)
    resource = config["resource_policy"]
    available = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output_root.parent).free / 2**30
    workers = active_workers()
    git = git_status_for_execution(output_root)
    gates = {
        "all_case_identities": all(row["status"] == "PASS" for row in cases),
        "all_attempts_absent": all(not row["attempt_exists"] for row in cases),
        "all_canonical_results_absent": all(not row["canonical_exists"] for row in cases),
        "startup_memory": available >= resource["minimum_available_memory_gib"],
        "disk": free_disk >= resource["minimum_free_disk_gib"],
        "git_status": git["pass"],
        "no_active_solver_worker": not workers,
    }
    return {
        "schema": "renault_eb_bd_dry_run_v1",
        "protocol_id": config["protocol_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "conditions": cases,
        "resource_snapshot": {
            "available_memory_gib": available,
            "free_disk_gib": free_disk,
            "active_workers": workers,
        },
        "git_status": git,
        "gates": gates,
        "environment": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        },
        "decision": "READY_FOR_AUTHORIZATION" if all(gates.values()) else "BLOCKED",
        "optimization_calls": 0,
    }


def certify_solution(instance: Any, solution: Any, gamma: int, time_limit: float) -> dict[str, Any]:
    oracle = EnhancedGlobalEnumeratedLPOracle(instance, gamma)
    try:
        certified = oracle.solve(solution.x, time_limit=time_limit)
    finally:
        oracle.close()
    objective = solution.first_stage_expenditure + certified.value
    residual = abs(objective - solution.objective)
    return {
        "certified_recourse": certified.value,
        "certified_objective": objective,
        "objective_residual": residual,
        "dual_feasible": certified.cut.dual_feasible,
        "strong_duality_residual": certified.cut.strong_duality_error,
        "pass": (
            certified.cut.dual_feasible
            and certified.cut.strong_duality_error <= 1e-4
            and residual <= 1e-4
        ),
    }


def solve_condition(config_path: Path, condition_id: str, attempt_root: Path) -> dict[str, Any]:
    import gurobipy as gp

    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: Renault EB-BD execution is disabled")
    if condition_id not in EXPECTED_CONDITIONS:
        raise RuntimeError("condition is outside the EB-BD allowlist")
    if attempt_root.exists():
        raise FileExistsError(f"refusing to overwrite attempt: {attempt_root}")
    attempt_root.mkdir(parents=True)
    case_id = condition_id.rsplit("_", 1)[1]
    identity = condition_identity(config, case_id)
    if identity["status"] != "PASS":
        raise RuntimeError(f"IDENTITY_FAILURE: {identity['checks']}")
    loaded = load_frozen_renault_case(case_id)
    algorithm_started = perf_counter()
    solved, diagnostics = solve_enhanced_basic_benders(
        loaded["instance"],
        loaded["x0"],
        loaded["budget"],
        loaded["gamma"],
        loaded["lambda_r"],
        relative_gap_tolerance=config["solver_tolerances"]["relative_gap"],
        cut_tolerance=config["solver_tolerances"]["cut_violation"],
        objective_certification_tolerance=config["solver_tolerances"]["objective_certification"],
        max_iterations=config["algorithm"]["max_iterations"],
        time_limit=config["resource_policy"]["condition_time_limit_seconds"],
        log_file=attempt_root / "solver.log",
        trace_path=attempt_root / "oracle_trace.jsonl",
    )
    algorithm_seconds = perf_counter() - algorithm_started
    remaining = config["resource_policy"]["condition_time_limit_seconds"] - algorithm_seconds
    if remaining <= 0:
        raise TimeoutError("no time remains for independent global certification")
    certification_started = perf_counter()
    independent = certify_solution(
        loaded["instance"], solved.solution, loaded["gamma"], remaining
    )
    certification_seconds = perf_counter() - certification_started
    exact = bool(
        solved.status == "OPTIMAL"
        and solved.exact_certification_pass
        and solved.cut_validity_pass
        and independent["pass"]
    )
    trajectory = [asdict(row) for row in solved.iterations]
    first_stage = {
        "y": solved.solution.y,
        "x": solved.solution.x,
        "a_plus": solved.solution.a_plus,
        "a_minus": solved.solution.a_minus,
    }
    result = {
        "schema": "renault_eb_bd_result_v1",
        "experiment_id": config["experiment_id"],
        "protocol_id": config["protocol_id"],
        "condition_id": condition_id,
        "case_id": case_id,
        "attempt": "attempt-001",
        "method": "EB-BD",
        "solver_status": solved.status,
        "exact_certification": exact,
        "cut_validity": solved.cut_validity_pass,
        "objective": solved.solution.objective,
        "final_lower_bound": solved.final_lower_bound,
        "final_upper_bound": solved.final_upper_bound,
        "final_absolute_gap": solved.final_absolute_gap,
        "final_relative_gap": solved.final_relative_gap,
        "iterations": len(solved.iterations),
        "cuts_added": solved.aggregate_cut_count,
        "oracle_seconds": solved.global_oracle_runtime,
        "algorithm_core_time_seconds": algorithm_seconds,
        "independent_certification_seconds": certification_seconds,
        "total_time_seconds": algorithm_seconds + certification_seconds,
        "independent_global_certification": independent,
        "oracle_engineering": diagnostics,
        "solver_profile": config["solver_profile"],
        "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        "identity": loaded["identity"],
    }
    write_json(attempt_root / "iteration_trajectory.json", trajectory)
    write_json(attempt_root / "first_stage_solution.json", first_stage)
    write_json(attempt_root / "result.json", result)
    provenance = {
        "schema": "renault_eb_bd_provenance_v1",
        "condition_id": condition_id,
        "attempt": "attempt-001",
        "formal_run_authorized": True,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "config_path": str(config_path),
        "config_sha256": sha256(config_path),
        "implementation_sha256": sha256(ROOT / "src/robust_inventory_reconfiguration/enhanced_basic_benders.py"),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "result_sha256": sha256(attempt_root / "result.json"),
        "trajectory_sha256": sha256(attempt_root / "iteration_trajectory.json"),
        "first_stage_sha256": sha256(attempt_root / "first_stage_solution.json"),
        "identity": loaded["identity"],
    }
    write_json(attempt_root / "provenance.json", provenance)
    if not exact:
        raise RuntimeError("NUMERICAL_CERTIFICATION_FAILURE: EB-BD result is not exact-certified")
    return result


def process_tree_rss(pid: int) -> int:
    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0
    total = 0
    for process in processes:
        try:
            total += process.memory_info().rss
        except psutil.Error:
            pass
    return total


def stop_process_tree(pid: int) -> None:
    try:
        root = psutil.Process(pid)
        processes = [*root.children(recursive=True), root]
    except psutil.Error:
        return
    for process in processes:
        try:
            process.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(processes, timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(alive, timeout=3)


def run_monitored(config_path: Path, condition_id: str) -> dict[str, Any]:
    config = load_config(config_path)
    output_root = ROOT / config["output_directory"]
    attempt_root = output_root / "worker_logs" / condition_id / "attempt-001"
    canonical = output_root / "runs" / condition_id
    if attempt_root.exists() or canonical.exists():
        raise FileExistsError(f"refusing to overwrite EB-BD evidence: {condition_id}")
    attempt_root.mkdir(parents=True)
    payload = attempt_root / "payload"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--config", str(config_path),
        "--worker", condition_id,
        "--attempt-root", str(payload),
    ]
    resource = config["resource_policy"]
    started = perf_counter()
    peak = 0
    stop_reason = None
    samples = []
    with (attempt_root / "stdout.log").open("w", encoding="utf-8") as stdout, (
        attempt_root / "stderr.log"
    ).open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            elapsed = perf_counter() - started
            rss = process_tree_rss(process.pid)
            available = psutil.virtual_memory().available
            peak = max(peak, rss)
            samples.append({
                "elapsed_seconds": elapsed,
                "process_tree_rss_gib": rss / 2**30,
                "system_available_gib": available / 2**30,
            })
            if elapsed >= resource["condition_time_limit_seconds"]:
                stop_reason = "TIME_LIMIT"
            elif rss / 2**30 > resource["maximum_process_tree_memory_gib"]:
                stop_reason = "RESOURCE_PROCESS_CAP"
            elif available / 2**30 < resource["minimum_system_available_memory_gib"]:
                stop_reason = "RESOURCE_SYSTEM_CAP"
            if stop_reason:
                stop_process_tree(process.pid)
                break
            sleep(resource["memory_monitor_interval_seconds"])
        return_code = process.poll()
    monitor = {
        "condition_id": condition_id,
        "attempt": "attempt-001",
        "elapsed_seconds": perf_counter() - started,
        "peak_process_tree_memory_gib": peak / 2**30,
        "stop_reason": stop_reason,
        "worker_return_code": return_code,
        "samples": samples,
        "limits": resource,
    }
    write_json(attempt_root / "resource_monitor.json", monitor)
    if return_code == 0 and stop_reason is None:
        result = json.loads((payload / "result.json").read_text(encoding="utf-8"))
        if result.get("exact_certification") is not True:
            raise RuntimeError(f"NUMERICAL_CERTIFICATION_FAILURE: {condition_id}")
        temporary = canonical.with_name(f".tmp-{condition_id}")
        if temporary.exists():
            raise FileExistsError(f"stale canonical temporary directory: {temporary}")
        shutil.copytree(payload, temporary)
        for artifact_name in ("stdout.log", "stderr.log", "resource_monitor.json"):
            shutil.copy2(attempt_root / artifact_name, temporary / artifact_name)
        os.replace(temporary, canonical)
        return {"classification": "SUCCESS", **monitor}
    if stop_reason in config["failure_policy"]["continue_after"]:
        if active_workers():
            raise RuntimeError(f"INTEGRITY_FAILURE: worker survived resource stop for {condition_id}")
        return {"classification": "RESOURCE_OR_TIME_FAILURE", **monitor}
    raise RuntimeError(f"UNKNOWN_WORKER_FAILURE: {condition_id}, return_code={return_code}")


def execute_batch(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: Renault EB-BD batch remains disabled")
    initial = build_dry_run(config_path)
    if not all(initial["gates"].values()):
        raise RuntimeError(f"BATCH_PREFLIGHT_BLOCKED: {initial['gates']}")
    records = []
    for condition_id in EXPECTED_CONDITIONS:
        current = build_dry_run(config_path)
        row = next(row for row in current["conditions"] if row["condition_id"] == condition_id)
        if row["status"] != "PASS" or row["attempt_exists"] or row["canonical_exists"]:
            raise RuntimeError(f"INTEGRITY_FAILURE before {condition_id}: {row}")
        outcome = run_monitored(config_path, condition_id)
        records.append(outcome)
    return {"protocol_id": config["protocol_id"], "status": "COMPLETE", "records": records}


def worker_main(config_path: Path, condition_id: str, attempt_root: Path) -> int:
    try:
        solve_condition(config_path.resolve(), condition_id, attempt_root.resolve())
        return 0
    except Exception as error:
        attempt_root.mkdir(parents=True, exist_ok=True)
        (attempt_root / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        write_json(attempt_root / "failure.json", {
            "condition_id": condition_id,
            "error_type": type(error).__name__,
            "error": str(error),
        })
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--worker", choices=EXPECTED_CONDITIONS)
    parser.add_argument("--attempt-root", type=Path)
    args = parser.parse_args()
    if args.worker:
        if args.attempt_root is None:
            parser.error("--worker requires --attempt-root")
        return worker_main(args.config, args.worker, args.attempt_root)
    result = execute_batch(args.config) if args.execute else build_dry_run(args.config)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
