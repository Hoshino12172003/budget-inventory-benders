from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
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
)
from robust_inventory_reconfiguration.exact_benchmark import solve_exact_benchmark
from robust_inventory_reconfiguration.instance import load_instance, save_instance
from robust_inventory_reconfiguration.nominal_baseline import (
    baseline_feasibility,
    solve_canonical_nominal_baseline,
)
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.pure_benders import solve_pure_benders
from robust_inventory_reconfiguration.standard_benders import solve_standard_benders


AUTHORIZATION = ROOT / "experiments/configs/e1c_development_probe_authorization.json"
OUTPUT_ROOT = ROOT / "experiments/results/e1c_development_probe_v1"
SOURCE_CASES = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")
METHODS = (
    "pure_benders",
    "prb_benders",
    "aggregate_benders_structured_oracle",
    "direct_exact",
)
SCALES = {
    "L": ScalingDimensions("L", 25, 24, 12),
    "XL_low": ScalingDimensions("XL_low", 30, 30, 14),
}


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


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def hardware() -> dict[str, object]:
    memory = psutil.virtual_memory()
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "physical_memory_gib": memory.total / 2**30,
    }


def validate_authorization() -> dict[str, Any]:
    authorization = read_json(AUTHORIZATION)
    if authorization.get("development_probe_authorized") is not True:
        raise PermissionError("E1C_DEVELOPMENT_PROBE_NOT_AUTHORIZED")
    if authorization.get("formal_run_authorized") is not False:
        raise RuntimeError("E1c formal authorization must remain false")
    if authorization.get("seed") != 20260911 or authorization.get("Gamma") != 2:
        raise RuntimeError("E1c development seed/Gamma identity changed")
    if tuple(authorization.get("method_order", ())) != METHODS:
        raise RuntimeError("E1c development method order changed")
    expected = [asdict(SCALES[name]) for name in ("L", "XL_low")]
    expected = [
        {"scale": row["scale"], "I": row["depots"], "R": row["regions"], "J": row["products"]}
        for row in expected
    ]
    if authorization.get("authorized_instances") != expected:
        raise RuntimeError("E1c development scale identity changed")
    if authorization.get("timeout_seconds_per_method") != 900:
        raise RuntimeError("E1c timeout changed")
    if authorization.get("minimum_available_memory_gib_before_launch") != 18:
        raise RuntimeError("E1c preflight threshold changed")
    if authorization.get("process_memory_hard_stop_gib") != 14:
        raise RuntimeError("E1c process-memory stop changed")
    if authorization.get("system_available_memory_emergency_stop_gib") != 3:
        raise RuntimeError("E1c emergency stop changed")
    if authorization.get("memory_poll_interval_seconds_max") < 0.25:
        raise RuntimeError("E1c monitoring interval contract is invalid")
    return authorization


def preflight(authorization: dict[str, Any]) -> list[float]:
    threshold = float(authorization["minimum_available_memory_gib_before_launch"])
    samples = []
    for index in range(int(authorization["preflight_consecutive_samples"])):
        available = psutil.virtual_memory().available / 2**30
        samples.append(available)
        if available < threshold:
            raise RuntimeError(
                f"E1C_RESOURCE_PREFLIGHT_BLOCKED: {available:.6f} GiB < {threshold:.6f} GiB"
            )
        if index + 1 < int(authorization["preflight_consecutive_samples"]):
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
            resident = int(info.rss)
            private = int(getattr(info, "private", 0))
            total += max(resident, private)
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


