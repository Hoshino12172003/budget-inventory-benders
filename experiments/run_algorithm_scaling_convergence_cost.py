from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter, sleep
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.algorithm_scaling import (
    BETA,
    GAMMA,
    LAMBDA_R,
    METHODS,
    SIZES,
    SOURCE_CASES,
    canonical_hash,
    dry_run_plan,
    enumerate_conditions,
    file_sha256,
    instance_characteristics,
    load_config,
    normalized_trajectory,
    require_formal_authorization,
    resource_dimension_check,
    resource_preflight_passes,
    resource_thresholds,
    size_by_label,
    source_identity,
    validate_config,
    validate_scientific_parameters,
)
from robust_inventory_reconfiguration.e1c_scaling import build_renault_calibrated_instance
from robust_inventory_reconfiguration.instance import load_instance, save_instance
from robust_inventory_reconfiguration.nominal_baseline import (
    baseline_feasibility,
    solve_canonical_nominal_baseline,
)
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.pure_benders import solve_pure_benders
from robust_inventory_reconfiguration.standard_benders import solve_standard_benders


CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost.yaml"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _condition_map():
    return {condition.condition_id: condition for condition in enumerate_conditions()}


def _config_hash(config: dict) -> str:
    return canonical_hash(config)


def _model_identity(config: dict) -> str:
    return source_identity(ROOT, config["code_identity"]["model_files"])


def validate_execution_gate(config: dict) -> None:
    validate_config(config)
    require_formal_authorization(config)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("formal algorithm-scaling execution requires a clean committed worktree")


def _source_instances():
    return [load_instance(ROOT / f"data/formal_instances_v2/{case_id}.json") for case_id in SOURCE_CASES]


def _prepare_root(output_root: Path, size: str, seed: int) -> Path:
    return output_root / "instances" / size / str(seed)


def _run_root(output_root: Path, condition_id: str) -> Path:
    return output_root / "runs" / condition_id


def _result_temporary_root(target: Path) -> Path:
    return target.parent / f".tmp-{uuid4().hex}"


def _load_verified_preparation(output_root: Path, condition, config: dict):
    target = _prepare_root(output_root, condition.size, condition.seed)
    instance_path = target / "instance.json"
    record_path = target / "preparation.json"
    if not instance_path.is_file() or not record_path.is_file():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))
    instance = load_instance(instance_path)
    expected = {
        "instance_id": condition.instance_id,
        "size": condition.size,
        "seed": condition.seed,
        "config_hash": _config_hash(config),
        "model_identity": _model_identity(config),
        "instance_hash": canonical_hash(instance.to_dict()),
    }
    mismatches = {key: (record.get(key), value) for key, value in expected.items() if record.get(key) != value}
    if mismatches:
        raise RuntimeError(f"prepared instance identity mismatch: {mismatches}")
    if not validate_scientific_parameters(instance)["pass"]:
        raise RuntimeError("prepared instance scientific-parameter mismatch")
    return instance, record


def _prepare_instance(output_root: Path, condition, config: dict):
    verified = _load_verified_preparation(output_root, condition, config)
    if verified is not None:
        return verified
    target = _prepare_root(output_root, condition.size, condition.seed)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite incomplete preparation: {target}")
    dimensions = size_by_label(condition.size)
    resource = resource_dimension_check(config, dimensions)
    if not resource["pass"]:
        raise RuntimeError(f"RESOURCE_DIMENSION_GATE_BLOCKED: {resource}")
    primitive = build_renault_calibrated_instance(_source_instances(), dimensions, condition.seed)
    science = validate_scientific_parameters(primitive)
    if not science["pass"]:
        raise RuntimeError(f"SCIENTIFIC_PARAMETER_PROPAGATION_FAILURE: {science}")
    baseline = solve_canonical_nominal_baseline(primitive)
    feasibility = baseline_feasibility(primitive, baseline.baseline)
    if not feasibility["capacity_compatible"] or not feasibility["ub_compatible"]:
        raise RuntimeError("CANONICAL_BASELINE_FEASIBILITY_FAILURE")
    instance = replace(primitive, initial_inventory=baseline.baseline.x)
    record = {
        "instance_id": condition.instance_id,
        "size": condition.size,
        "seed": condition.seed,
        "dimensions": asdict(dimensions),
        "characteristics": instance_characteristics(dimensions),
        "config_hash": _config_hash(config),
        "model_identity": _model_identity(config),
        "code_commit": _git_commit(),
        "instance_hash": canonical_hash(instance.to_dict()),
        "primitive_instance_hash": canonical_hash(primitive.to_dict()),
        "source_data_hashes": {
            case_id: file_sha256(ROOT / f"data/formal_instances_v2/{case_id}.json")
            for case_id in SOURCE_CASES
        },
        "x0_hash": canonical_hash(instance.initial_inventory),
        "B_ref": baseline.baseline.first_stage_spending,
        "budget": BETA * baseline.baseline.first_stage_spending,
        "scientific_parameters": config["fixed_scientific_parameters"],
        "scientific_parameter_checks": science,
        "baseline_feasibility": feasibility,
        "canonical_baseline_rule": baseline.rule,
    }
    temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
    temporary.mkdir(parents=True)
    try:
        save_instance(instance, temporary / "instance.json")
        _write_json(temporary / "preparation.json", record)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return instance, record


