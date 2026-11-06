"""Same-environment Basic PRB vs Accelerated PRB V2 on frozen Renault cases.

This runner is intentionally isolated from historical E1 and Scaling30 outputs.
Each condition is solved in its own monitored process and written atomically.
Original strict certification remains authoritative; the optional independent
numerical audit is reported as a separate, narrower evidence class.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
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
from uuid import uuid4

import psutil


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
EXPERIMENTS = ROOT / "experiments"
for candidate in (str(SRC), str(EXPERIMENTS)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from run_renault_vanilla_bd_pilot import CASE_IDS, load_frozen_renault_case
from run_prb_basic_v2_fair_scaling30_numeric_guard_v1 import (
    independent_audit,
    numerical_policy,
)


EXPERIMENT_ID = "RENAULT8_PRB_V2_PAIRED_V1"
DEVELOPMENT_BASE_COMMIT = "dfca83faa1d334f22e2e7a83dcf50f69761e300f"
METHODS = ("basic", "v2")
GAMMA = 2
BETA = 1.0
LAMBDA_R = 0.05
RELATIVE_GAP_TOLERANCE = 1e-6
CUT_TOLERANCE = 1e-7
MAX_ITERATIONS = 500
OBJECTIVE_TOLERANCE = 1e-4
V2_WORKERS = 2
GUROBI_THREADS = 1
CONDITION_TIMEOUT_SECONDS = 900.0
MONITOR_INTERVAL_SECONDS = 0.25
MIN_AVAILABLE_MEMORY_GIB = 7.0
MAX_PROCESS_TREE_MEMORY_GIB = 4.0
SYSTEM_MEMORY_FLOOR_GIB = 3.0
OUTPUT_ROOT = ROOT / "experiments/results/renault8_prb_v2_paired_v1"
DIRECT_REFERENCE = ROOT / "table_e1_empirical_performance.csv"
EXPECTED_PYTHON = "3.12.7"
EXPECTED_GUROBI = (13, 0, 1)

CODE_PATHS = (
    "experiments/run_renault8_prb_v2_paired_v1.py",
    "experiments/run_renault_vanilla_bd_pilot.py",
    "experiments/run_prb_basic_v2_fair_scaling30_numeric_guard_v1.py",
    "src/robust_inventory_reconfiguration/instance.py",
    "src/robust_inventory_reconfiguration/product_risk_budget_benders.py",
    "src/robust_inventory_reconfiguration/product_risk_subproblem.py",
    "src/robust_inventory_reconfiguration/accelerated_product_risk_budget_benders.py",
    "src/robust_inventory_reconfiguration/accelerated_product_risk_subproblem.py",
    "src/robust_inventory_reconfiguration/risk_budget_composition.py",
    "src/robust_inventory_reconfiguration/reconfiguration_model.py",
    "src/robust_inventory_reconfiguration/solver_profile.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def code_hashes() -> dict[str, str]:
    return {relative: sha256(ROOT / relative) for relative in CODE_PATHS}


def environment() -> dict[str, object]:
    import gurobipy as gp
    import numpy

    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "gurobi": list(gp.gurobi.version()),
        "gurobipy": getattr(gp, "__version__", ".".join(map(str, gp.gurobi.version()))),
        "numpy": numpy.__version__,
        "psutil": psutil.__version__,
        "cpu": platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "physical_memory_gib": psutil.virtual_memory().total / 2**30,
    }


def validate_environment() -> dict[str, object]:
    current = environment()
    failures = []
    if current["python"] != EXPECTED_PYTHON:
        failures.append(f"python={current['python']} expected={EXPECTED_PYTHON}")
    if tuple(current["gurobi"]) != EXPECTED_GUROBI:
        failures.append(f"gurobi={current['gurobi']} expected={list(EXPECTED_GUROBI)}")
    if not str(current["os"]).startswith("Windows-11-"):
        failures.append(f"os={current['os']} expected=Windows 11")
    if failures:
        raise RuntimeError("ENVIRONMENT_MISMATCH: " + "; ".join(failures))
    return current


def direct_reference(case_id: str, loaded: dict[str, Any]) -> dict[str, object]:
    with DIRECT_REFERENCE.open(encoding="utf-8", newline="") as stream:
        rows = {row["case"]: row for row in csv.DictReader(stream)}
    row = rows.get(case_id)
    if row is None:
        raise RuntimeError(f"missing frozen Direct objective for Renault {case_id}")
    if row["instance_hash"] != loaded["identity"]["instance_hash"]:
        raise RuntimeError(f"Direct reference instance mismatch for Renault {case_id}")
    if row["x0_hash"] != loaded["identity"]["x0_hash"]:
        raise RuntimeError(f"Direct reference x0 mismatch for Renault {case_id}")
    return {
        "objective": float(row["direct_objective"]),
        "source": str(DIRECT_REFERENCE.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": sha256(DIRECT_REFERENCE),
        "historical_status": row["direct_optimality_status"],
    }


def condition_id(case_id: str, method: str) -> str:
    return f"RENAULT_{case_id}_{method.upper()}"


def result_dir(case_id: str, method: str) -> Path:
    return OUTPUT_ROOT / "runs" / condition_id(case_id, method)


def identity(
    case_id: str,
    method: str,
    workers: int,
    loaded: dict[str, Any],
    reference: dict[str, object],
) -> dict[str, object]:
    return {
        "experiment": EXPERIMENT_ID,
        "case": case_id,
        "method": method,
        "git_development_base": DEVELOPMENT_BASE_COMMIT,
        "code_sha256": code_hashes(),
        "input_sha256": loaded["identity"],
        "input_paths": {
            key: str(Path(value).relative_to(ROOT)).replace("\\", "/")
            for key, value in loaded["paths"].items()
        },
        "direct_reference": reference,
        "Gamma": GAMMA,
        "beta": BETA,
        "lambda_R": LAMBDA_R,
        "relative_gap_tolerance": RELATIVE_GAP_TOLERANCE,
        "cut_tolerance": CUT_TOLERANCE,
        "max_iterations": MAX_ITERATIONS,
        "objective_comparison_tolerance": OBJECTIVE_TOLERANCE,
        "solver_profile": "gurobi-balanced-1e-8-v1",
        "gurobi_threads_per_model": GUROBI_THREADS,
        "method_workers": 1 if method == "basic" else workers,
        "v2_backend": None if method == "basic" else "process",
        "v2_selective_separation": None if method == "basic" else False,
        "environment": validate_environment(),
    }


def verified_result(path: Path, expected_identity: dict[str, object]) -> bool:
    if not path.exists():
        return False
    result_path = path / "result.json"
    provenance_path = path / "provenance.json"
    if not result_path.is_file() or not provenance_path.is_file():
        raise RuntimeError(f"partial result; refusing overwrite: {path}")
    result = read_json(result_path)
    provenance = read_json(provenance_path)
    valid_classes = {
        "strict_original",
        "independently_numerically_validated",
        "FAILED",
    }
    if (
        provenance.get("identity") != expected_identity
        or provenance.get("result_sha256") != sha256(result_path)
        or result.get("condition_completed") is not True
        or result.get("certification_class") not in valid_classes
    ):
        raise RuntimeError(f"incompatible or damaged result; refusing reuse: {path}")
    return True


def run_child(case_id: str, method: str, workers: int) -> None:
    import gurobipy as gp
    from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import (
        solve_accelerated_prb_benders,
    )
    from robust_inventory_reconfiguration.product_risk_budget_benders import (
        solve_prb_benders,
    )

    loaded = load_frozen_renault_case(case_id)
    reference = direct_reference(case_id, loaded)
    expected_identity = identity(case_id, method, workers, loaded, reference)
    target = result_dir(case_id, method)
    if verified_result(target, expected_identity):
        print(f"[VERIFIED SKIP] {condition_id(case_id, method)}", flush=True)
        return

    gp.setParam("Threads", GUROBI_THREADS)
    common = {
        "relative_gap_tolerance": RELATIVE_GAP_TOLERANCE,
        "cut_tolerance": CUT_TOLERANCE,
        "max_iterations": MAX_ITERATIONS,
    }
    args = (
        loaded["instance"],
        loaded["x0"],
        loaded["budget"],
        GAMMA,
        LAMBDA_R,
    )
    started = perf_counter()
    if method == "basic":
        solved = solve_prb_benders(*args, **common)
        method_workers = 1
    elif method == "v2":
        solved = solve_accelerated_prb_benders(
            *args,
            parallel_workers=workers,
            _oracle_backend="process",
            _selective_separation=False,
            **common,
        )
        method_workers = int(solved.parallel_worker_count)
    else:
        raise ValueError(method)
    child_solve_wall = perf_counter() - started

    reference_objective = float(reference["objective"])
    preliminary = numerical_policy(solved, reference_objective, None)
    audit = None
    if not preliminary["strict_original_certification"]:
        audit = independent_audit(loaded["instance"], solved)
    certification = numerical_policy(solved, reference_objective, audit)
    objective = float(solved.solution.objective)
    objective_difference = abs(objective - reference_objective)
    objective_match = objective_difference <= OBJECTIVE_TOLERANCE

    result = {
        "experiment": EXPERIMENT_ID,
        "condition_id": condition_id(case_id, method),
        "condition_completed": True,
        "case": case_id,
        "method": method,
        "solver_status": solved.status,
        "objective": objective,
        "historical_direct_objective": reference_objective,
        "objective_absolute_difference": objective_difference,
        "objective_reference_match": objective_match,
        "final_lower_bound": float(solved.final_lower_bound),
        "final_upper_bound": float(solved.final_upper_bound),
        "relative_gap": float(solved.final_relative_gap),
        "core_solve_time_seconds": float(solved.total_runtime),
        "child_solve_wall_seconds": child_solve_wall,
        "master_time_seconds": float(solved.master_runtime),
        "oracle_time_seconds": float(solved.separation_runtime),
        "certification_time_seconds": float(solved.certification_runtime),
        "iterations": len(solved.iterations),
        "benders_cut_count": int(solved.unique_product_cuts),
        "master_solve_count": int(solved.master_solve_count),
        "worker_count": method_workers,
        "gurobi_threads_per_model": GUROBI_THREADS,
        "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        "python_version": platform.python_version(),
        "Gamma": GAMMA,
        "beta": BETA,
        "lambda_R": LAMBDA_R,
        "budget": loaded["budget"],
        "input_sha256": loaded["identity"],
        "first_stage_solution": asdict(solved.solution),
        "independent_numerical_audit": audit,
        **certification,
        "strict_exact_certification": certification["strict_original_certification"],
    }
    if method == "v2":
        result.update(
            {
                "cache_hits": int(solved.cache_hits),
                "cache_misses": int(solved.cache_misses),
                "product_solves_avoided": int(solved.product_solves_avoided),
                "oracle_model_build_seconds": float(solved.oracle_model_build_runtime),
                "selective_separation_enabled": bool(solved.selective_separation_enabled),
                "runtime_profile": solved.runtime_profile,
            }
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".tmp-{target.name}-{uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        result_path = temporary / "result.json"
        write_json(result_path, result)
        write_json(
            temporary / "provenance.json",
            {
                "identity": expected_identity,
                "result_sha256": sha256(result_path),
                "saved_at_utc": datetime.now(timezone.utc).isoformat(),
                "certification_class": result["certification_class"],
            },
        )
        if target.exists():
            raise FileExistsError(f"refusing overwrite: {target}")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)

    if solved.status != "OPTIMAL" or not bool(solved.exact_certification_pass):
        raise RuntimeError(f"MODEL_OR_EXACT_CERTIFICATION_FAILURE: {target}")
    if not objective_match:
        raise RuntimeError(f"DIRECT_OBJECTIVE_MISMATCH: {target}")
    if not result["validated_under_protocol"]:
        raise RuntimeError(f"UNEXPLAINED_CERTIFICATION_FAILURE: {target}")
    print(
        f"[{result['certification_class']}] {condition_id(case_id, method)} "
        f"{result['core_solve_time_seconds']:.3f}s",
        flush=True,
    )


def tree_rss_gib(pid: int) -> float:
    try:
        parent = psutil.Process(pid)
        processes = [parent, *parent.children(recursive=True)]
    except psutil.Error:
        return 0.0
    total = 0
    for process in processes:
        try:
            total += process.memory_info().rss
        except psutil.Error:
            pass
    return total / 2**30


def terminate_tree(pid: int) -> None:
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


def monitored_run(case_id: str, method: str, workers: int) -> None:
    loaded = load_frozen_renault_case(case_id)
    reference = direct_reference(case_id, loaded)
    expected_identity = identity(case_id, method, workers, loaded, reference)
    target = result_dir(case_id, method)
    if verified_result(target, expected_identity):
        print(f"[VERIFIED SKIP] {condition_id(case_id, method)}", flush=True)
        return

    available_before = psutil.virtual_memory().available / 2**30
    if available_before < MIN_AVAILABLE_MEMORY_GIB:
        raise RuntimeError(
            f"LOW_AVAILABLE_MEMORY: {available_before:.2f} < {MIN_AVAILABLE_MEMORY_GIB} GiB"
        )
    log_parent = OUTPUT_ROOT / "logs" / condition_id(case_id, method)
    attempt = 1
    while (log_parent / f"attempt-{attempt:03d}").exists():
        attempt += 1
    log_dir = log_parent / f"attempt-{attempt:03d}"
    log_dir.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker-condition",
        case_id,
        method,
        "--workers",
        str(workers),
    ]
    started = perf_counter()
    peak = 0.0
    stop_reason = None
    with (log_dir / "stdout.log").open("w", encoding="utf-8") as stdout, (
        log_dir / "stderr.log"
    ).open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            peak = max(peak, tree_rss_gib(process.pid))
            available_now = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - started
            if peak >= MAX_PROCESS_TREE_MEMORY_GIB:
                stop_reason = (
                    f"PROCESS_MEMORY_CAP: {peak:.2f} >= "
                    f"{MAX_PROCESS_TREE_MEMORY_GIB} GiB"
                )
            elif available_now <= SYSTEM_MEMORY_FLOOR_GIB:
                stop_reason = f"SYSTEM_MEMORY_FLOOR: {available_now:.2f} GiB"
            elif elapsed >= CONDITION_TIMEOUT_SECONDS:
                stop_reason = "TIME_LIMIT"
            if stop_reason:
                terminate_tree(process.pid)
                break
            sleep(MONITOR_INTERVAL_SECONDS)
        return_code = process.poll()
    record = {
        "condition_id": condition_id(case_id, method),
        "attempt": attempt,
        "command": command,
        "return_code": return_code,
        "stop_reason": stop_reason,
        "available_memory_before_gib": available_before,
        "peak_process_tree_rss_gib": peak,
        "monitored_wall_seconds": perf_counter() - started,
        "poll_interval_seconds": MONITOR_INTERVAL_SECONDS,
        "process_memory_cap_gib": MAX_PROCESS_TREE_MEMORY_GIB,
        "system_memory_floor_gib": SYSTEM_MEMORY_FLOOR_GIB,
    }
    write_json(log_dir / "monitor.json", record)
    if stop_reason or return_code != 0:
        raise RuntimeError(
            f"FAILED {condition_id(case_id, method)}: {stop_reason or return_code}; "
            f"see {log_dir}"
        )
    if not verified_result(target, expected_identity):
        raise RuntimeError(f"worker produced no complete result: {target}")
    print(
        f"[DONE] {condition_id(case_id, method)} peak={peak:.3f} GiB",
        flush=True,
    )


def validate_case(case_id: str, workers: int) -> dict[str, object]:
    loaded = load_frozen_renault_case(case_id)
    reference = direct_reference(case_id, loaded)
    identities = {
        method: identity(case_id, method, workers, loaded, reference)
        for method in METHODS
    }
    return {
        "case": case_id,
        "depots": loaded["instance"].num_depots,
        "regions": loaded["instance"].num_regions,
        "products": loaded["instance"].num_products,
        "budget": loaded["budget"],
        "input_sha256": loaded["identity"],
        "direct_objective": reference["objective"],
        "condition_ids": [condition_id(case_id, method) for method in METHODS],
        "identity_sha256": {
            method: hashlib.sha256(
                json.dumps(identities[method], sort_keys=True).encode("utf-8")
            ).hexdigest()
            for method in METHODS
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitored Renault8 Basic PRB vs Accelerated PRB V2 pairing"
    )
    scope = parser.add_mutually_exclusive_group(required=False)
    scope.add_argument("--case", choices=CASE_IDS)
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=V2_WORKERS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--worker-condition",
        nargs=2,
        metavar=("CASE", "METHOD"),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.workers != V2_WORKERS:
        parser.error("this frozen protocol requires --workers 2")
    if args.worker_condition:
        case_id, method = args.worker_condition
        if case_id not in CASE_IDS or method not in METHODS:
            parser.error("invalid worker condition")
        run_child(case_id, method, args.workers)
        return
    if not args.case and not args.all:
        parser.error("select --case CASE or --all")

    validate_environment()
    cases = CASE_IDS if args.all else (args.case,)
    for case_id in cases:
        audit = validate_case(case_id, args.workers)
        if args.dry_run:
            print(
                f"[READY] {case_id} I/R/J={audit['depots']}/{audit['regions']}/"
                f"{audit['products']} instance={audit['input_sha256']['instance_hash'][:12]}",
                flush=True,
            )
            continue
        index = CASE_IDS.index(case_id)
        ordering = METHODS if index % 2 == 0 else METHODS[::-1]
        for method in ordering:
            monitored_run(case_id, method, args.workers)
    if not args.dry_run:
        print("[FINISHED] requested Renault pair(s) completed or verified", flush=True)


if __name__ == "__main__":
    main()
