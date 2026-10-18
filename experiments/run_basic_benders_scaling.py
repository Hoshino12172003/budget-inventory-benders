"""Fail-closed launcher for the Basic-BD Scaling V2 development pilot.

Dry-run and identity checks do not build or optimize a Gurobi model.  The
execution path is intentionally limited to the single condition named by the
versioned protocol.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import gc
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from time import perf_counter, sleep
import traceback

import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_direct_scaling as direct_runner


DEFAULT_CONFIG = ROOT / "experiments/configs/development/basic_benders_scaling_l10_pilot_v1.yaml"


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def global_scenario_count(regions: int, products: int, gamma: int) -> int:
    from math import comb

    components = regions * products
    return sum(comb(components, value) for value in range(gamma + 1))


def candidate(config: dict) -> dict:
    allowed = config.get("authorized_condition_ids", [])
    if allowed != ["BASIC_L10_S20260921"]:
        raise RuntimeError("Basic-BD pilot scope is not exactly one frozen condition")
    return {"condition_id": allowed[0], "size": "L10", "seed": 20260921}


def source_condition(config: dict, selected: dict) -> dict:
    return {
        "condition_id": f"DIRECT_{selected['size']}_S{selected['seed']}",
        "size": selected["size"],
        "seed": selected["seed"],
    }


def dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = load_config(config_path)
    selected = candidate(config)
    instance, preparation, hashes = direct_runner.verified_input(
        config, source_condition(config, selected)
    )
    size = selected["size"]
    policy = config["resource_policy"]
    scenarios = global_scenario_count(
        instance.num_regions,
        instance.num_products,
        int(config["fixed_scientific_parameters"]["Gamma"]),
    )
    if scenarios > int(config["algorithm"]["maximum_global_scenarios"]):
        raise RuntimeError("global scenario count exceeds the frozen safety cap")
    memory = psutil.virtual_memory()
    output = ROOT / config["output_directory"]
    free_disk = shutil.disk_usage(output.parent).free / 2**30
    canonical = output / "runs" / selected["condition_id"]
    git_changes = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    return {
        "protocol_id": config["protocol_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "condition": selected,
        "source_instance_id": preparation["instance_id"],
        "instance_hash": preparation["instance_hash"],
        "x0_hash": preparation["x0_hash"],
        "instance_sha256": hashes["instance_sha256"],
        "preparation_sha256": hashes["preparation_sha256"],
        "global_scenario_count": scenarios,
        "maximum_global_scenarios": config["algorithm"]["maximum_global_scenarios"],
        "resource_gate": {
            "available_memory_gib": memory.available / 2**30,
            "startup_required_gib": policy["minimum_available_memory_gib_by_size"][size],
            "process_tree_cap_gib": policy["maximum_process_tree_memory_gib_by_size"][size],
            "system_available_floor_gib": policy["minimum_system_available_memory_gib"],
            "free_disk_gib": free_disk,
            "minimum_free_disk_gib": policy["minimum_free_disk_gib"],
            "time_limit_seconds": policy["condition_time_limit_seconds"],
            "monitor_interval_seconds": policy["memory_monitor_interval_seconds"],
        },
        "canonical_result_exists": canonical.exists(),
        "environment": direct_runner.current_environment(),
        "git_status_clean": not git_changes,
        "git_status_entries": git_changes,
        "optimization_calls": 0,
    }


def validate_execution_gate(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: Basic-BD development pilot remains disabled")
    audit = dry_run(config_path)
    gate = audit["resource_gate"]
    if gate["available_memory_gib"] < gate["startup_required_gib"]:
        raise RuntimeError("RESOURCE_START_MEMORY_GATE")
    if gate["free_disk_gib"] < gate["minimum_free_disk_gib"]:
        raise RuntimeError("RESOURCE_DISK_GATE")
    if audit["canonical_result_exists"]:
        raise FileExistsError("refusing to overwrite an existing Basic-BD pilot result")
    if not audit["git_status_clean"]:
        raise RuntimeError(f"GIT_STATUS_NOT_CLEAN: {audit['git_status_entries']}")
    return audit


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _process_tree_rss(pid: int) -> int:
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


def _stop_process_tree(pid: int) -> None:
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


def _model_identity() -> dict:
    paths = (
        "experiments/run_basic_benders_scaling.py",
        "experiments/run_renault_vanilla_bd_pilot.py",
        "src/robust_inventory_reconfiguration/pure_benders.py",
        "src/robust_inventory_reconfiguration/reconfiguration_model.py",
        "src/robust_inventory_reconfiguration/solver_profile.py",
    )
    files = {name: _sha256(ROOT / name) for name in paths}
    return {"sha256": direct_runner.canonical_hash(files), "files": files}


def _worker(config_path: Path, attempt_dir: Path) -> int:
    config = load_config(config_path)
    selected = candidate(config)
    try:
        if config.get("formal_run_authorized") is not True:
            raise RuntimeError("NOT_AUTHORIZED: Basic-BD worker remains disabled")
        import robust_inventory_reconfiguration.pure_benders as pure
        from experiments.run_renault_vanilla_bd_pilot import GlobalEnumeratedLPOracle
        from robust_inventory_reconfiguration.first_stage_solution import build_first_stage_solution_artifact

        instance, preparation, hashes = direct_runner.verified_input(
            config, source_condition(config, selected)
        )
        gamma = int(config["fixed_scientific_parameters"]["Gamma"])
        tolerance = config["solver_tolerances"]
        limit = float(config["resource_policy"]["condition_time_limit_seconds"])
        GlobalEnumeratedLPOracle.max_scenarios = int(config["algorithm"]["maximum_global_scenarios"])
        GlobalEnumeratedLPOracle.trace_path = attempt_dir / "oracle_trace.jsonl"
        original = pure.GlobalRobustAdversarialSubproblem
        started = perf_counter()
        try:
            pure.GlobalRobustAdversarialSubproblem = GlobalEnumeratedLPOracle
            solved = pure.solve_pure_benders(
                instance,
                instance.initial_inventory,
                float(preparation["budget"]),
                gamma,
                float(config["fixed_scientific_parameters"]["lambda_R"]),
                relative_gap_tolerance=float(tolerance["relative_gap"]),
                cut_tolerance=float(tolerance["cut_violation"]),
                objective_certification_tolerance=float(tolerance["objective_certification"]),
                max_iterations=int(config["algorithm"]["max_iterations"]),
                time_limit=limit,
                log_file=attempt_dir / "solver.log",
            )
        finally:
            pure.GlobalRobustAdversarialSubproblem = original
        remaining = limit - (perf_counter() - started)
        if remaining <= 0:
            raise TimeoutError("no time remains for independent Basic-BD certification")
        certification_started = perf_counter()
        certifier = GlobalEnumeratedLPOracle(instance, gamma)
        try:
            certified = certifier.solve(solved.solution.x, time_limit=remaining)
        finally:
            certifier.model.dispose()
        independent_seconds = perf_counter() - certification_started
        certified_objective = solved.solution.first_stage_expenditure + certified.value
        objective_residual = abs(certified_objective - solved.solution.objective)
        exact = bool(
            solved.status == "OPTIMAL"
            and solved.exact_certification_pass
            and solved.cut_validity_pass
            and certified.cut.dual_feasible
            and certified.cut.strong_duality_error <= float(tolerance["objective_certification"])
            and objective_residual <= float(tolerance["objective_certification"])
        )
        trace_rows = [
            json.loads(line)
            for line in (attempt_dir / "oracle_trace.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if len(trace_rows) < len(solved.iterations) + 2:
            raise RuntimeError("Basic-BD oracle trace is incomplete")
        trajectory = []
        for iteration, oracle_row in zip(solved.iterations, trace_rows):
            row = asdict(iteration)
            row["scenarios_checked"] = oracle_row["scenarios_solved"]
            row["oracle_trace_seconds"] = oracle_row["oracle_seconds"]
            row["cuts_added"] = 1 if row["cut_added"] else 0
            trajectory.append(row)
        identity = _model_identity()
        commit = _git_commit()
        result = {
            "experiment_id": config["experiment_id"],
            "protocol_id": config["protocol_id"],
            "condition_id": selected["condition_id"],
            "method": "basic_benders",
            "size": selected["size"],
            "seed": selected["seed"],
            "instance_id": preparation["instance_id"],
            "instance_hash": preparation["instance_hash"],
            "instance_sha256": hashes["instance_sha256"],
            "preparation_sha256": hashes["preparation_sha256"],
            "config_hash": direct_runner.canonical_hash(config),
            "code_commit": commit,
            "model_identity": identity,
            "solver_profile": config["solver_profile"],
            "environment": direct_runner.current_environment(),
            "solver_status": solved.status,
            "exact_certification": exact,
            "cut_validity": solved.cut_validity_pass,
            "final_objective": solved.solution.objective,
            "final_lower_bound": solved.final_lower_bound,
            "final_upper_bound": solved.final_upper_bound,
            "final_gap": solved.final_relative_gap,
            "iterations": len(trajectory),
            "cuts_added": solved.aggregate_cut_count,
            "algorithm_core_time": solved.total_runtime,
            "oracle_time": solved.global_oracle_runtime,
            "certification_time": solved.certification_runtime + independent_seconds,
            "total_time": perf_counter() - started,
            "independent_certification": {
                "objective": certified_objective,
                "objective_residual": objective_residual,
                "dual_feasible": certified.cut.dual_feasible,
                "strong_duality_residual": certified.cut.strong_duality_error,
            },
        }
        _write_json(attempt_dir / "result.json", result)
        _write_json(attempt_dir / "iteration_trajectory.json", trajectory)
        first_stage = build_first_stage_solution_artifact(
            instance,
            instance.initial_inventory,
            solved.solution,
            case_id=selected["condition_id"],
            mode="basic_benders",
            identity={
                "config_hash": result["config_hash"],
                "data_hash": result["instance_hash"],
                "x0_hash": preparation["x0_hash"],
                "git_commit": commit,
            },
            solver_profile=config["solver_profile"],
        )
        _write_json(attempt_dir / "first_stage_solution.json", first_stage)
        provenance = {
            "result_sha256": _sha256(attempt_dir / "result.json"),
            "trajectory_sha256": _sha256(attempt_dir / "iteration_trajectory.json"),
            "first_stage_solution_sha256": _sha256(attempt_dir / "first_stage_solution.json"),
            "instance_sha256": hashes["instance_sha256"],
            "preparation_sha256": hashes["preparation_sha256"],
            "config_hash": result["config_hash"],
            "model_identity": identity,
            "code_commit": commit,
        }
        _write_json(attempt_dir / "provenance.json", provenance)
        gc.collect()
        return 0 if exact else 2
    except Exception as error:
        (attempt_dir / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _write_json(attempt_dir / "worker_failure.json", {"error_type": type(error).__name__, "error": str(error)})
        return 1


def run_single_pilot(config_path: Path = DEFAULT_CONFIG) -> dict:
    audit = validate_execution_gate(config_path)
    config = load_config(config_path)
    selected = candidate(config)
    policy = config["resource_policy"]
    output = ROOT / config["output_directory"]
    attempt = output / "worker_logs" / selected["condition_id"] / "attempt-001"
    if attempt.exists():
        raise FileExistsError("attempt-001 already exists; automatic retry is forbidden")
    attempt.mkdir(parents=True)
    stdout_path, stderr_path = attempt / "stdout.log", attempt / "stderr.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--config",
        str(config_path),
        "--attempt-dir",
        str(attempt),
    ]
    started = perf_counter()
    peak = 0
    stop_reason = None
    samples = []
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            elapsed = perf_counter() - started
            rss = _process_tree_rss(process.pid) / 2**30
            available = psutil.virtual_memory().available / 2**30
            peak = max(peak, rss)
            samples.append({
                "elapsed_seconds": elapsed,
                "process_tree_rss_gib": rss,
                "system_available_gib": available,
            })
            if elapsed >= policy["condition_time_limit_seconds"]:
                stop_reason = "TIME_LIMIT"
            elif rss > policy["maximum_process_tree_memory_gib_by_size"][selected["size"]]:
                stop_reason = "RESOURCE_PROCESS_CAP"
            elif available < policy["minimum_system_available_memory_gib"]:
                stop_reason = "RESOURCE_SYSTEM_CAP"
            if stop_reason:
                _stop_process_tree(process.pid)
                break
            sleep(policy["memory_monitor_interval_seconds"])
        return_code = process.poll()
    monitor = {
        "condition_id": selected["condition_id"],
        "attempt": "attempt-001",
        "elapsed_seconds": perf_counter() - started,
        "peak_process_tree_memory_gib": peak,
        "stop_reason": stop_reason,
        "worker_return_code": return_code,
        "preflight": audit["resource_gate"],
        "samples": samples,
    }
    _write_json(attempt / "resource_monitor.json", monitor)
    outcome = {
        "condition_id": selected["condition_id"],
        "attempt": "attempt-001",
        "status": (
            "SUCCESS"
            if return_code == 0 and stop_reason is None
            else "RESOURCE_OR_TIME_FAILURE"
            if stop_reason is not None
            else "NUMERICAL_OR_WORKER_FAILURE"
        ),
        "stop_reason": stop_reason,
        "worker_return_code": return_code,
        "peak_process_tree_memory_gib": peak,
    }
    _write_json(attempt / "outcome.json", outcome)
    if return_code == 0 and stop_reason is None:
        result = json.loads((attempt / "result.json").read_text(encoding="utf-8"))
        if result.get("exact_certification") is not True:
            raise RuntimeError("worker returned success without exact certification")
        target = output / "runs" / selected["condition_id"]
        temporary = target.with_name(".tmp-basic-attempt-001")
        if target.exists() or temporary.exists():
            raise FileExistsError("canonical Basic-BD result path already exists")
        shutil.copytree(attempt, temporary)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
    return monitor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--attempt-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        if args.attempt_dir is None:
            raise ValueError("--attempt-dir is required for worker mode")
        return _worker(args.config.resolve(), args.attempt_dir.resolve())
    if args.execute:
        print(json.dumps(run_single_pilot(args.config.resolve()), indent=2, allow_nan=False))
        return 0
    print(json.dumps(dry_run(args.config), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
