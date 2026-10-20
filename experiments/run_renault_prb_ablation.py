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
    "PRB-SG": ROOT / "experiments/configs/development/renault_prb_sg_continuation_v3.yaml",
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
            "210129": ("preserve_canonical", "attempt-002"),
            "210310": ("preserve_canonical", "attempt-001"),
            "210330": ("preserve_numerical_failure", "attempt-001"),
            "210323": ("run", "attempt-001"),
            "210428": ("run", "attempt-001"),
            "210611": ("run", "attempt-001"),
        }
        observed = {
            case: (plan[case]["action"], plan[case]["attempt"])
            for case in CASES
        }
        if observed != expected_plan:
            raise RuntimeError("PRB-SG continuation attempt plan mismatch")
    policy = config.get("known_failure_policy")
    if policy != {
        "classification": "NUMERICAL_CERTIFICATION_FAIL",
        "require_internal_exact_certification": True,
        "require_independent_global_certification": True,
        "require_cut_validity": True,
        "require_direct_objective_consistency": True,
        "require_complete_identity_and_artifacts": True,
        "coupling_residual_must_exceed": 1e-6,
        "maximum_numerical_closure_residual": 1e-4,
        "continue_after_independent_classification": True,
    }:
        raise RuntimeError("known coupling-only failure policy mismatch")
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


ATTEMPT_ARTIFACTS = (
    "result.json",
    "provenance.json",
    "iteration_trajectory.json",
    "first_stage_solution.json",
    "solver.log",
    "stdout.log",
    "stderr.log",
    "resource_monitor.json",
)


def write_attempt_manifest(attempt: Path) -> dict[str, str]:
    hashes = {
        name: sha256(attempt / name)
        for name in ATTEMPT_ARTIFACTS
        if (attempt / name).is_file()
    }
    write_json(attempt / "attempt_manifest.json", hashes)
    return hashes


