from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
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

from experiments.run_renault_vanilla_bd_pilot import load_frozen_renault_case
from robust_inventory_reconfiguration.enhanced_basic_benders import (
    EnhancedGlobalEnumeratedLPOracle,
)
from robust_inventory_reconfiguration.prb_ablation import solve_prb_ablation


CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
CONFIGS = {
    "PRB-SG": ROOT / "experiments/configs/development/renault_prb_sg_recovery_v2.yaml",
    "A-PRB": ROOT / "experiments/configs/development/renault_a_prb_v1.yaml",
    "A-PRB-SG": ROOT / "experiments/configs/development/renault_a_prb_sg_v1.yaml",
}
ALLOWED_PREEXISTING = "?? experiments/results/basic_benders_scaling_development_v1/"


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


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    method = config.get("method_id")
    if method not in CONFIGS:
        raise RuntimeError("unknown PRB ablation method")
    if path.resolve() != CONFIGS[method].resolve():
        raise RuntimeError("method/config path identity mismatch")
    if tuple(config.get("case_ids", ())) != CASES:
        raise RuntimeError("Renault case scope differs from the frozen order")
    if config.get("fixed_scientific_parameters") != {"Gamma": 2, "lambda_R": 0.05}:
        raise RuntimeError("scientific parameters differ from the frozen protocol")
    mechanisms = config.get("mechanisms")
    expected = {
        "PRB-SG": {"adaptive_cut_selection": False, "exact_product_scenario_screening": True},
        "A-PRB": {"adaptive_cut_selection": True, "exact_product_scenario_screening": False},
        "A-PRB-SG": {"adaptive_cut_selection": True, "exact_product_scenario_screening": True},
    }[method]
    if mechanisms != expected:
        raise RuntimeError("method mechanism identity mismatch")
    if method == "PRB-SG":
        historical = ROOT / config["historical_protocol_config"]
        if sha256(historical) != config["historical_protocol_config_sha256"]:
            raise RuntimeError("historical PRB-SG protocol hash mismatch")
        plan = config.get("execution_plan", {})
        if tuple(plan) != CASES:
            raise RuntimeError("PRB-SG recovery plan differs from the frozen case order")
        expected_plan = {
            "210202": ("preserve_canonical", "attempt-001"),
            "210628": ("preserve_canonical", "attempt-001"),
            "210129": ("run", "attempt-002"),
            "210310": ("run", "attempt-001"),
            "210330": ("run", "attempt-001"),
            "210323": ("run", "attempt-001"),
            "210428": ("run", "attempt-001"),
            "210611": ("run", "attempt-001"),
        }
        observed = {
            case: (plan[case]["action"], plan[case]["attempt"])
            for case in CASES
        }
        if observed != expected_plan:
            raise RuntimeError("PRB-SG recovery attempt plan mismatch")
    resource = config["resource_policy"]
    if resource != {
        "execution": "sequential_single_process",
        "parallel_workers": 1,
        "minimum_available_memory_gib": 8,
        "maximum_process_tree_memory_gib": 4,
        "minimum_system_available_memory_gib": 3,
        "minimum_free_disk_gib": 20,
        "condition_time_limit_seconds": 300,
        "memory_monitor_interval_seconds": 0.25,
        "retry_policy": "no_automatic_retry",
    }:
        raise RuntimeError("resource policy differs from the frozen ablation contract")
    identity_path = ROOT / config["identity_source"]
    if sha256(identity_path) != config["identity_source_sha256"]:
        raise RuntimeError("frozen Renault identity source hash mismatch")
    return config


def condition_id(config: dict[str, Any], case: str) -> str:
    return f"{config['condition_prefix']}{case}"


def execution_plan(config: dict[str, Any], case: str) -> dict[str, Any]:
    if "execution_plan" in config:
        return config["execution_plan"][case]
    return {"action": "run", "attempt": "attempt-001"}