def _solve(condition, instance, preparation: dict, config: dict):
    x0 = instance.initial_inventory
    if x0 is None:
        raise RuntimeError("prepared instance has no initial inventory")
    budget = float(preparation["budget"])
    tolerances = config["solver_tolerances"]
    maximum_iterations = config["algorithm"]["max_iterations"]
    time_limit = config["resource_policy"]["condition_time_limit_seconds"]
    if condition.method == "pure_benders":
        solved = solve_pure_benders(
            instance, x0, budget, GAMMA, LAMBDA_R,
            relative_gap_tolerance=tolerances["relative_gap"],
            cut_tolerance=tolerances["cut_violation"],
            objective_certification_tolerance=tolerances["objective_certification"],
            max_iterations=maximum_iterations,
            time_limit=time_limit,
        )
        exact = solved.exact_certification_pass and solved.cut_validity_pass
        cuts = solved.aggregate_cut_count
        feasibility_cuts = 0
        optimality_cuts = cuts
        oracle_time = solved.global_oracle_runtime
    elif condition.method == "aggregate_benders_structured_oracle":
        solved = solve_standard_benders(
            instance, x0, budget, GAMMA, LAMBDA_R,
            relative_gap_tolerance=tolerances["relative_gap"],
            cut_tolerance=tolerances["cut_violation"],
            objective_certification_tolerance=tolerances["objective_certification"],
            max_iterations=maximum_iterations,
            time_limit=time_limit,
        )
        exact = solved.exact_certification_pass and solved.cut_validity_pass
        cuts = solved.aggregate_cut_count
        feasibility_cuts = 0
        optimality_cuts = cuts
        oracle_time = solved.oracle_runtime
    else:
        solved = solve_prb_benders(
            instance, x0, budget, GAMMA, LAMBDA_R,
            relative_gap_tolerance=tolerances["relative_gap"],
            cut_tolerance=tolerances["cut_violation"],
            max_iterations=maximum_iterations,
        )
        exact = solved.exact_certification_pass and solved.global_risk_budget_coupling_pass
        cuts = solved.unique_product_cuts
        feasibility_cuts = 0
        optimality_cuts = cuts
        oracle_time = solved.separation_runtime
    if solved.status != "OPTIMAL" or not exact:
        raise RuntimeError(f"algorithm scaling condition is not exactly certified: {condition.condition_id}")
    trajectory = normalized_trajectory([asdict(item) for item in solved.iterations], solved.final_lower_bound)
    threshold_iterations = {
        threshold: next(
            (row["iteration"] for row in trajectory if row["normalized_LB"] >= threshold),
            None,
        )
        for threshold in (0.99, 0.995, 0.999, 0.9999)
    }
    accounted = solved.master_runtime + oracle_time + solved.certification_runtime
    result = {
        "experiment_id": config["experiment_id"],
        "condition_id": condition.condition_id,
        "method": condition.method,
        "size": condition.size,
        "seed": condition.seed,
        "instance_id": condition.instance_id,
        "instance_hash": preparation["instance_hash"],
        "config_hash": _config_hash(config),
        "code_commit": _git_commit(),
        "model_identity": _model_identity(config),
        "solver_profile": config["solver_profile"],
        "Gamma": GAMMA,
        "beta": BETA,
        "lambda_R": LAMBDA_R,
        "SL": config["fixed_scientific_parameters"]["SL"],
        "phi_multiplier": config["fixed_scientific_parameters"]["phi_multiplier"],
        "solver_status": solved.status,
        "exact_certification": bool(exact),
        "final_objective": solved.solution.objective,
        "final_lower_bound": solved.final_lower_bound,
        "final_upper_bound": solved.final_upper_bound,
        "relative_gap": solved.final_relative_gap,
        "iterations": len(solved.iterations),
        "iterations_to_99pct_final_LB": threshold_iterations[0.99],
        "iterations_to_99_5pct_final_LB": threshold_iterations[0.995],
        "iterations_to_99_9pct_final_LB": threshold_iterations[0.999],
        "iterations_to_99_99pct_final_LB": threshold_iterations[0.9999],
        "cuts": cuts,
        "feasibility_cuts": feasibility_cuts,
        "optimality_cuts": optimality_cuts,
        "total_core_solve_time": solved.total_runtime,
        "master_time": solved.master_runtime,
        "oracle_time": oracle_time,
        "certification_time": solved.certification_runtime,
        "initialization_other_overhead": max(0.0, solved.total_runtime - accounted),
        "master_share": solved.master_runtime / solved.total_runtime,
        "oracle_share": oracle_time / solved.total_runtime,
        "peak_process_tree_memory_gib": None,
        "result_reused": False,
    }
    return result, trajectory