def coupling_only_failure_audit(
    config: dict[str, Any],
    attempt: Path,
    condition: str,
    *,
    expected_artifact_sha256: dict[str, str] | None = None,
    expected_config_sha256: str | None = None,
    expected_code_commit: str | None = None,
) -> dict[str, Any]:
    required = {name: (attempt / name).is_file() for name in ATTEMPT_ARTIFACTS}
    if not all(required.values()):
        return {"pass": False, "classification": "INTEGRITY_FAILURE", "required_artifacts": required}
    result = json.loads((attempt / "result.json").read_text(encoding="utf-8"))
    provenance = json.loads((attempt / "provenance.json").read_text(encoding="utf-8"))
    monitor = json.loads((attempt / "resource_monitor.json").read_text(encoding="utf-8"))
    observed_hashes = {name: sha256(attempt / name) for name in ATTEMPT_ARTIFACTS}
    manifest_path = attempt / "attempt_manifest.json"
    if expected_artifact_sha256 is not None:
        manifest_match = observed_hashes == expected_artifact_sha256
    else:
        manifest_match = manifest_path.is_file() and json.loads(
            manifest_path.read_text(encoding="utf-8")
        ) == observed_hashes
    tolerance = config["solver_tolerances"]
    coupling = float(result.get("global_risk_budget_coupling_error", float("inf")))
    closure = abs(float(result.get("final_lower_bound", float("inf"))) - float(
        result.get("final_upper_bound", float("-inf"))
    ))
    independent = result.get("independent_certification", {})
    identity = result.get("identity", {})
    current_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if expected_config_sha256 is None:
        provenance_config = Path(provenance.get("config_path", ""))
        config_sha_match = (
            provenance_config.is_file()
            and provenance_config.resolve() == CONFIGS[config["method_id"]].resolve()
            and provenance.get("config_sha256") == sha256(provenance_config)
        )
    else:
        config_sha_match = provenance.get("config_sha256") == expected_config_sha256
    checks = {
        "artifacts_complete": all(required.values()),
        "artifact_sha256": manifest_match,
        "condition_identity": result.get("condition_id") == condition
        and monitor.get("condition_id") == condition,
        "method_identity": result.get("method_id") == config["method_id"]
        and provenance.get("method_id") == config["method_id"],
        "instance_identity": identity.get("status") == "PASS"
        and all(identity.get("checks", {}).values())
        and provenance.get("instance_identity") == identity.get("identity"),
        "worker_exit": monitor.get("return_code") == 1 and monitor.get("stop_reason") is None,
        "failure_marker": "NUMERICAL_CERTIFICATION_FAILURE"
        in (attempt / "stderr.log").read_text(encoding="utf-8"),
        "result_not_certified": result.get("exact_certification") is False
        and result.get("solver_status") == "ERROR",
        "coupling_failed": result.get("global_risk_budget_coupling_pass") is False
        and coupling > tolerance["global_coupling"]
        and coupling <= config["known_failure_policy"]["maximum_numerical_closure_residual"],
        "closure_signature": abs(coupling - closure) <= 1e-12,
        "internal_exact": result.get("internal_exact_certification") is True,
        "independent_exact": independent.get("pass") is True
        and independent.get("dual_feasible") is True
        and float(independent.get("objective_residual", float("inf")))
        <= tolerance["objective_certification"]
        and float(independent.get("strong_duality_residual", float("inf")))
        <= tolerance["objective_certification"],
        "cut_validity": result.get("cut_validity") is True,
        "direct_consistency": float(result.get("direct_objective_residual", float("inf")))
        <= tolerance["objective_certification"],
        "provenance_result_sha256": provenance.get("result_sha256") == observed_hashes["result.json"],
        "provenance_trajectory_sha256": provenance.get("trajectory_sha256")
        == observed_hashes["iteration_trajectory.json"],
        "provenance_first_stage_sha256": provenance.get("first_stage_sha256")
        == observed_hashes["first_stage_solution.json"],
        "config_sha256": config_sha_match,
        "code_commit": provenance.get("code_commit")
        == (expected_code_commit if expected_code_commit is not None else current_commit),
    }
    passed = all(checks.values())
    return {
        "pass": passed,
        "classification": "NUMERICAL_CERTIFICATION_FAIL" if passed else "INTEGRITY_FAILURE",
        "checks": checks,
        "coupling_residual": coupling,
        "closure_residual": closure,
        "threshold": tolerance["global_coupling"],
        "artifact_sha256": observed_hashes,
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
        elif plan["action"] == "preserve_numerical_failure":
            attempt = output_root / "worker_logs" / cid / plan["attempt"]
            canonical = output_root / "runs" / cid
            failure = coupling_only_failure_audit(
                config,
                attempt,
                cid,
                expected_artifact_sha256=plan["artifact_sha256"],
                expected_config_sha256=plan["config_sha256"],
                expected_code_commit=plan["code_commit"],
            )
            row["attempt_exists"] = attempt.is_dir()
            row["canonical_exists"] = canonical.exists()
            row["known_failure_audit"] = failure
            row["plan_pass"] = attempt.is_dir() and not canonical.exists() and failure["pass"]
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
    write_attempt_manifest(attempt)
    classification = "UNKNOWN_WORKER_FAILURE"
    failure = None
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
        failure = coupling_only_failure_audit(config, attempt, cid)
        classification = failure["classification"]
    row = {
        **monitor,
        "classification": classification,
        "attempt": str(attempt),
        "canonical": str(canonical) if canonical.exists() else None,
    }
    if "failure" in locals() and failure is not None:
        row["known_failure_audit"] = failure
    return row


def continuation_allowed(classification: str) -> bool:
    return classification in {
        "SUCCESS",
        "NUMERICAL_CERTIFICATION_FAIL",
        "TIME_LIMIT",
        "RESOURCE_PROCESS_CAP",
        "RESOURCE_SYSTEM_CAP",
    }


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
        if plan["action"] in {"preserve_canonical", "preserve_numerical_failure"}:
            rows.append({
                "condition_id": condition_id(config, case),
                "classification": (
                    "PRESERVED_CANONICAL"
                    if plan["action"] == "preserve_canonical"
                    else "PRESERVED_NUMERICAL_CERTIFICATION_FAIL"
                ),
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
        if not continuation_allowed(row["classification"]):
            break
    report = {
        "protocol_id": config["protocol_id"],
        "method_id": config["method_id"],
        "expected": len(CASES),
        "attempted": len(rows),
        "rows": rows,
    }
    report_name = config.get("batch_report_name", "batch_report.json")
    report_path = ROOT / config["output_directory"] / report_name
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite {report_path}")
    write_json(report_path, report)
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