def preserved_canonical_audit(
    output_root: Path, condition: str, plan: dict[str, Any]
) -> dict[str, Any]:
    attempt = output_root / "worker_logs" / condition / plan["attempt"]
    canonical = output_root / "runs" / condition
    mismatches = []
    if attempt.is_dir() and canonical.is_dir():
        for source in attempt.iterdir():
            if not source.is_file():
                continue
            target = canonical / source.name
            if not target.is_file() or sha256(source) != sha256(target):
                mismatches.append(source.name)
    result_path = canonical / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    expected_hash = plan.get("result_sha256")
    return {
        "attempt_exists": attempt.is_dir(),
        "canonical_exists": canonical.is_dir(),
        "canonical_matches_attempt": attempt.is_dir() and canonical.is_dir() and not mismatches,
        "mismatches": mismatches,
        "result_sha256_match": bool(result_path.is_file() and expected_hash and sha256(result_path) == expected_hash),
        "exact_certification": result.get("exact_certification") is True,
    }


def identity_audit(config: dict[str, Any], case: str) -> dict[str, Any]:
    identity_config = json.loads((ROOT / config["identity_source"]).read_text(encoding="utf-8"))
    reference = identity_config["frozen_identity_reference"]
    reference_path = ROOT / reference["path"]
    if sha256(reference_path) != reference["sha256"]:
        raise RuntimeError("nested frozen Renault identity hash mismatch")
    frozen = json.loads(reference_path.read_text(encoding="utf-8"))
    expected = frozen["frozen_case_identity"][case]
    loaded = load_frozen_renault_case(case)
    checks = {
        key: loaded["identity"][key] == expected[key]
        for key in ("instance_hash", "x0_hash", "calibration_hash", "mapping_hash")
    }
    checks["Gamma"] = loaded["gamma"] == 2
    checks["lambda_R"] = loaded["lambda_r"] == 0.05
    return {
        "case": case,
        "condition_id": condition_id(config, case),
        "identity": loaded["identity"],
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
                "run_renault_prb_ablation.py" in command and "--worker" in command
            ):
                found.append({"pid": process.pid, "name": process.info.get("name")})
        except psutil.Error:
            continue
    return found


def git_audit(output_root: Path) -> dict[str, Any]:
    entries = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).splitlines()
    prefix = f"?? {output_root.relative_to(ROOT).as_posix()}/"
    unexpected = [
        entry for entry in entries
        if not entry.startswith(ALLOWED_PREEXISTING) and not entry.startswith(prefix)
    ]
    return {"entries": entries, "unexpected_entries": unexpected, "pass": not unexpected}


def dry_run(config_path: Path) -> dict[str, Any]:
    import gurobipy as gp

    config = load_config(config_path)
    output_root = ROOT / config["output_directory"]
    conditions = []
    for case in CASES:
        row = identity_audit(config, case)
        cid = condition_id(config, case)
        plan = execution_plan(config, case)
        row["planned_action"] = plan["action"]
        row["planned_attempt"] = plan["attempt"]
        if plan["action"] == "preserve_canonical":
            preserved = preserved_canonical_audit(output_root, cid, plan)
            row.update(preserved)
            row["plan_pass"] = all(
                preserved[key]
                for key in (
                    "attempt_exists",
                    "canonical_exists",
                    "canonical_matches_attempt",
                    "result_sha256_match",
                    "exact_certification",
                )
            )
        else:
            attempt = output_root / "worker_logs" / cid / plan["attempt"]
            canonical = output_root / "runs" / cid
            row["attempt_exists"] = attempt.exists()
            row["canonical_exists"] = canonical.exists()
            row["plan_pass"] = not attempt.exists() and not canonical.exists()
        conditions.append(row)
    resource = config["resource_policy"]
    available = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output_root.parent).free / 2**30
    git = git_audit(output_root)
    workers = active_workers()
    gates = {
        "identity": all(row["status"] == "PASS" for row in conditions),
        "execution_plan": all(row["plan_pass"] for row in conditions),
        "startup_memory": available >= resource["minimum_available_memory_gib"],
        "disk": free_disk >= resource["minimum_free_disk_gib"],
        "git_status": git["pass"],
        "no_active_worker": not workers,
    }
    return {
        "schema": "renault_prb_ablation_dry_run_v1",
        "method_id": config["method_id"],
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
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "gurobi": ".".join(map(str, gp.gurobi.version())),
        },
        "decision": "READY_FOR_AUTHORIZATION" if all(gates.values()) else "BLOCKED",
        "optimization_calls": 0,
    }


