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
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.pure_benders import (
    estimate_global_adversarial_size,
    solve_pure_benders,
)
from robust_inventory_reconfiguration.standard_benders import solve_standard_benders


CONFIG_PATH = ROOT / "experiments/configs/e1c_gamma_sensitivity_development.json"
EXISTING_L_ROOT = ROOT / "experiments/results/e1c_development_probe_v1/L"
METHODS = (
    "pure_benders",
    "aggregate_benders_structured_oracle",
    "prb_benders",
)
GAMMAS = (2, 4, 6, 8)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def validate_config() -> tuple[dict[str, Any], Any, dict[str, Any]]:
    config = read_json(CONFIG_PATH)
    if config["development_run_authorized"] is not True:
        raise PermissionError("E1C_GAMMA_DEVELOPMENT_NOT_AUTHORIZED")
    if config["formal_run_authorized"] is not False:
        raise RuntimeError("formal authorization must remain false")
    if tuple(config["gamma_grid"]) != GAMMAS or tuple(config["methods"]) != METHODS:
        raise RuntimeError("Gamma grid or method order changed")
    frozen = {
        "beta": 1.0,
        "lambda_R": 0.05,
        "relative_gap_tolerance": 1e-6,
        "cut_tolerance": 1e-7,
        "objective_certification_tolerance": 1e-4,
        "max_iterations": 500,
        "timeout_seconds_per_method": 900,
        "minimum_available_memory_gib_before_launch": 18,
        "process_memory_hard_stop_gib": 14,
        "system_available_memory_emergency_stop_gib": 3,
        "memory_poll_interval_seconds": 0.25,
    }
    for key, value in frozen.items():
        if config[key] != value:
            raise RuntimeError(f"frozen setting changed: {key}")
    instance_path = ROOT / config["prepared_instance"]
    baseline_path = ROOT / config["prepared_baseline"]
    instance = load_instance(instance_path)
    baseline = read_json(baseline_path)
    if (instance.num_depots, instance.num_regions, instance.num_products) != (25, 24, 12):
        raise RuntimeError("prepared L dimensions changed")
    if canonical_hash(instance.to_dict()) != config["expected_instance_hash"]:
        raise RuntimeError("prepared instance hash changed")
    if instance.initial_inventory is None:
        raise RuntimeError("prepared L instance has no x0")
    if canonical_hash(instance.initial_inventory) != config["expected_x0_hash"]:
        raise RuntimeError("prepared x0 hash changed")
    if float(baseline["B_ref"]) <= 0:
        raise RuntimeError("prepared B_ref is invalid")
    return config, instance, baseline


def preflight(config: dict[str, Any]) -> list[float]:
    samples: list[float] = []
    for index in range(int(config["preflight_consecutive_samples"])):
        available = psutil.virtual_memory().available / 2**30
        samples.append(available)
        if available < float(config["minimum_available_memory_gib_before_launch"]):
            raise RuntimeError(
                "E1C_GAMMA_RESOURCE_PREFLIGHT_BLOCKED: "
                f"{available:.6f} GiB < {config['minimum_available_memory_gib_before_launch']:.6f} GiB"
            )
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


def result_root(config: dict[str, Any]) -> Path:
    return ROOT / config["result_root"]


def run_worker_monitored(config: dict[str, Any], gamma: int, method: str) -> dict[str, Any]:
    samples = preflight(config)
    target = result_root(config) / f"G{gamma}" / method.upper()
    partial = target.with_name(f".{target.name}.partial")
    if target.exists() or partial.exists():
        raise FileExistsError(f"refusing to overwrite development artifact: {target}")
    partial.mkdir(parents=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        method,
        "--gamma",
        str(gamma),
    ]
    started = perf_counter()
    with (partial / "worker.stdout.log").open("w", encoding="utf-8") as stdout, (
        partial / "worker.stderr.log"
    ).open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=partial, stdout=stdout, stderr=stderr)
        peak = 0.0
        stop_status = None
        while process.poll() is None:
            peak = max(peak, process_tree_memory_gib(process.pid))
            available = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - started
            if peak >= float(config["process_memory_hard_stop_gib"]):
                stop_status = "RESOURCE_STOP"
            elif available <= float(config["system_available_memory_emergency_stop_gib"]):
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
        write_json(result_path, {"gamma": gamma, "method": method, "status": stop_status})
    elif return_code != 0:
        write_json(
            result_path,
            {"gamma": gamma, "method": method, "status": "ERROR", "return_code": return_code},
        )
    result = read_json(result_path)
    result.update(
        {
            "development_only": True,
            "paper_final_observation": False,
            "worker_started": True,
            "preflight_available_memory_gib": samples,
            "peak_process_tree_memory_gib": peak,
            "wall_clock_seconds": wall,
        }
    )
    write_json(result_path, result)
    shutil.move(str(partial), str(target))
    return result