def _write_result(output_root: Path, condition, result: dict, trajectory: list[dict]) -> None:
    target = _run_root(output_root, condition.condition_id)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite result: {condition.condition_id}")
    temporary = _result_temporary_root(target)
    temporary.mkdir(parents=True)
    try:
        result_path = temporary / "result.json"
        trajectory_path = temporary / "iteration_trajectory.json"
        _write_json(result_path, result)
        _write_json(trajectory_path, trajectory)
        _write_json(temporary / "provenance.json", {
            "result_sha256": file_sha256(result_path),
            "trajectory_sha256": file_sha256(trajectory_path),
            "config_hash": result["config_hash"],
            "instance_hash": result["instance_hash"],
            "model_identity": result["model_identity"],
            "code_commit": result["code_commit"],
        })
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _verified_complete_result(output_root: Path, condition, config: dict) -> bool:
    target = _run_root(output_root, condition.condition_id)
    paths = [target / name for name in ("result.json", "iteration_trajectory.json", "provenance.json")]
    if not any(path.exists() for path in paths):
        return False
    if not all(path.is_file() for path in paths):
        raise RuntimeError(f"incomplete existing result: {condition.condition_id}")
    result = json.loads(paths[0].read_text(encoding="utf-8"))
    provenance = json.loads(paths[2].read_text(encoding="utf-8"))
    checks = {
        "condition": result.get("condition_id") == condition.condition_id,
        "method": result.get("method") == condition.method,
        "size": result.get("size") == condition.size,
        "seed": result.get("seed") == condition.seed,
        "config": result.get("config_hash") == _config_hash(config),
        "model": result.get("model_identity") == _model_identity(config),
        "result_hash": provenance.get("result_sha256") == file_sha256(paths[0]),
        "trajectory_hash": provenance.get("trajectory_sha256") == file_sha256(paths[1]),
        "certified": result.get("solver_status") == "OPTIMAL" and result.get("exact_certification") is True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"existing result identity failure {condition.condition_id}: {','.join(failed)}")
    return True


def _preflight(config: dict, condition) -> list[float]:
    dimension_check = resource_dimension_check(config, size_by_label(condition.size))
    if not dimension_check["pass"]:
        raise RuntimeError(f"RESOURCE_DIMENSION_GATE_BLOCKED: {dimension_check}")
    samples = [psutil.virtual_memory().available / 2**30 for _ in range(3)]
    thresholds = resource_thresholds(config, condition.size)
    minimum = thresholds["minimum_available_memory_gib"]
    if not resource_preflight_passes(config, condition.size, samples):
        raise RuntimeError(
            f"RESOURCE_PREFLIGHT_BLOCKED {condition.size}: "
            f"{min(samples):.3f} GiB < {minimum:.3f} GiB"
        )
    return samples