def independent_certification(instance: Any, solution: Any, gamma: int, time_limit: float) -> dict[str, Any]:
    oracle = EnhancedGlobalEnumeratedLPOracle(instance, gamma)
    try:
        certified = oracle.solve(solution.x, time_limit=time_limit)
    finally:
        oracle.close()
    objective = solution.first_stage_expenditure + certified.value
    return {
        "objective": objective,
        "recourse": certified.value,
        "objective_residual": abs(objective - solution.objective),
        "dual_feasible": certified.cut.dual_feasible,
        "strong_duality_residual": certified.cut.strong_duality_error,
        "pass": (
            certified.cut.dual_feasible
            and certified.cut.strong_duality_error <= 1e-4
            and abs(objective - solution.objective) <= 1e-4
        ),
    }


def direct_objectives() -> dict[str, float]:
    rows = json.loads((ROOT / "artifacts/renault_sg_bd_acceptance_audit.json").read_text(encoding="utf-8"))
    if rows.get("status") != "PASS":
        raise RuntimeError("SG acceptance audit is not PASS")
    import csv

    with (ROOT / "artifacts/renault_sg_bd_results.csv").open(encoding="utf-8", newline="") as handle:
        return {row["case"]: float(row["direct_objective"]) for row in csv.DictReader(handle)}


def solve_worker(config_path: Path, cid: str, attempt_root: Path) -> None:
    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED")
    expected = {condition_id(config, case): case for case in CASES}
    if cid not in expected:
        raise RuntimeError("condition is outside the frozen method allowlist")
    if attempt_root.exists():
        raise FileExistsError(f"refusing to overwrite {attempt_root}")
    attempt_root.mkdir(parents=True)
    case = expected[cid]
    identity = identity_audit(config, case)
    if identity["status"] != "PASS":
        raise RuntimeError("IDENTITY_FAILURE")
    loaded = load_frozen_renault_case(case)
    mechanism = config["mechanisms"]
    started = perf_counter()
    solved = solve_prb_ablation(
        loaded["instance"],
        loaded["x0"],
        loaded["budget"],
        loaded["gamma"],
        loaded["lambda_r"],
        method_id=config["method_id"],
        scenario_screening=mechanism["exact_product_scenario_screening"],
        adaptive_cut_selection=mechanism["adaptive_cut_selection"],
        relative_gap_tolerance=config["solver_tolerances"]["relative_gap"],
        cut_tolerance=config["solver_tolerances"]["cut_violation"],
        max_iterations=config["algorithm"]["max_iterations"],
        log_file=attempt_root / "solver.log",
    )
    algorithm_seconds = perf_counter() - started
    remaining = config["resource_policy"]["condition_time_limit_seconds"] - algorithm_seconds
    if remaining <= 0:
        raise TimeoutError("no time remains for independent certification")
    cert_started = perf_counter()
    independent = independent_certification(
        loaded["instance"], solved.solution, loaded["gamma"], remaining
    )
    certification_seconds = perf_counter() - cert_started
    cuts_valid = all(
        cut.dual_feasible and cut.strong_duality_error <= 1e-4
        for cut in solved.cuts
    )
    direct = direct_objectives()[case]
    direct_residual = abs(solved.solution.objective - direct)
    exact = bool(
        solved.exact_certification_pass
        and solved.global_risk_budget_coupling_pass
        and independent["pass"]
        and cuts_valid
        and direct_residual <= 1e-4
    )
    trajectory = [asdict(item) for item in solved.iterations]
    write_json(attempt_root / "iteration_trajectory.json", trajectory)
    write_json(attempt_root / "first_stage_solution.json", {
        "y": solved.solution.y,
        "x": solved.solution.x,
        "a_plus": solved.solution.a_plus,
        "a_minus": solved.solution.a_minus,
    })
    result = {
        "case": case,
        "condition_id": cid,
        "method_id": config["method_id"],
        "solver_status": solved.status,
        "exact_certification": exact,
        "internal_exact_certification": solved.exact_certification_pass,
        "global_risk_budget_coupling_pass": solved.global_risk_budget_coupling_pass,
        "global_risk_budget_coupling_error": solved.global_risk_budget_coupling_error,
        "cut_validity": cuts_valid,
        "objective": solved.solution.objective,
        "direct_objective": direct,
        "direct_objective_residual": direct_residual,
        "final_lower_bound": solved.final_lower_bound,
        "final_upper_bound": solved.final_upper_bound,
        "final_gap": solved.final_relative_gap,
        "iterations": len(solved.iterations),
        "candidate_cuts": solved.candidate_cuts,
        "violated_cuts": solved.violated_cuts,
        "selected_cuts": solved.selected_cuts,
        "cuts_added": solved.unique_product_cuts,
        "algorithm_core_time_seconds": algorithm_seconds,
        "master_time_seconds": solved.master_runtime,
        "oracle_time_seconds": solved.separation_runtime,
        "internal_certification_time_seconds": solved.certification_runtime,
        "independent_certification_time_seconds": certification_seconds,
        "total_time_seconds": algorithm_seconds + certification_seconds,
        "scenario_patterns": solved.scenario_patterns,
        "scenario_lp_solves": solved.scenario_lp_solves,
        "safely_pruned_patterns": solved.safely_pruned_patterns,
        "pruning_fraction": (
            solved.safely_pruned_patterns / solved.scenario_patterns
            if solved.scenario_patterns else 0.0
        ),
        "branch_nodes": solved.branch_nodes,
        "upper_bound_seconds": solved.upper_bound_seconds,
        "independent_certification": independent,
        "identity": identity,
    }
    write_json(attempt_root / "result.json", result)
    write_json(attempt_root / "provenance.json", {
        "config_path": str(config_path.resolve()),
        "config_sha256": sha256(config_path),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "instance_identity": loaded["identity"],
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "method_id": config["method_id"],
        "mechanisms": mechanism,
        "formal_run_authorized": True,
        "result_sha256": sha256(attempt_root / "result.json"),
        "trajectory_sha256": sha256(attempt_root / "iteration_trajectory.json"),
        "first_stage_sha256": sha256(attempt_root / "first_stage_solution.json"),
    })
    if not exact:
        raise RuntimeError("NUMERICAL_CERTIFICATION_FAILURE")


