from __future__ import annotations

import argparse
from dataclasses import replace
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
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.e1c_scaling import (
    ScalingDimensions,
    build_renault_calibrated_instance,
    scaling_size,
    validate_generated_instance,
)
from robust_inventory_reconfiguration.instance import load_instance, save_instance
from robust_inventory_reconfiguration.nominal_baseline import (
    baseline_feasibility,
    solve_canonical_nominal_baseline,
)
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.pure_benders import solve_pure_benders
from robust_inventory_reconfiguration.standard_benders import solve_standard_benders


CONFIG_PATH = ROOT / "experiments/configs/prb_j_scaling_development.json"
SOURCE_CASES = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")
PRODUCTS = (12, 24, 48, 96)
METHODS = ("pure_benders", "aggregate_benders_structured_oracle", "prb_benders")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def source_instances():
    return [load_instance(ROOT / f"data/formal_instances_v2/{case}.json") for case in SOURCE_CASES]


def dimensions(products: int) -> ScalingDimensions:
    return ScalingDimensions(f"J{products}", 25, 24, products)


def validate_config() -> dict[str, Any]:
    config = read_json(CONFIG_PATH)
    if config["development_run_authorized"] is not True or config["formal_run_authorized"] is not False:
        raise PermissionError("PRB_J_SCALING_DEVELOPMENT_AUTHORIZATION_INVALID")
    if tuple(config["product_grid"]) != PRODUCTS or tuple(config["methods"]) != METHODS:
        raise RuntimeError("product grid or methods changed")
    expected = {
        "seed": 20260911,
        "Gamma": 2,
        "beta": 1.0,
        "lambda_R": 0.05,
        "relative_gap_tolerance": 1e-6,
        "cut_tolerance": 1e-7,
        "objective_certification_tolerance": 1e-4,
        "canonical_continuous_fix_tolerance": 1e-8,
        "canonical_objective_face_validation_slack": 2e-9,
        "max_iterations": 500,
        "timeout_seconds_per_method": 900,
        "minimum_available_memory_gib_before_launch": 18,
        "process_memory_hard_stop_gib": 14,
        "system_available_memory_emergency_stop_gib": 3,
        "memory_poll_interval_seconds": 0.25,
    }
    for key, value in expected.items():
        if config[key] != value:
            raise RuntimeError(f"frozen setting changed: {key}")
    j12 = load_instance(ROOT / config["reuse_j12_prepare"] / "instance.json")
    if canonical_hash(j12.to_dict()) != config["expected_j12_instance_hash"]:
        raise RuntimeError("reused J12 instance identity changed")
    return config


def static_audit() -> dict[str, Any]:
    config = validate_config()
    rows = []
    for products in PRODUCTS:
        size = scaling_size(dimensions(products), gamma=2)
        allocations = math.comb(products + 2, 2)
        rows.append({"J": products, **size, "risk_budget_allocation_rows": allocations})
    return {
        "status": "STATIC_AUDIT_PASS",
        "optimization_calls": 0,
        "grid": list(PRODUCTS),
        "rows": rows,
        "j96_decision": "SAFE_TO_ATTEMPT_UNDER_FROZEN_MONITOR",
        "reason": "Pure has 11712 adversarial variables and 73729 constraints; structured methods hold 301 patterns per product and 28896 total product-risk blocks. The 14 GiB process-tree stop remains binding.",
        "memory_gate": {
            "preflight_gib": config["minimum_available_memory_gib_before_launch"],
            "process_stop_gib": config["process_memory_hard_stop_gib"],
            "system_emergency_gib": config["system_available_memory_emergency_stop_gib"],
            "poll_seconds": config["memory_poll_interval_seconds"],
        },
    }


def preflight(config: dict[str, Any]) -> list[float]:
    samples = []
    for index in range(int(config["preflight_consecutive_samples"])):
        available = psutil.virtual_memory().available / 2**30
        samples.append(available)
        if available < float(config["minimum_available_memory_gib_before_launch"]):
            raise RuntimeError(f"PRB_J_SCALING_PREFLIGHT_BLOCKED: {available:.6f} GiB < 18.000000 GiB")
        if index + 1 < int(config["preflight_consecutive_samples"]):
            sleep(0.25)
    return samples


