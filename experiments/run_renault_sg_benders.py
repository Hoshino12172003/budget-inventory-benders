from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
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
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.run_renault_enhanced_basic_benders import (
    load_frozen_renault_case,
    process_tree_rss,
    sha256,
    stop_process_tree,
    write_json,
)
from robust_inventory_reconfiguration.enhanced_basic_benders import (
    EnhancedGlobalEnumeratedLPOracle,
)
from robust_inventory_reconfiguration.scenario_generation_benders import (
    solve_scenario_generation_benders,
)


DEFAULT_CONFIG = ROOT / "experiments/configs/development/renault_sg_benders_v1.yaml"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
CONDITIONS = tuple(f"SG_RENAULT_{case}" for case in CASES)
ALLOWED_PREEXISTING_STATUS_PREFIX = "?? experiments/results/basic_benders_scaling_development_v1/"


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("protocol_id") != "RENAULT_SG_BD_8CASE_V1":
        raise RuntimeError("unexpected SG-BD protocol identity")
    if tuple(config.get("case_ids", ())) != CASES:
        raise RuntimeError("SG-BD case scope differs from the frozen Renault order")
    if tuple(config.get("authorized_condition_ids", ())) != CONDITIONS:
        raise RuntimeError("SG-BD condition allowlist differs from the frozen scope")
    if config.get("fixed_scientific_parameters") != {"Gamma": 2, "lambda_R": 0.05}:
        raise RuntimeError("SG-BD scientific parameters differ from the frozen protocol")
    return config


def reference_payload(config: dict[str, Any], key: str) -> tuple[Path, Any]:
    reference = config[key]
    path = ROOT / reference["path"]
    if sha256(path) != reference["sha256"]:
        raise RuntimeError(f"HASH_FAILURE: frozen reference changed: {path}")
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as stream:
            return path, list(csv.DictReader(stream))
    return path, json.loads(path.read_text(encoding="utf-8"))


def condition_identity(config: dict[str, Any], case: str) -> dict[str, Any]:
    _, identity_config = reference_payload(config, "frozen_identity_reference")
    _, direct_rows = reference_payload(config, "frozen_direct_reference")
    direct = next(row for row in direct_rows if row["case"] == case)
    loaded = load_frozen_renault_case(case)
    instance = loaded["instance"]
    total_scenarios = sum(
        math.comb(instance.num_regions * instance.num_products, size)
        for size in range(loaded["gamma"] + 1)
    )
    expected = identity_config["frozen_case_identity"][case]
    checks = {
        key: loaded["identity"][key] == expected[key]
        for key in ("instance_hash", "x0_hash", "calibration_hash", "mapping_hash")
    }
    checks.update({
        "direct_instance_hash": direct["instance_hash"] == loaded["identity"]["instance_hash"],
        "direct_x0_hash": direct["x0_hash"] == loaded["identity"]["x0_hash"],
        "direct_exact": direct["direct_optimality_status"] == "CERTIFIED_EXACT",
        "Gamma": loaded["gamma"] == 2,
        "lambda_R": loaded["lambda_r"] == 0.05,
        "scenario_count": total_scenarios == 4657,
        "scenario_cap": total_scenarios <= config["algorithm"]["maximum_global_scenarios"],
    })
    return {
        "case_id": case,
        "condition_id": f"SG_RENAULT_{case}",
        "identity": loaded["identity"],
        "direct_objective": float(direct["direct_objective"]),
        "total_scenarios": total_scenarios,
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


def active_workers() -> list[dict[str, Any]]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or []).lower()
            name = (process.info.get("name") or "").lower()
            if name.startswith("gurobi") or (
                "run_renault_sg_benders.py" in command and "--worker" in command
            ):
                found.append({"pid": process.info["pid"], "name": process.info.get("name")})
        except psutil.Error:
            pass
    return found