def tree_rss(process: psutil.Process) -> int:
    total = 0
    try:
        processes = [process, *process.children(recursive=True)]
    except psutil.NoSuchProcess:
        return 0
    for item in processes:
        try:
            total += item.memory_info().rss
        except psutil.Error:
            continue
    return total


def terminate_tree(process: psutil.Process) -> None:
    children = process.children(recursive=True)
    for item in reversed(children):
        try:
            item.terminate()
        except psutil.Error:
            pass
    try:
        process.terminate()
    except psutil.Error:
        pass
    _, alive = psutil.wait_procs([*children, process], timeout=5)
    for item in alive:
        try:
            item.kill()
        except psutil.Error:
            pass


def run_monitored(config_path: Path, cid: str, attempt_name: str) -> dict[str, Any]:
    config = load_config(config_path)
    output_root = ROOT / config["output_directory"]
    attempt = output_root / "worker_logs" / cid / attempt_name
    canonical = output_root / "runs" / cid
    if attempt.exists() or canonical.exists():
        raise FileExistsError(f"refusing to overwrite {cid}")
    attempt.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--config", str(config_path.resolve()),
        "--worker", cid,
        "--attempt-root", str(attempt.resolve()),
    ]
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    monitored = psutil.Process(process.pid)
    resource = config["resource_policy"]
    started = perf_counter()
    peak = 0
    stop_reason = None
    samples = []
    while process.poll() is None:
        elapsed = perf_counter() - started
        rss = tree_rss(monitored)
        available = psutil.virtual_memory().available
        peak = max(peak, rss)
        samples.append({"elapsed_seconds": elapsed, "process_tree_rss_gib": rss / 2**30, "available_memory_gib": available / 2**30})
        if elapsed > resource["condition_time_limit_seconds"]:
            stop_reason = "TIME_LIMIT"
        elif rss / 2**30 > resource["maximum_process_tree_memory_gib"]:
            stop_reason = "RESOURCE_PROCESS_CAP"
        elif available / 2**30 < resource["minimum_system_available_memory_gib"]:
            stop_reason = "RESOURCE_SYSTEM_CAP"
        if stop_reason:
            terminate_tree(monitored)
            break
        sleep(resource["memory_monitor_interval_seconds"])
    stdout, stderr = process.communicate()
    attempt.mkdir(parents=True, exist_ok=True)
    (attempt / "stdout.log").write_text(stdout, encoding="utf-8")
    (attempt / "stderr.log").write_text(stderr, encoding="utf-8")
    monitor = {
        "condition_id": cid,
        "return_code": process.returncode,
        "stop_reason": stop_reason,
        "elapsed_seconds": perf_counter() - started,
        "peak_process_tree_rss_gib": peak / 2**30,
        "samples": samples,
    }
    write_json(attempt / "resource_monitor.json", monitor)
    classification = "UNKNOWN_WORKER_FAILURE"
    if stop_reason in {"TIME_LIMIT", "RESOURCE_PROCESS_CAP", "RESOURCE_SYSTEM_CAP"}:
        classification = stop_reason
    elif process.returncode == 0:
        result = json.loads((attempt / "result.json").read_text(encoding="utf-8"))
        if result["exact_certification"]:
            temporary = canonical.with_name(f".tmp-{os.getpid()}-{canonical.name}")
            shutil.copytree(attempt, temporary)
            os.replace(temporary, canonical)
            classification = "SUCCESS"
        else:
            classification = "NUMERICAL_CERTIFICATION_FAILURE"
    elif "NUMERICAL_CERTIFICATION_FAILURE" in stderr:
        classification = "NUMERICAL_CERTIFICATION_FAILURE"
    return {**monitor, "classification": classification, "attempt": str(attempt), "canonical": str(canonical) if canonical.exists() else None}