def monitored_worker(
    authorization: dict[str, Any], scale: str, task: str, target: Path
) -> dict[str, Any]:
    samples = preflight(authorization)
    if target.exists() or target.with_name(f".{target.name}.partial").exists():
        raise FileExistsError(f"refusing to overwrite development artifact: {target}")
    partial = target.with_name(f".{target.name}.partial")
    partial.mkdir(parents=True)
    stdout_path = partial / "worker.stdout.log"
    stderr_path = partial / "worker.stderr.log"
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", task, "--scale", scale]
    started = perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(command, cwd=partial, stdout=stdout, stderr=stderr)
        peak = 0.0
        stop_status = None
        while process.poll() is None:
            current = process_tree_memory_gib(process.pid)
            peak = max(peak, current)
            available = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - started
            if current >= float(authorization["process_memory_hard_stop_gib"]):
                stop_status = "RESOURCE_STOP"
            elif available <= float(authorization["system_available_memory_emergency_stop_gib"]):
                stop_status = "RESOURCE_STOP"
            elif elapsed >= float(authorization["timeout_seconds_per_method"]):
                stop_status = "TIME_LIMIT"
            if stop_status is not None:
                terminate_tree(process.pid)
                break
            sleep(0.25)
        return_code = process.poll()
    elapsed = perf_counter() - started
    if stop_status is not None:
        write_json(
            partial / "result.json",
            {
                "scale": scale,
                "task": task,
                "status": stop_status,
                "development_only": True,
                "paper_final_observation": False,
                "preflight_available_memory_gib": samples,
                "peak_process_tree_memory_gib": peak,
                "monitor_wall_clock_seconds": elapsed,
            },
        )
    elif return_code != 0:
        write_json(
            partial / "result.json",
            {
                "scale": scale,
                "task": task,
                "status": "ERROR",
                "development_only": True,
                "paper_final_observation": False,
                "preflight_available_memory_gib": samples,
                "peak_process_tree_memory_gib": peak,
                "monitor_wall_clock_seconds": elapsed,
                "worker_return_code": return_code,
            },
        )
    else:
        result = read_json(partial / "result.json")
        result.update(
            {
                "preflight_available_memory_gib": samples,
                "peak_process_tree_memory_gib": peak,
                "monitor_wall_clock_seconds": elapsed,
            }
        )
        write_json(partial / "result.json", result)
    shutil.move(str(partial), str(target))
    return read_json(target / "result.json")


def source_instances():
    return [load_instance(ROOT / f"data/formal_instances_v2/{case}.json") for case in SOURCE_CASES]


def worker_prepare(scale: str, target: Path) -> None:
    dimensions = SCALES[scale]
    started = perf_counter()
    primitive = build_renault_calibrated_instance(source_instances(), dimensions, 20260911)
    primitive_hash = canonical_hash(primitive.to_dict())
    canonical = solve_canonical_nominal_baseline(primitive)
    feasibility = baseline_feasibility(primitive, canonical.baseline)
    if not feasibility["capacity_compatible"] or not feasibility["ub_compatible"]:
        raise RuntimeError("generated nominal incumbent failed feasibility audit")
    instance = replace(primitive, initial_inventory=canonical.baseline.x)
    save_instance(instance, target / "instance.json")
    write_json(
        target / "baseline.json",
        {
            "development_only": True,
            "paper_final_observation": False,
            "scale": scale,
            "seed": 20260911,
            "Gamma": 2,
            "primitive_instance_hash": primitive_hash,
            "instance_hash": canonical_hash(instance.to_dict()),
            "x0_hash": canonical_hash(canonical.baseline.x),
            "B_ref": canonical.baseline.first_stage_spending,
            "nominal_objective": canonical.baseline.objective,
            "nominal_recourse": canonical.baseline.recourse_cost,
            "canonical_rule": canonical.rule,
            "canonical_objective_delta": canonical.objective_delta,
            "nominal_solver_optimize_calls": canonical.solve_count,
            "feasibility": feasibility,
            "preparation_runtime_seconds": perf_counter() - started,
        },
    )
    write_json(
        target / "result.json",
        {
            "scale": scale,
            "task": "prepare",
            "status": "OPTIMAL",
            "construction_status": "COMPLETE",
            "exact_certification": True,
            "development_only": True,
            "paper_final_observation": False,
            "core_runtime_seconds": perf_counter() - started,
            "solver_optimize_calls": canonical.solve_count,
        },
    )


def solution_payload(solution) -> dict[str, object]:
    return {
        "objective": solution.objective,
        "first_stage_expenditure": solution.first_stage_expenditure,
        "robust_recourse_cost": solution.robust_recourse_cost,
        "reconfiguration_cost": solution.reconfiguration_cost,
        "y": solution.y,
        "x": solution.x,
        "a_plus": solution.a_plus,
        "a_minus": solution.a_minus,
    }