def process_tree_memory_gib(pid: int) -> float:
    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0.0
    total = 0
    for process in processes:
        try:
            info = process.memory_info()
            total += max(int(info.rss), int(getattr(info, "private", 0)))
        except psutil.Error:
            continue
    return total / 2**30


def terminate_tree(pid: int) -> None:
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


def output_root(config: dict[str, Any]) -> Path:
    return ROOT / config["result_root"]


def prepared_root(config: dict[str, Any], products: int) -> Path:
    if products == 12:
        return ROOT / config["reuse_j12_prepare"]
    return output_root(config) / f"J{products}" / "PREPARE"


def monitored(config: dict[str, Any], products: int, task: str) -> dict[str, Any]:
    samples = preflight(config)
    target = output_root(config) / f"J{products}" / ("PREPARE" if task == "prepare" else task.upper())
    partial = target.with_name(f".{target.name}.partial")
    if target.exists() or partial.exists():
        raise FileExistsError(f"refusing to overwrite development artifact: {target}")
    partial.mkdir(parents=True)
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", task, "--products", str(products)]
    started = perf_counter()
    with (partial / "worker.stdout.log").open("w", encoding="utf-8") as stdout, (partial / "worker.stderr.log").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=partial, stdout=stdout, stderr=stderr)
        peak = 0.0
        stop_status = None
        while process.poll() is None:
            peak = max(peak, process_tree_memory_gib(process.pid))
            available = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - started
            if peak >= float(config["process_memory_hard_stop_gib"]) or available <= float(config["system_available_memory_emergency_stop_gib"]):
                stop_status = "RESOURCE_STOP"
            elif elapsed >= float(config["timeout_seconds_per_method"]):
                stop_status = "TIME_LIMIT"
            if stop_status:
                terminate_tree(process.pid)
                break
            sleep(float(config["memory_poll_interval_seconds"]))
        return_code = process.poll()
    wall = perf_counter() - started
    result_path = partial / "result.json"
    if stop_status:
        write_json(result_path, {"J": products, "task": task, "status": stop_status})
    elif return_code != 0:
        write_json(result_path, {"J": products, "task": task, "status": "ERROR", "return_code": return_code})
    result = read_json(result_path)
    result.update({
        "development_only": True,
        "paper_final_observation": False,
        "worker_started": True,
        "preflight_available_memory_gib": samples,
        "peak_process_tree_memory_gib": peak,
        "wall_clock_seconds": wall,
    })
    write_json(result_path, result)
    shutil.move(str(partial), str(target))
    return result


def worker_prepare(products: int, target: Path) -> None:
    config = validate_config()
    primitive = build_renault_calibrated_instance(source_instances(), dimensions(products), config["seed"])
    validation = validate_generated_instance(primitive, dimensions(products), config["seed"])
    if not validation["pass"]:
        raise RuntimeError("generated instance static validation failed")
    started = perf_counter()
    canonical = solve_canonical_nominal_baseline(
        primitive,
        fix_with_bounds=True,
        continuous_fix_tolerance=config["canonical_continuous_fix_tolerance"],
        objective_face_validation_slack=config["canonical_objective_face_validation_slack"],
    )
    feasibility = baseline_feasibility(primitive, canonical.baseline)
    if not feasibility["capacity_compatible"] or not feasibility["ub_compatible"]:
        raise RuntimeError("nominal incumbent failed feasibility audit")
    instance = replace(primitive, initial_inventory=canonical.baseline.x)
    save_instance(instance, target / "instance.json")
    write_json(target / "baseline.json", {
        "J": products,
        "seed": config["seed"],
        "Gamma": 2,
        "instance_hash": canonical_hash(instance.to_dict()),
        "x0_hash": canonical_hash(canonical.baseline.x),
        "B_ref": canonical.baseline.first_stage_spending,
        "nominal_objective": canonical.baseline.objective,
        "nominal_recourse": canonical.baseline.recourse_cost,
        "nominal_solver_optimize_calls": canonical.solve_count,
        "canonical_rule": canonical.rule,
        "feasibility": feasibility,
    })
    write_json(target / "result.json", {
        "J": products,
        "task": "prepare",
        "status": "OPTIMAL",
        "exact_certification": True,
        "core_runtime_seconds": perf_counter() - started,
        "nominal_solver_optimize_calls": canonical.solve_count,
    })