def execute(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED")
    initial = dry_run(config_path)
    if initial["decision"] != "READY_FOR_AUTHORIZATION":
        raise RuntimeError(f"PREFLIGHT_BLOCKED: {initial['gates']}")
    rows = []
    for case in CASES:
        plan = execution_plan(config, case)
        if plan["action"] == "preserve_canonical":
            rows.append({
                "condition_id": condition_id(config, case),
                "classification": "PRESERVED_CANONICAL",
                "attempt": plan["attempt"],
            })
            continue
        current = dry_run(config_path)
        resource = config["resource_policy"]
        if (
            current["resource_snapshot"]["available_memory_gib"] < resource["minimum_available_memory_gib"]
            or current["resource_snapshot"]["free_disk_gib"] < resource["minimum_free_disk_gib"]
            or current["resource_snapshot"]["active_workers"]
        ):
            raise RuntimeError("PER_CONDITION_RESOURCE_GATE_BLOCKED")
        row = run_monitored(
            config_path, condition_id(config, case), plan["attempt"]
        )
        rows.append(row)
        if row["classification"] not in {"SUCCESS", "TIME_LIMIT", "RESOURCE_PROCESS_CAP", "RESOURCE_SYSTEM_CAP"}:
            break
    report = {
        "protocol_id": config["protocol_id"],
        "method_id": config["method_id"],
        "expected": len(CASES),
        "attempted": len(rows),
        "rows": rows,
    }
    write_json(ROOT / config["output_directory"] / "batch_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker")
    parser.add_argument("--attempt-root", type=Path)
    args = parser.parse_args()
    try:
        if args.worker:
            if args.attempt_root is None:
                parser.error("--worker requires --attempt-root")
            solve_worker(args.config.resolve(), args.worker, args.attempt_root.resolve())
            return 0
        output = execute(args.config.resolve()) if args.execute else dry_run(args.config.resolve())
        print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