def base_result(config: dict[str, Any], baseline: dict[str, Any], gamma: int, method: str) -> dict[str, Any]:
    import gurobipy

    return {
        "gamma": gamma,
        "method": method,
        "development_only": True,
        "paper_final_observation": False,
        "instance_hash": config["expected_instance_hash"],
        "x0_hash": config["expected_x0_hash"],
        "B_ref": float(baseline["B_ref"]),
        "beta": config["beta"],
        "lambda_R": config["lambda_R"],
        "solver_version": ".".join(map(str, gurobipy.gurobi.version())),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "hardware": {
            "platform": platform.platform(),
            "logical_cpu_count": os.cpu_count(),
            "physical_memory_gib": psutil.virtual_memory().total / 2**30,
        },
    }


def solution_metrics(solution: Any) -> dict[str, float]:
    return {
        "objective": solution.objective,
        "first_stage_expenditure": solution.first_stage_expenditure,
        "robust_recourse_cost": solution.robust_recourse_cost,
    }


def worker(method: str, gamma: int) -> None:
    config, instance, baseline = validate_config()
    target = Path.cwd()
    common = base_result(config, baseline, gamma, method)
    budget = float(baseline["B_ref"])
    x0 = instance.initial_inventory
    assert x0 is not None
    if method == "pure_benders":
        solved = solve_pure_benders(
            instance,
            x0,
            budget,
            gamma,
            config["lambda_R"],
            relative_gap_tolerance=config["relative_gap_tolerance"],
            cut_tolerance=config["cut_tolerance"],
            objective_certification_tolerance=config["objective_certification_tolerance"],
            max_iterations=config["max_iterations"],
            time_limit=config["timeout_seconds_per_method"],
            log_file=target / "solver.log",
        )
        size = estimate_global_adversarial_size(instance)
        solve_count = len(solved.iterations) + 1
        result = {
            **common,
            "status": solved.status,
            "certified": solved.exact_certification_pass and solved.cut_validity_pass,
            **solution_metrics(solved.solution),
            "lower_bound": solved.final_lower_bound,
            "upper_bound": solved.final_upper_bound,
            "absolute_gap": solved.final_absolute_gap,
            "relative_gap": solved.final_relative_gap,
            "T_core_seconds": solved.total_runtime,
            "master_time_seconds": solved.master_runtime,
            "oracle_time_seconds": solved.global_oracle_runtime,
            "certification_time_seconds": solved.certification_runtime,
            "cut_generation_time_seconds": "NOT_RECORDED",
            "iterations": len(solved.iterations),
            "cuts": solved.aggregate_cut_count,
            "global_adversarial_milp": size,
            "global_milp_solve_count": solve_count,
            "mean_oracle_solve_time_seconds": solved.global_oracle_runtime / solve_count,
            "max_oracle_solve_time_seconds": "NOT_RECORDED",
            "product_risk_block_count": "NOT_APPLICABLE",
            "block_solve_count": "NOT_APPLICABLE",
            "gamma_allocation_dp_time_seconds": "NOT_APPLICABLE",
        }
    elif method == "aggregate_benders_structured_oracle":
        solved = solve_standard_benders(
            instance,
            x0,
            budget,
            gamma,
            config["lambda_R"],
            relative_gap_tolerance=config["relative_gap_tolerance"],
            cut_tolerance=config["cut_tolerance"],
            objective_certification_tolerance=config["objective_certification_tolerance"],
            max_iterations=config["max_iterations"],
            time_limit=config["timeout_seconds_per_method"],
            log_file=target / "solver.log",
        )
        blocks = instance.num_products * sum(
            math.comb(instance.num_regions, g) for g in range(gamma + 1)
        )
        result = {
            **common,
            "status": solved.status,
            "certified": solved.exact_certification_pass and solved.cut_validity_pass,
            **solution_metrics(solved.solution),
            "lower_bound": solved.final_lower_bound,
            "upper_bound": solved.final_upper_bound,
            "absolute_gap": solved.final_absolute_gap,
            "relative_gap": solved.final_relative_gap,
            "T_core_seconds": solved.total_runtime,
            "master_time_seconds": solved.master_runtime,
            "oracle_time_seconds": solved.oracle_runtime,
            "certification_time_seconds": solved.certification_runtime,
            "cut_generation_time_seconds": solved.cut_construction_runtime,
            "iterations": len(solved.iterations),
            "cuts": solved.aggregate_cut_count,
            "product_risk_block_count": blocks,
            "block_solve_count": solved.product_subproblem_evaluations,
            "gamma_allocation_dp_time_seconds": "NOT_RECORDED",
        }
    elif method == "prb_benders":
        solved = solve_prb_benders(
            instance,
            x0,
            budget,
            gamma,
            config["lambda_R"],
            relative_gap_tolerance=config["relative_gap_tolerance"],
            cut_tolerance=config["cut_tolerance"],
            max_iterations=config["max_iterations"],
        )
        blocks = instance.num_products * sum(
            math.comb(instance.num_regions, g) for g in range(gamma + 1)
        )
        result = {
            **common,
            "status": solved.status,
            "certified": solved.exact_certification_pass and solved.global_risk_budget_coupling_pass,
            **solution_metrics(solved.solution),
            "lower_bound": solved.final_lower_bound,
            "upper_bound": solved.final_upper_bound,
            "absolute_gap": max(0.0, solved.final_upper_bound - solved.final_lower_bound),
            "relative_gap": solved.final_relative_gap,
            "T_core_seconds": solved.total_runtime,
            "master_time_seconds": solved.master_runtime,
            "oracle_time_seconds": solved.separation_runtime,
            "certification_time_seconds": solved.certification_runtime,
            "cut_generation_time_seconds": "NOT_RECORDED",
            "iterations": len(solved.iterations),
            "cuts": solved.unique_product_cuts,
            "product_risk_block_count": blocks,
            "block_solve_count": solved.product_subproblem_evaluations,
            "gamma_allocation_dp_time_seconds": "NOT_RECORDED",
            "global_coupling_pass": solved.global_risk_budget_coupling_pass,
            "global_coupling_error": solved.global_risk_budget_coupling_error,
        }
    else:
        raise ValueError(f"unsupported method: {method}")
    write_json(target / "result.json", result)