def method_common(config: dict[str, Any], products: int, method: str, baseline: dict[str, Any], instance: Any) -> dict[str, Any]:
    import gurobipy
    return {
        "J": products,
        "method": method,
        "Gamma": 2,
        "beta": 1.0,
        "lambda_R": 0.05,
        "instance_hash": canonical_hash(instance.to_dict()),
        "x0_hash": canonical_hash(instance.initial_inventory),
        "B_ref": float(baseline["B_ref"]),
        "solver_version": ".".join(map(str, gurobipy.gurobi.version())),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "hardware": {"platform": platform.platform(), "logical_cpu_count": os.cpu_count(), "physical_memory_gib": psutil.virtual_memory().total / 2**30},
    }


def worker_method(products: int, method: str, target: Path) -> None:
    config = validate_config()
    prepared = prepared_root(config, products)
    instance = load_instance(prepared / "instance.json")
    baseline = read_json(prepared / "baseline.json")
    x0 = instance.initial_inventory
    if x0 is None:
        raise RuntimeError("prepared instance has no x0")
    budget = float(baseline["B_ref"])
    common = method_common(config, products, method, baseline, instance)
    block_count = 301 * products
    if method == "pure_benders":
        solved = solve_pure_benders(instance, x0, budget, 2, 0.05, relative_gap_tolerance=1e-6, cut_tolerance=1e-7, objective_certification_tolerance=1e-4, max_iterations=500, time_limit=900, log_file=target / "solver.log")
        calls = len(solved.iterations) + 1
        result = {**common, "status": solved.status, "certified": solved.exact_certification_pass and solved.cut_validity_pass, "objective": solved.solution.objective, "lower_bound": solved.final_lower_bound, "upper_bound": solved.final_upper_bound, "relative_gap": solved.final_relative_gap, "T_core_seconds": solved.total_runtime, "master_time_seconds": solved.master_runtime, "oracle_time_seconds": solved.global_oracle_runtime, "certification_time_seconds": solved.certification_runtime, "iterations": len(solved.iterations), "cuts": solved.aggregate_cut_count, "global_milp_solve_count": calls, "mean_oracle_solve_time_seconds": solved.global_oracle_runtime / calls, "max_oracle_solve_time_seconds": "NOT_RECORDED", "product_risk_block_count": "NOT_APPLICABLE", "block_solve_count": "NOT_APPLICABLE"}
    elif method == "aggregate_benders_structured_oracle":
        solved = solve_standard_benders(instance, x0, budget, 2, 0.05, relative_gap_tolerance=1e-6, cut_tolerance=1e-7, objective_certification_tolerance=1e-4, max_iterations=500, time_limit=900, log_file=target / "solver.log")
        result = {**common, "status": solved.status, "certified": solved.exact_certification_pass and solved.cut_validity_pass, "objective": solved.solution.objective, "lower_bound": solved.final_lower_bound, "upper_bound": solved.final_upper_bound, "relative_gap": solved.final_relative_gap, "T_core_seconds": solved.total_runtime, "master_time_seconds": solved.master_runtime, "oracle_time_seconds": solved.oracle_runtime, "certification_time_seconds": solved.certification_runtime, "cut_generation_time_seconds": solved.cut_construction_runtime, "iterations": len(solved.iterations), "cuts": solved.aggregate_cut_count, "product_risk_block_count": block_count, "block_solve_count": solved.product_subproblem_evaluations, "mean_block_solve_time_seconds": solved.oracle_runtime / solved.product_pattern_evaluations if solved.product_pattern_evaluations else None, "gamma_allocation_dp_time_seconds": "NOT_RECORDED"}
    elif method == "prb_benders":
        solved = solve_prb_benders(instance, x0, budget, 2, 0.05, relative_gap_tolerance=1e-6, cut_tolerance=1e-7, max_iterations=500)
        result = {**common, "status": solved.status, "certified": solved.exact_certification_pass and solved.global_risk_budget_coupling_pass, "objective": solved.solution.objective, "lower_bound": solved.final_lower_bound, "upper_bound": solved.final_upper_bound, "relative_gap": solved.final_relative_gap, "T_core_seconds": solved.total_runtime, "master_time_seconds": solved.master_runtime, "oracle_time_seconds": solved.separation_runtime, "certification_time_seconds": solved.certification_runtime, "iterations": len(solved.iterations), "cuts": solved.unique_product_cuts, "product_risk_block_count": block_count, "block_solve_count": solved.product_subproblem_evaluations, "mean_block_solve_time_seconds": solved.separation_runtime / solved.product_pattern_evaluations if solved.product_pattern_evaluations else None, "gamma_allocation_dp_time_seconds": "NOT_RECORDED", "global_coupling_pass": solved.global_risk_budget_coupling_pass, "global_coupling_error": solved.global_risk_budget_coupling_error}
    else:
        raise ValueError(f"unsupported method: {method}")
    write_json(target / "result.json", result)