def worker_method(scale: str, method: str, target: Path) -> None:
    prepared = OUTPUT_ROOT / scale / "PREPARE"
    instance = load_instance(prepared / "instance.json")
    baseline = read_json(prepared / "baseline.json")
    x0 = instance.initial_inventory
    if x0 is None:
        raise RuntimeError("prepared development instance has no x0")
    budget = float(baseline["B_ref"])
    size = scaling_size(SCALES[scale], gamma=2)
    started = perf_counter()
    common = {
        "scale": scale,
        "method": method,
        "development_only": True,
        "paper_final_observation": False,
        "seed": 20260911,
        "Gamma": 2,
        "beta": 1.0,
        "lambda_R": 0.05,
        "B_ref": budget,
        "construction_status": "COMPLETE",
        "timeout": False,
        "resource_stop": False,
        "solver_version": ".".join(map(str, __import__("gurobipy").gurobi.version())),
        "git_commit": git_commit(),
        "hardware": hardware(),
    }
    if method == "pure_benders":
        solved = solve_pure_benders(
            instance,
            x0,
            budget,
            2,
            0.05,
            relative_gap_tolerance=1e-6,
            cut_tolerance=1e-7,
            objective_certification_tolerance=1e-4,
            max_iterations=500,
            time_limit=900,
            log_file=target / "solver.log",
        )
        result = {
            **common,
            "status": solved.status,
            "exact_certification": solved.exact_certification_pass and solved.cut_validity_pass,
            "core_runtime_seconds": solved.total_runtime,
            "master_runtime_seconds": solved.master_runtime,
            "oracle_runtime_seconds": solved.global_oracle_runtime,
            "certification_runtime_seconds": solved.certification_runtime,
            "iterations": len(solved.iterations),
            "cuts": solved.aggregate_cut_count,
            "model_variable_count": size["pure_total_variables"],
            "model_constraint_count": size["pure_constraints"],
            "solution": solution_payload(solved.solution),
        }
    elif method == "prb_benders":
        solved = solve_prb_benders(
            instance,
            x0,
            budget,
            2,
            0.05,
            relative_gap_tolerance=1e-6,
            cut_tolerance=1e-7,
            max_iterations=500,
        )
        result = {
            **common,
            "status": solved.status,
            "exact_certification": solved.exact_certification_pass,
            "global_coupling_pass": solved.global_risk_budget_coupling_pass,
            "core_runtime_seconds": solved.total_runtime,
            "master_runtime_seconds": solved.master_runtime,
            "oracle_runtime_seconds": solved.separation_runtime,
            "certification_runtime_seconds": solved.certification_runtime,
            "iterations": len(solved.iterations),
            "cuts": solved.unique_product_cuts,
            "model_variable_count": size["first_stage_variables"] + size["prb_master_surrogates"],
            "model_constraint_count": (
                instance.num_depots
                + 2 * instance.num_depots * instance.num_products
                + 1
                + len(__import__("robust_inventory_reconfiguration.risk_budget_composition", fromlist=["enumerate_gamma_allocations"]).enumerate_gamma_allocations(instance.num_products, 2))
                + solved.unique_product_cuts
            ),
            "product_risk_blocks": size["prb_product_risk_blocks"],
            "solution": solution_payload(solved.solution),
        }
    elif method == "aggregate_benders_structured_oracle":
        solved = solve_standard_benders(
            instance,
            x0,
            budget,
            2,
            0.05,
            relative_gap_tolerance=1e-6,
            cut_tolerance=1e-7,
            objective_certification_tolerance=1e-4,
            max_iterations=500,
            time_limit=900,
            log_file=target / "solver.log",
        )
        result = {
            **common,
            "status": solved.status,
            "exact_certification": solved.exact_certification_pass and solved.cut_validity_pass,
            "core_runtime_seconds": solved.total_runtime,
            "master_runtime_seconds": solved.master_runtime,
            "oracle_runtime_seconds": solved.oracle_runtime,
            "cut_construction_runtime_seconds": solved.cut_construction_runtime,
            "certification_runtime_seconds": solved.certification_runtime,
            "iterations": len(solved.iterations),
            "cuts": solved.aggregate_cut_count,
            "model_variable_count": size["first_stage_variables"] + 1,
            "model_constraint_count": (
                instance.num_depots
                + 2 * instance.num_depots * instance.num_products
                + 1
                + solved.aggregate_cut_count
            ),
            "product_risk_blocks": size["prb_product_risk_blocks"],
            "solution": solution_payload(solved.solution),
        }
    elif method == "direct_exact":
        solved = solve_exact_benchmark(
            instance,
            x0,
            budget,
            2,
            0.05,
            time_limit=900,
            log_file=target / "solver.log",
        )
        result = {
            **common,
            "status": solved.status,
            "exact_certification": solved.status == "OPTIMAL" and solved.mip_gap == 0,
            "core_runtime_seconds": perf_counter() - started,
            "solver_runtime_seconds": solved.runtime,
            "master_runtime_seconds": None,
            "oracle_runtime_seconds": None,
            "iterations": None,
            "cuts": None,
            "model_variable_count": solved.variable_count,
            "model_constraint_count": solved.constraint_count,
            "solution": solution_payload(solved.solution) if solved.solution else None,
        }
    else:
        raise ValueError(f"unsupported method: {method}")
    write_json(target / "result.json", result)