def git_status_for_execution(output_root: Path) -> dict[str, Any]:
    lines = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).splitlines()
    output_prefix = f"?? {output_root.relative_to(ROOT).as_posix()}/"
    unexpected = [
        line for line in lines
        if not line.startswith(ALLOWED_PREEXISTING_STATUS_PREFIX)
        and not line.startswith(output_prefix)
    ]
    return {"entries": lines, "unexpected_entries": unexpected, "pass": not unexpected}


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    import gurobipy as gp

    config_path = config_path.resolve()
    config = load_config(config_path)
    output_root = ROOT / config["output_directory"]
    conditions = []
    for case in CASES:
        row = condition_identity(config, case)
        condition = row["condition_id"]
        row.update({
            "expected_attempt": "attempt-001",
            "attempt_exists": (output_root / "worker_logs" / condition / "attempt-001").exists(),
            "canonical_exists": (output_root / "runs" / condition).exists(),
        })
        conditions.append(row)
    resources = config["resource_policy"]
    available = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output_root.parent).free / 2**30
    workers = active_workers()
    git = git_status_for_execution(output_root)
    gates = {
        "all_case_identities": all(row["status"] == "PASS" for row in conditions),
        "all_attempts_absent": all(not row["attempt_exists"] for row in conditions),
        "all_canonical_results_absent": all(not row["canonical_exists"] for row in conditions),
        "startup_memory": available >= resources["minimum_available_memory_gib"],
        "disk": free_disk >= resources["minimum_free_disk_gib"],
        "git_status": git["pass"],
        "no_active_solver_worker": not workers,
    }
    return {
        "schema": "renault_sg_bd_dry_run_v1",
        "protocol_id": config["protocol_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "conditions": conditions,
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


def certify_solution(
    instance: Any,
    solution: Any,
    gamma: int,
    final_sg_trace: dict[str, Any],
    time_limit: float,
    tolerance: float,
) -> dict[str, Any]:
    oracle = EnhancedGlobalEnumeratedLPOracle(instance, gamma)
    try:
        certified = oracle.solve(solution.x, time_limit=time_limit)
    finally:
        oracle.close()
    certified_objective = solution.first_stage_expenditure + certified.value
    return {
        "certified_recourse": certified.value,
        "certified_objective": certified_objective,
        "objective_residual": abs(certified_objective - solution.objective),
        "sg_worst_value_residual": abs(certified.value - final_sg_trace["worst_recourse_value"]),
        "worst_pattern_equal": certified.cut.shock_pattern == tuple(
            tuple(pair) for pair in final_sg_trace["worst_pattern"]
        ),
        "eb_worst_pattern": certified.cut.shock_pattern,
        "sg_worst_pattern": final_sg_trace["worst_pattern"],
        "dual_feasible": certified.cut.dual_feasible,
        "strong_duality_residual": certified.cut.strong_duality_error,
        "pass": (
            certified.cut.dual_feasible
            and certified.cut.strong_duality_error <= tolerance
            and abs(certified_objective - solution.objective) <= tolerance
            and abs(certified.value - final_sg_trace["worst_recourse_value"]) <= tolerance
        ),
    }


def solve_condition(config_path: Path, condition_id: str, attempt_root: Path) -> dict[str, Any]:
    import gurobipy as gp

    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: Renault SG-BD execution is disabled")
    if condition_id not in CONDITIONS:
        raise RuntimeError("condition is outside the SG-BD allowlist")
    if attempt_root.exists():
        raise FileExistsError(f"refusing to overwrite attempt: {attempt_root}")
    attempt_root.mkdir(parents=True)
    case = condition_id.rsplit("_", 1)[1]
    identity = condition_identity(config, case)
    if identity["status"] != "PASS":
        raise RuntimeError(f"IDENTITY_FAILURE: {identity['checks']}")
    loaded = load_frozen_renault_case(case)
    trace_path = attempt_root / "oracle_trace.jsonl"
    started = perf_counter()
    solved, diagnostics = solve_scenario_generation_benders(
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
        trace_path=trace_path,
    )
    algorithm_seconds = perf_counter() - started
    traces = [
        json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if len(traces) != len(solved.iterations) + 1:
        raise RuntimeError("INTEGRITY_FAILURE: SG trace does not match master iterations plus final certification call")
    tolerance = config["solver_tolerances"]["objective_certification"]
    maximum_trace_dual_violation = max(
        trace["dual_feasibility_max_violation"] for trace in traces
    )
    maximum_trace_strong_duality_residual = max(
        trace["strong_duality_residual"] for trace in traces
    )
    maximum_trace_cut_anchor_residual = max(
        trace["cut_anchor_residual"] for trace in traces
    )
    trace_certification_pass = (
        maximum_trace_dual_violation <= 1e-7
        and maximum_trace_strong_duality_residual <= tolerance
        and maximum_trace_cut_anchor_residual <= tolerance
    )
    cut_anchor_residual = max(
        (abs(cut.value_at([list(row) for row in cut.generation_x]) - cut.generation_value) for cut in solved.cuts),
        default=0.0,
    )
    remaining = config["resource_policy"]["condition_time_limit_seconds"] - algorithm_seconds
    if remaining <= 0.0:
        raise TimeoutError("no time remains for independent full-enumeration certification")
    certification_started = perf_counter()
    independent = certify_solution(
        loaded["instance"], solved.solution, loaded["gamma"], traces[-1], remaining, tolerance
    )
    certification_seconds = perf_counter() - certification_started
    direct_residual = abs(solved.solution.objective - identity["direct_objective"])
    exact = bool(
        solved.status == "OPTIMAL"
        and solved.exact_certification_pass
        and solved.cut_validity_pass
        and trace_certification_pass
        and cut_anchor_residual <= tolerance
        and independent["pass"]
        and direct_residual <= tolerance
    )
    trajectory = []
    for iteration, trace in zip(solved.iterations, traces[:-1], strict=True):
        trajectory.append({
            **asdict(iteration),
            "first_stage_x": trace["first_stage_x"],
            "total_scenarios": trace["total_scenarios"],
            "exact_lp_solves": trace["exact_lp_solves"],
            "safely_pruned_scenarios": trace["safely_pruned_scenarios"],
            "pruning_fraction": trace["pruning_fraction"],
            "branch_nodes": trace["branch_nodes"],
            "upper_bound_seconds": trace["upper_bound_seconds"],
            "oracle_lp_optimize_seconds": trace["lp_optimize_seconds"],
            "worst_pattern": trace["worst_pattern"],
            "worst_recourse_value": trace["worst_recourse_value"],
        })
    first_stage = {
        "y": solved.solution.y,
        "x": solved.solution.x,
        "a_plus": solved.solution.a_plus,
        "a_minus": solved.solution.a_minus,
    }
    result = {
        "schema": "renault_sg_bd_result_v1",
        "experiment_id": config["experiment_id"],
        "protocol_id": config["protocol_id"],
        "condition_id": condition_id,
        "case_id": case,
        "attempt": "attempt-001",
        "method": "SG-BD",
        "solver_status": solved.status,
        "exact_certification": exact,
        "cut_validity": solved.cut_validity_pass and cut_anchor_residual <= tolerance,
        "objective": solved.solution.objective,
        "direct_objective": identity["direct_objective"],
        "direct_objective_residual": direct_residual,
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
        "maximum_cut_anchor_residual": cut_anchor_residual,
        "maximum_oracle_dual_feasibility_violation": maximum_trace_dual_violation,
        "maximum_oracle_strong_duality_residual": maximum_trace_strong_duality_residual,
        "maximum_oracle_cut_anchor_residual": maximum_trace_cut_anchor_residual,
        "all_oracle_calls_certified": trace_certification_pass,
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
        "schema": "renault_sg_bd_provenance_v1",
        "condition_id": condition_id,
        "attempt": "attempt-001",
        "formal_run_authorized": True,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "config_sha256": sha256(config_path),
        "implementation_sha256": sha256(ROOT / "src/robust_inventory_reconfiguration/scenario_generation_benders.py"),
        "bound_sha256": sha256(ROOT / "src/robust_inventory_reconfiguration/scenario_generation_single_cut.py"),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "result_sha256": sha256(attempt_root / "result.json"),
        "trajectory_sha256": sha256(attempt_root / "iteration_trajectory.json"),
        "oracle_trace_sha256": sha256(trace_path),
        "first_stage_sha256": sha256(attempt_root / "first_stage_solution.json"),
        "identity": loaded["identity"],
    }
    write_json(attempt_root / "provenance.json", provenance)
    if not exact:
        raise RuntimeError("NUMERICAL_CERTIFICATION_FAILURE: SG-BD result is not exact-certified")
    return result


def run_monitored(config_path: Path, condition_id: str) -> dict[str, Any]:
    config = load_config(config_path)
    output_root = ROOT / config["output_directory"]
    attempt = output_root / "worker_logs" / condition_id / "attempt-001"
    canonical = output_root / "runs" / condition_id
    if attempt.exists() or canonical.exists():
        raise FileExistsError(f"refusing to overwrite SG-BD evidence: {condition_id}")
    attempt.mkdir(parents=True)
    payload = attempt / "payload"
    command = [
        sys.executable, str(Path(__file__).resolve()), "--config", str(config_path),
        "--worker", condition_id, "--attempt-root", str(payload),
    ]
    resource = config["resource_policy"]
    started = perf_counter()
    peak = 0
    stop_reason = None
    samples = []
    with (attempt / "stdout.log").open("w", encoding="utf-8") as stdout, (
        attempt / "stderr.log"
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
    write_json(attempt / "resource_monitor.json", monitor)
    if return_code == 0 and stop_reason is None:
        result = json.loads((payload / "result.json").read_text(encoding="utf-8"))
        if result.get("exact_certification") is not True:
            raise RuntimeError(f"NUMERICAL_CERTIFICATION_FAILURE: {condition_id}")
        temporary = canonical.with_name(f".tmp-{condition_id}")
        if temporary.exists():
            raise FileExistsError(f"stale canonical temporary directory: {temporary}")
        shutil.copytree(payload, temporary)
        for name in ("stdout.log", "stderr.log", "resource_monitor.json"):
            shutil.copy2(attempt / name, temporary / name)
        os.replace(temporary, canonical)
        return {"classification": "SUCCESS", **monitor}
    if stop_reason in config["failure_policy"]["continue_after"]:
        if active_workers():
            raise RuntimeError(f"INTEGRITY_FAILURE: worker survived stop for {condition_id}")
        return {"classification": "RESOURCE_OR_TIME_FAILURE", **monitor}
    raise RuntimeError(f"UNKNOWN_WORKER_FAILURE: {condition_id}, return_code={return_code}")


def execute_batch(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: Renault SG-BD batch remains disabled")
    initial = build_dry_run(config_path)
    if not all(initial["gates"].values()):
        raise RuntimeError(f"BATCH_PREFLIGHT_BLOCKED: {initial['gates']}")
    records = []
    for condition in CONDITIONS:
        current = build_dry_run(config_path)
        row = next(item for item in current["conditions"] if item["condition_id"] == condition)
        gates = {
            key: value for key, value in current["gates"].items()
            if key not in {"all_attempts_absent", "all_canonical_results_absent"}
        }
        if not all(gates.values()) or row["attempt_exists"] or row["canonical_exists"]:
            raise RuntimeError(f"INTEGRITY_FAILURE before {condition}: {row}, {gates}")
        records.append(run_monitored(config_path, condition))
    report = {"protocol_id": config["protocol_id"], "status": "COMPLETE", "records": records}
    write_json(ROOT / config["output_directory"] / "batch_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--worker", choices=CONDITIONS)
    parser.add_argument("--attempt-root", type=Path)
    args = parser.parse_args()
    try:
        if args.worker:
            if args.attempt_root is None:
                parser.error("--worker requires --attempt-root")
            solve_condition(args.config.resolve(), args.worker, args.attempt_root.resolve())
            return 0
        result = execute_batch(args.config.resolve()) if args.execute else build_dry_run(args.config.resolve())
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except Exception as error:
        if args.worker and args.attempt_root:
            args.attempt_root.mkdir(parents=True, exist_ok=True)
            (args.attempt_root / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
            write_json(args.attempt_root / "failure.json", {
                "condition_id": args.worker,
                "error_type": type(error).__name__,
                "error": str(error),
            })
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