def worker(task: str, products: int) -> None:
    target = Path.cwd()
    if task == "prepare":
        worker_prepare(products, target)
    else:
        worker_method(products, task, target)


def dry_run() -> dict[str, Any]:
    config = validate_config()
    audit = static_audit()
    return {
        "status": "DRY_RUN_PASS",
        "optimization_calls": 0,
        "preparation_runs": [24, 48, 96],
        "reused_prepare": 12,
        "method_conditions": [{"J": products, "method": method} for products in PRODUCTS for method in METHODS],
        "static_audit": audit,
        "result_root": config["result_root"],
    }


def exactness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_method = {row["method"]: row for row in rows}
    pure = by_method["pure_benders"]
    checks = {}
    for method in METHODS[1:]:
        row = by_method[method]
        diff = abs(float(row["objective"]) - float(pure["objective"]))
        checks[method] = {"objective_difference": diff, "pass": diff <= 1e-4 and row.get("certified") is True and pure.get("certified") is True}
    return {"pass": all(check["pass"] for check in checks.values()), "checks": checks}


def run_all() -> None:
    config = validate_config()
    root = output_root(config)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite development result root: {root}")
    root.mkdir(parents=True)
    summary = {"status": "RUNNING", "development_only": True, "paper_final_observation": False, "formal_optimization_runs": 0, "development_preparation_runs": 0, "development_method_runs": 0, "results": []}
    prepared = [12]
    blocked: dict[str, str] = {}
    for products in PRODUCTS[1:]:
        row = monitored(config, products, "prepare")
        summary["results"].append(row)
        summary["development_preparation_runs"] += 1
        if row["status"] == "OPTIMAL":
            prepared.append(products)
        else:
            blocked[str(products)] = "CANONICAL_X0_PREPARATION_NUMERICAL_FAILURE"
    for products in prepared:
        rows = []
        for method in METHODS:
            row = monitored(config, products, method)
            summary["results"].append(row)
            summary["development_method_runs"] += 1
            rows.append(row)
        if all(row.get("objective") is not None for row in rows):
            consistency = exactness(rows)
            summary.setdefault("objective_consistency", {})[str(products)] = consistency
            if not consistency["pass"]:
                blocked[str(products)] = "METHOD_NONCERTIFICATION"
        else:
            blocked[str(products)] = "METHOD_TIMEOUT_OR_NONCERTIFICATION"
    summary["status"] = "PARTIAL_PREDECLARED_GRID" if blocked else "COMPLETE"
    summary["blocked_grid_points"] = blocked
    write_json(root / "development_summary.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-audit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--worker", choices=("prepare", *METHODS))
    parser.add_argument("--products", type=int, choices=PRODUCTS)
    args = parser.parse_args()
    if args.worker:
        if args.products is None:
            parser.error("--worker requires --products")
        worker(args.worker, args.products)
    elif args.static_audit:
        print(json.dumps(static_audit(), indent=2))
    elif args.dry_run:
        print(json.dumps(dry_run(), indent=2))
    elif args.run_all:
        run_all()
    else:
        parser.error("choose --static-audit, --dry-run, or --run-all")


if __name__ == "__main__":
    main()