def worker(task: str, scale: str) -> None:
    target = Path.cwd()
    if task == "prepare":
        worker_prepare(scale, target)
    elif task in METHODS:
        worker_method(scale, task, target)
    else:
        raise ValueError(f"unsupported worker task: {task}")


def dry_run() -> dict[str, object]:
    authorization = validate_authorization()
    return {
        "status": "DRY_RUN_PASS",
        "optimization_calls": 0,
        "authorized_scales": [asdict(SCALES[name]) for name in ("L", "XL_low")],
        "method_order": list(METHODS),
        "seed": authorization["seed"],
        "Gamma": authorization["Gamma"],
        "timeout_seconds": authorization["timeout_seconds_per_method"],
        "memory_gate": {
            "preflight_gib": authorization["minimum_available_memory_gib_before_launch"],
            "process_stop_gib": authorization["process_memory_hard_stop_gib"],
            "system_emergency_gib": authorization["system_available_memory_emergency_stop_gib"],
        },
    }


def run_all() -> None:
    authorization = validate_authorization()
    if OUTPUT_ROOT.exists():
        raise FileExistsError(f"refusing to overwrite development result root: {OUTPUT_ROOT}")
    OUTPUT_ROOT.mkdir(parents=True)
    summary: list[dict[str, Any]] = []
    try:
        for scale in ("L", "XL_low"):
            scale_root = OUTPUT_ROOT / scale
            preparation = monitored_worker(
                authorization, scale, "prepare", scale_root / "PREPARE"
            )
            summary.append(preparation)
            if preparation["status"] != "OPTIMAL":
                continue
            for method in METHODS:
                result = monitored_worker(
                    authorization, scale, method, scale_root / method.upper()
                )
                summary.append(result)
        write_json(
            OUTPUT_ROOT / "development_summary.json",
            {
                "status": "COMPLETE",
                "development_only": True,
                "paper_final_observation": False,
                "formal_optimization_runs": 0,
                "development_top_level_runs": len(summary),
                "results": summary,
            },
        )
    except Exception as error:
        write_json(
            OUTPUT_ROOT / "development_summary.json",
            {
                "status": "BLOCKED",
                "development_only": True,
                "paper_final_observation": False,
                "formal_optimization_runs": 0,
                "development_top_level_runs": len(summary),
                "results": summary,
                "error": f"{type(error).__name__}: {error}",
            },
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--worker", choices=("prepare", *METHODS))
    parser.add_argument("--scale", choices=tuple(SCALES))
    args = parser.parse_args()
    if args.worker:
        if args.scale is None:
            parser.error("--worker requires --scale")
        worker(args.worker, args.scale)
    elif args.dry_run:
        print(json.dumps(dry_run(), indent=2))
    elif args.run_all:
        run_all()
    else:
        parser.error("choose --dry-run or --run-all")


if __name__ == "__main__":
    main()