def _process_tree_memory_gib(pid: int) -> float:
    try:
        parent = psutil.Process(pid)
        processes = [parent, *parent.children(recursive=True)]
    except psutil.Error:
        return 0.0
    total = 0
    for process in processes:
        try:
            memory = process.memory_info()
            total += max(int(memory.rss), int(getattr(memory, "private", 0)))
        except psutil.Error:
            pass
    return total / 2**30


def _terminate_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
        processes = [*parent.children(recursive=True), parent]
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


def _run_monitored(condition, config_path: Path, output_root: Path, config: dict) -> None:
    samples = _preflight(config, condition)
    thresholds = resource_thresholds(config, condition.size)
    log_parent = output_root / "worker_logs" / condition.condition_id
    attempt = 1
    while (log_parent / f"attempt-{attempt:03d}").exists():
        attempt += 1
    log_root = log_parent / f"attempt-{attempt:03d}"
    log_root.mkdir(parents=True)
    command = [
        sys.executable, str(Path(__file__).resolve()),
        "--worker-condition", condition.condition_id,
        "--config", str(config_path),
        "--output-root", str(output_root),
    ]
    started = perf_counter()
    peak = 0.0
    stop_reason = None
    with (log_root / "stdout.log").open("w", encoding="utf-8") as stdout, (log_root / "stderr.log").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            peak = max(peak, _process_tree_memory_gib(process.pid))
            available = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - started
            if peak >= thresholds["maximum_process_tree_memory_gib"]:
                stop_reason = "RESOURCE_PROCESS_CAP"
            elif available <= config["resource_policy"]["minimum_system_available_memory_gib"]:
                stop_reason = "RESOURCE_SYSTEM_CAP"
            elif elapsed >= config["resource_policy"]["condition_time_limit_seconds"]:
                stop_reason = "TIME_LIMIT"
            if stop_reason:
                _terminate_tree(process.pid)
                break
            sleep(config["resource_policy"]["poll_seconds"])
        return_code = process.poll()
    monitor = {
        "condition_id": condition.condition_id,
        "preflight_available_memory_gib": samples,
        "peak_process_tree_memory_gib": peak,
        "wall_clock_seconds": perf_counter() - started,
        "stop_reason": stop_reason,
        "worker_return_code": return_code,
    }
    _write_json(log_root / "monitor.json", monitor)
    if stop_reason or return_code != 0:
        raise RuntimeError(f"condition worker failed {condition.condition_id}: {stop_reason or return_code}")


def _worker(condition, output_root: Path, config: dict) -> None:
    instance, preparation = _prepare_instance(output_root, condition, config)
    result, trajectory = _solve(condition, instance, preparation, config)
    _write_result(output_root, condition, result, trajectory)


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded algorithm scaling/convergence-cost runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", metavar="CONDITION_ID")
    mode.add_argument("--execute-all", action="store_true")
    mode.add_argument("--execute-size", choices=tuple(size.scale for size in SIZES))
    mode.add_argument("--worker-condition", metavar="CONDITION_ID")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    validate_config(config)
    if args.dry_run:
        print(json.dumps(dry_run_plan(config), indent=2))
        return
    validate_execution_gate(config)
    conditions = _condition_map()
    condition_id = args.worker_condition or args.execute
    if condition_id is not None and condition_id not in conditions:
        raise ValueError("unknown algorithm-scaling condition ID")
    output_root = args.output_root or ROOT / config["output_directory"]
    if args.worker_condition:
        _worker(conditions[args.worker_condition], output_root, config)
        return
    if args.execute:
        selected = [conditions[args.execute]]
    elif args.execute_size:
        selected = [condition for condition in conditions.values() if condition.size == args.execute_size]
    else:
        selected = list(conditions.values())
    for condition in selected:
        if _verified_complete_result(output_root, condition, config):
            print(f"[RESUME VERIFIED] {condition.condition_id}", flush=True)
            continue
        print(f"[RUN] {condition.condition_id}", flush=True)
        _run_monitored(condition, args.config, output_root, config)


if __name__ == "__main__":
    main()