def dry_run() -> dict[str, Any]:
    config, instance, baseline = validate_config()
    return {
        "status": "DRY_RUN_PASS",
        "optimization_calls": 0,
        "instance_hash": canonical_hash(instance.to_dict()),
        "x0_hash": canonical_hash(instance.initial_inventory),
        "B_ref": baseline["B_ref"],
        "conditions": [
            {"gamma": gamma, "method": method}
            for gamma in GAMMAS
            for method in METHODS
        ],
        "timeout_seconds": config["timeout_seconds_per_method"],
        "memory_gate": {
            "preflight_gib": config["minimum_available_memory_gib_before_launch"],
            "process_stop_gib": config["process_memory_hard_stop_gib"],
            "system_emergency_gib": config["system_available_memory_emergency_stop_gib"],
            "poll_seconds": config["memory_poll_interval_seconds"],
        },
    }


def gamma2_sanity(results: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    existing = {
        "pure_benders": read_json(EXISTING_L_ROOT / "PURE_BENDERS/result.json"),
        "aggregate_benders_structured_oracle": read_json(
            EXISTING_L_ROOT / "AGGREGATE_BENDERS_STRUCTURED_ORACLE/result.json"
        ),
        "prb_benders": read_json(EXISTING_L_ROOT / "PRB_BENDERS/result.json"),
    }
    checks = []
    tolerance = float(config["gamma2_sanity_objective_tolerance"])
    for row in results:
        reference = existing[row["method"]]
        difference = abs(float(row["objective"]) - float(reference["solution"]["objective"]))
        checks.append(
            {
                "method": row["method"],
                "objective_difference": difference,
                "certified": row.get("certified") is True,
                "pass": difference <= tolerance and row.get("certified") is True,
            }
        )
    return {"pass": all(row["pass"] for row in checks), "checks": checks}


def run_all() -> None:
    config, _, _ = validate_config()
    output = result_root(config)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite development result root: {output}")
    output.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "status": "RUNNING",
        "development_only": True,
        "paper_final_observation": False,
        "formal_optimization_runs": 0,
        "development_optimization_runs": 0,
        "results": rows,
    }
    try:
        for gamma in GAMMAS:
            gamma_rows = []
            for method in METHODS:
                row = run_worker_monitored(config, gamma, method)
                rows.append(row)
                gamma_rows.append(row)
                summary["development_optimization_runs"] += 1
            if gamma == 2:
                if not all(row.get("objective") is not None for row in gamma_rows):
                    raise RuntimeError("GAMMA2_SANITY_INCOMPLETE")
                sanity = gamma2_sanity(gamma_rows, config)
                summary["gamma2_sanity"] = sanity
                if not sanity["pass"]:
                    raise RuntimeError("GAMMA2_SANITY_FAILED")
        summary["status"] = "COMPLETE"
    except Exception as error:
        summary["status"] = "BLOCKED"
        summary["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write_json(output / "development_summary.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--worker", choices=METHODS)
    parser.add_argument("--gamma", type=int, choices=GAMMAS)
    args = parser.parse_args()
    if args.worker:
        if args.gamma is None:
            parser.error("--worker requires --gamma")
        worker(args.worker, args.gamma)
    elif args.dry_run:
        print(json.dumps(dry_run(), indent=2))
    elif args.run_all:
        run_all()
    else:
        parser.error("choose --dry-run or --run-all")


if __name__ == "__main__":
    main()
