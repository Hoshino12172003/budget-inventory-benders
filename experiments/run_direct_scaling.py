from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from time import perf_counter, sleep
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.algorithm_scaling import canonical_hash, file_sha256
from robust_inventory_reconfiguration.first_stage_solution import build_first_stage_solution_artifact
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.reconfiguration_model import (
    ReconfigurationSolution,
    build_exact_reconfiguration_model,
)
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget


CONFIG = ROOT / "experiments/configs/formal/direct_scaling_extension.yaml"
MODEL_FILES = (
    "experiments/run_direct_scaling.py",
    "src/robust_inventory_reconfiguration/reconfiguration_model.py",
    "src/robust_inventory_reconfiguration/product_risk_subproblem.py",
    "src/robust_inventory_reconfiguration/risk_budget_composition.py",
    "src/robust_inventory_reconfiguration/solver_profile.py",
)


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def conditions(config: dict) -> list[dict]:
    return [
        {"size": size["label"], "seed": seed, "condition_id": f"DIRECT_{size['label']}_S{seed}"}
        for size in config["sizes"] for seed in config["seeds"]
    ]


def authorized_conditions(config: dict) -> list[dict]:
    grid = conditions(config)
    lookup = {row["condition_id"]: row for row in grid}
    identifiers = config.get("authorized_condition_ids", [])
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("duplicate Direct authorization condition")
    unknown = sorted(set(identifiers) - set(lookup))
    if unknown:
        raise RuntimeError(f"unknown Direct authorization condition: {unknown}")
    return [lookup[identifier] for identifier in identifiers]


def next_attempt_number(output_root: Path, condition_id: str) -> int:
    log_parent = output_root / "worker_logs" / condition_id
    attempt = 1
    while (log_parent / f"attempt-{attempt:03d}").exists():
        attempt += 1
    return attempt


def current_environment() -> dict:
    import gurobipy as gp

    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "gurobipy_version": gp.__version__,
        "gurobi_native_version": list(gp.gurobi.version()),
        "gurobipy_file": str(Path(gp.__file__).resolve()),
    }


def model_identity() -> dict:
    files = {path: file_sha256(ROOT / path) for path in MODEL_FILES}
    return {"sha256": canonical_hash(files), "files": files}


def validate_environment(config: dict) -> dict:
    current = current_environment()
    required = config["required_environment"]
    checks = {
        "python_version": current["python_version"] == required["python_version"],
        "gurobipy_version": current["gurobipy_version"] == required["gurobipy_version"],
        "gurobi_native_version": current["gurobi_native_version"] == required["gurobi_native_version"],
    }
    return {"pass": all(checks.values()), "checks": checks, "required": required, "current": current}


def _unexpected_worktree_changes(output_root: Path) -> list[str]:
    relative_output = output_root.resolve().relative_to(ROOT.resolve()).as_posix() + "/"
    lines = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    return [line for line in lines if not line[3:].replace("\\", "/").startswith(relative_output)]


def validate_execution_gate(config: dict, condition: dict, output_root: Path) -> dict:
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("FORMAL_DIRECT_EXECUTION_NOT_AUTHORIZED")
    if condition["condition_id"] not in {row["condition_id"] for row in authorized_conditions(config)}:
        raise RuntimeError(f"DIRECT_CONDITION_NOT_AUTHORIZED: {condition['condition_id']}")
    configured_output = (ROOT / config["output_directory"]).resolve()
    if output_root.resolve() != configured_output:
        raise RuntimeError(f"DIRECT_OUTPUT_ROOT_MISMATCH: {output_root} != {configured_output}")
    environment = validate_environment(config)
    if not environment["pass"]:
        raise RuntimeError(f"ENVIRONMENT_IDENTITY_MISMATCH: {environment['checks']}")
    unexpected = _unexpected_worktree_changes(output_root)
    if unexpected:
        raise RuntimeError(f"formal Direct execution found changes outside its output root: {unexpected}")
    available = psutil.virtual_memory().available / 2**30
    minimum = config["resource_policy"]["minimum_available_memory_gib_by_size"][condition["size"]]
    if available < minimum:
        raise RuntimeError(f"RESOURCE_GATE_BLOCKED {condition['size']}: {available:.3f} GiB < {minimum:.3f} GiB")
    disk_free = shutil.disk_usage(configured_output.parent).free / 2**30
    disk_minimum = config["resource_policy"]["minimum_free_disk_gib"]
    if disk_free < disk_minimum:
        raise RuntimeError(f"DISK_GATE_BLOCKED: {disk_free:.3f} GiB < {disk_minimum:.3f} GiB")
    return {
        "available_memory_gib": available,
        "minimum_memory_gib": minimum,
        "free_disk_gib": disk_free,
        "minimum_free_disk_gib": disk_minimum,
        "environment": environment,
    }


def verified_input(config: dict, condition: dict):
    root = ROOT / config["source_output_root"] / "instances" / condition["size"] / str(condition["seed"])
    instance_path, preparation_path = root / "instance.json", root / "preparation.json"
    instance = load_instance(instance_path)
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    expected_id = f"ASC_INSTANCE_{condition['size']}_S{condition['seed']}"
    checks = {
        "instance_id": preparation.get("instance_id") == expected_id,
        "size": preparation.get("size") == condition["size"],
        "seed": preparation.get("seed") == condition["seed"],
        "instance_hash": preparation.get("instance_hash") == canonical_hash(instance.to_dict()),
        "x0_hash": preparation.get("x0_hash") == canonical_hash(instance.initial_inventory),
        "Gamma": preparation["scientific_parameters"]["Gamma"] == config["fixed_scientific_parameters"]["Gamma"],
        "beta": preparation["scientific_parameters"]["beta"] == config["fixed_scientific_parameters"]["beta"],
        "lambda_R": preparation["scientific_parameters"]["lambda_R"] == config["fixed_scientific_parameters"]["lambda_R"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"DIRECT_INPUT_IDENTITY_MISMATCH: {checks}")
    return instance, preparation, {"instance_sha256": file_sha256(instance_path), "preparation_sha256": file_sha256(preparation_path)}


def _solution(instance, model, variables) -> ReconfigurationSolution:
    x = [[variables["x"][i, j].X for j in range(instance.num_products)] for i in range(instance.num_depots)]
    plus = [[variables["a_plus"][i, j].X for j in range(instance.num_products)] for i in range(instance.num_depots)]
    minus = [[variables["a_minus"][i, j].X for j in range(instance.num_products)] for i in range(instance.num_depots)]
    return ReconfigurationSolution(
        objective=float(model.ObjVal),
        first_stage_expenditure=float(variables["first_stage"].getValue()),
        robust_recourse_cost=float(variables["theta"].X),
        y=[int(round(variables["y"][i].X)) for i in range(instance.num_depots)],
        x=x,
        a_plus=plus,
        a_minus=minus,
        reconfiguration_cost=float(variables["reconfiguration_cost"].getValue()),
    )


def certify_solution(instance, solution: ReconfigurationSolution, gamma: int) -> float:
    tables = []
    for j in range(instance.num_products):
        subproblem = ProductRiskSubproblem(instance, j, gamma)
        try:
            solved = subproblem.solve([row[j] for row in solution.x])
        finally:
            subproblem.model.dispose()
        if not all(item.cut.dual_feasible and item.cut.strong_duality_error <= 1e-4 for item in solved.worst_cases):
            raise RuntimeError("DIRECT_CERTIFICATION_DUAL_FAILURE")
        tables.append([item.value for item in solved.worst_cases])
    return compose_risk_budget(tables, gamma).value


def _write_solver_progress(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _release_solver_resources(model) -> None:
    import gurobipy as gp

    model.Params.LogFile = ""
    model.dispose()
    gp.disposeDefaultEnv()


def _copy_with_windows_lock_retry(source: Path, target: Path, attempts: int = 20, delay: float = 0.1) -> None:
    for attempt in range(attempts):
        try:
            shutil.copy2(source, target)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) != 32 or attempt + 1 == attempts:
                raise
            sleep(delay)


def persist_result_artifacts(
    output_root: Path,
    condition: dict,
    result: dict,
    first_stage_artifact: dict | None,
    input_hashes: dict,
    model_identity_record: dict,
    solver_log_path: Path,
    progress_path: Path,
    *,
    log_copy_attempts: int = 20,
    log_copy_delay: float = 0.1,
) -> Path:
    target = output_root / "runs" / condition["condition_id"]
    if target.exists():
        raise FileExistsError(f"refusing to overwrite Direct result: {target}")
    candidate = output_root / "recovery_candidates" / f".candidate-{uuid4().hex[:12]}"
    candidate.mkdir(parents=True)
    marker = candidate / "CANDIDATE_NOT_FORMAL.json"
    marker.write_text(json.dumps({
        "condition_id": condition["condition_id"],
        "formal_artifact": False,
        "reason": "ATOMIC_PUBLICATION_NOT_COMPLETED",
    }, indent=2) + "\n", encoding="utf-8")
    result_path = candidate / "result.json"
    result_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if first_stage_artifact is not None:
        (candidate / "first_stage_solution.json").write_text(
            json.dumps(first_stage_artifact, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    provenance = {
        **input_hashes,
        "result_sha256": file_sha256(result_path),
        "model_identity": model_identity_record,
        "environment": result["environment"],
        "archive_complete": False,
    }
    if (candidate / "first_stage_solution.json").is_file():
        provenance["first_stage_solution_sha256"] = file_sha256(candidate / "first_stage_solution.json")
    provenance_path = candidate / "provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    try:
        _copy_with_windows_lock_retry(
            solver_log_path,
            candidate / "solver.log",
            attempts=log_copy_attempts,
            delay=log_copy_delay,
        )
        provenance["solver_log_sha256"] = file_sha256(candidate / "solver.log")
        if progress_path.is_file():
            shutil.copy2(progress_path, candidate / "solver_progress.json")
            provenance["solver_progress_sha256"] = file_sha256(candidate / "solver_progress.json")
        provenance["archive_complete"] = True
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        marker.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(candidate, target)
        except Exception:
            marker.write_text(json.dumps({
                "condition_id": condition["condition_id"],
                "formal_artifact": False,
                "reason": "ATOMIC_PUBLICATION_FAILED",
            }, indent=2) + "\n", encoding="utf-8")
            raise
    except Exception:
        if not marker.exists():
            marker.write_text(json.dumps({
                "condition_id": condition["condition_id"],
                "formal_artifact": False,
                "reason": "ARTIFACT_ARCHIVE_FAILED",
            }, indent=2) + "\n", encoding="utf-8")
        raise
    for source in (solver_log_path, progress_path):
        try:
            source.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def solve_condition(config: dict, condition: dict, output_root: Path) -> None:
    from gurobipy import GRB

    gate = validate_execution_gate(config, condition, output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "runs" / condition["condition_id"]
    if target.exists():
        raise FileExistsError(f"refusing to overwrite Direct result: {target}")
    instance, preparation, input_hashes = verified_input(config, condition)
    x0 = instance.initial_inventory
    if x0 is None:
        raise RuntimeError("prepared instance has no x0")
    total_started = perf_counter()
    core_started = perf_counter()
    model_identity_record = model_identity()
    build_started = perf_counter()
    model, variables = build_exact_reconfiguration_model(
        instance, x0, float(preparation["budget"]),
        config["fixed_scientific_parameters"]["Gamma"],
        config["fixed_scientific_parameters"]["lambda_R"],
    )
    model_build_seconds = perf_counter() - build_started
    time_limit = config["resource_policy"]["condition_time_limit_seconds"]
    model.Params.TimeLimit = max(1.0, time_limit - model_build_seconds)
    solver_log_path = output_root / f".{condition['condition_id']}.solver.log"
    model.Params.LogFile = str(solver_log_path)
    model.Params.OutputFlag = 1
    progress_path = output_root / f".{condition['condition_id']}.progress.json"
    last_progress_seconds = [-5.0]

    def progress_callback(active_model, where):
        if where != GRB.Callback.MIP:
            return
        runtime = float(active_model.cbGet(GRB.Callback.RUNTIME))
        if runtime - last_progress_seconds[0] < 5.0:
            return
        last_progress_seconds[0] = runtime
        _write_solver_progress(progress_path, {
            "condition_id": condition["condition_id"],
            "runtime_seconds": runtime,
            "incumbent": float(active_model.cbGet(GRB.Callback.MIP_OBJBST)),
            "best_bound": float(active_model.cbGet(GRB.Callback.MIP_OBJBND)),
            "node_count": float(active_model.cbGet(GRB.Callback.MIP_NODCNT)),
        })

    try:
        model.optimize(progress_callback)
        optimize_seconds = float(model.Runtime)
        status = {GRB.OPTIMAL: "OPTIMAL", GRB.TIME_LIMIT: "TIME_LIMIT", GRB.MEM_LIMIT: "MEMORY_LIMIT"}.get(model.Status, "OTHER")
        solution = _solution(instance, model, variables) if model.SolCount else None
        certification_seconds = None
        certified_recourse = None
        exact = False
        certification_status = "NOT_ATTEMPTED"
        certification_error = None
        if status == "OPTIMAL" and solution is not None:
            started = perf_counter()
            try:
                certified_recourse = certify_solution(instance, solution, config["fixed_scientific_parameters"]["Gamma"])
                exact = abs(solution.first_stage_expenditure + certified_recourse - solution.objective) <= 1e-4
                certification_status = "PASS" if exact else "OBJECTIVE_RESIDUAL_FAILURE"
            except Exception as exc:
                certification_status = "ERROR"
                certification_error = f"{type(exc).__name__}: {exc}"
            finally:
                certification_seconds = perf_counter() - started
        core_seconds = perf_counter() - core_started
        result = {
            "experiment_id": config["experiment_id"], "condition_id": condition["condition_id"],
            "method": "direct_exact", "size": condition["size"], "seed": condition["seed"],
            "solver_status": status, "exact_certification": exact,
            "certification_status": certification_status, "certification_error": certification_error,
            "objective": solution.objective if solution else None,
            "best_bound": float(model.ObjBound) if model.SolCount else None,
            "mip_gap": float(model.MIPGap) if model.SolCount else None,
            "node_count": float(model.NodeCount), "variable_count": int(model.NumVars),
            "binary_variable_count": int(model.NumBinVars), "constraint_count": int(model.NumConstrs),
            "nonzero_count": int(model.NumNZs), "certified_recourse_value": certified_recourse,
            "model_build_seconds": model_build_seconds, "solver_optimize_seconds": optimize_seconds,
            "certification_seconds": certification_seconds, "T_core_seconds": core_seconds,
            "total_wall_seconds": perf_counter() - total_started,
            "config_hash": canonical_hash(config), "instance_hash": preparation["instance_hash"],
            "model_identity": model_identity_record["sha256"],
            "solver_parameters": config["solver_parameters"],
            "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "environment": current_environment(), "resource_preflight": gate,
        }
        first_stage_artifact = None
        if solution:
            first_stage_artifact = build_first_stage_solution_artifact(
                instance, x0, solution, case_id=condition["condition_id"], mode="direct_exact",
                identity={"config_hash": result["config_hash"], "data_hash": result["instance_hash"], "x0_hash": preparation["x0_hash"], "git_commit": result["code_commit"]},
                solver_profile=config["solver_profile"],
            )
    finally:
        _release_solver_resources(model)
    persist_result_artifacts(
        output_root,
        condition,
        result,
        first_stage_artifact,
        input_hashes,
        model_identity_record,
        solver_log_path,
        progress_path,
    )


def verified_existing_result(config: dict, condition: dict, output_root: Path) -> bool:
    target = output_root / "runs" / condition["condition_id"]
    paths = [target / name for name in ("result.json", "provenance.json")]
    if not any(path.exists() for path in paths):
        return False
    if not all(path.is_file() for path in paths):
        raise RuntimeError(f"incomplete existing Direct result: {target}")
    result = json.loads(paths[0].read_text(encoding="utf-8"))
    provenance = json.loads(paths[1].read_text(encoding="utf-8"))
    checks = {
        "condition": result.get("condition_id") == condition["condition_id"],
        "size": result.get("size") == condition["size"],
        "seed": result.get("seed") == condition["seed"],
        "config": result.get("config_hash") == canonical_hash(config),
        "certified": result.get("solver_status") == "OPTIMAL" and result.get("exact_certification") is True,
        "archive_complete": provenance.get("archive_complete") is True,
        "hash": provenance.get("result_sha256") == file_sha256(paths[0]),
    }
    if not all(checks.values()):
        raise RuntimeError(f"existing Direct result identity failure: {checks}")
    return True


def _process_tree_memory_gib(pid: int) -> float | None:
    try:
        parent = psutil.Process(pid)
        processes = [parent, *parent.children(recursive=True)]
    except psutil.Error:
        return None
    total = 0
    for process in processes:
        try:
            total += process.memory_info().rss
        except psutil.Error:
            pass
    return total / 2**30


def run_monitored(config_path: Path, config: dict, condition: dict, output_root: Path) -> None:
    preflight = validate_execution_gate(config, condition, output_root)
    verified_input(config, condition)
    log_parent = output_root / "worker_logs" / condition["condition_id"]
    attempt = next_attempt_number(output_root, condition["condition_id"])
    log_root = log_parent / f"attempt-{attempt:03d}"
    log_root.mkdir(parents=True)
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", condition["condition_id"], "--config", str(config_path), "--output-root", str(output_root)]
    started = perf_counter()
    peak = 0.0
    sample_count = 0
    stop_reason = None
    with (log_root / "stdout.log").open("w", encoding="utf-8") as stdout, (log_root / "stderr.log").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            sampled_memory = _process_tree_memory_gib(process.pid)
            if sampled_memory is None:
                stop_reason = "RESOURCE_MONITOR_FAILURE"
                process.kill()
                break
            sample_count += 1
            peak = max(peak, sampled_memory)
            available = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - started
            cap = config["resource_policy"]["maximum_process_tree_memory_gib_by_size"][condition["size"]]
            if peak >= cap:
                stop_reason = "RESOURCE_PROCESS_CAP"
            elif available <= config["resource_policy"]["minimum_system_available_memory_gib"]:
                stop_reason = "RESOURCE_SYSTEM_CAP"
            elif elapsed >= config["resource_policy"]["condition_time_limit_seconds"] + 60:
                stop_reason = "MONITOR_HARD_TIME_LIMIT"
            if stop_reason:
                process.kill()
                break
            sleep(config["resource_policy"].get("memory_monitor_interval_seconds", 0.25))
        return_code = process.wait()
    if sample_count == 0 and stop_reason is None:
        stop_reason = "RESOURCE_MONITOR_NO_SAMPLES"
    monitor = {"condition_id": condition["condition_id"], "attempt": f"attempt-{attempt:03d}", "resource_protocol_id": config.get("resource_protocol_id"), "preflight": preflight, "sample_count": sample_count, "peak_process_tree_memory_gib": peak, "wall_clock_seconds": perf_counter() - started, "stop_reason": stop_reason, "worker_return_code": return_code}
    (log_root / "resource_monitor.json").write_text(json.dumps(monitor, indent=2) + "\n", encoding="utf-8")
    for suffix, name in (("solver.log", "solver.log"), ("progress.json", "solver_progress.json")):
        interrupted_artifact = output_root / f".{condition['condition_id']}.{suffix}"
        if interrupted_artifact.is_file():
            shutil.move(str(interrupted_artifact), log_root / name)
    if stop_reason or return_code != 0:
        raise RuntimeError(f"Direct worker failed: {condition['condition_id']}: {stop_reason or return_code}")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", metavar="CONDITION_ID")
    mode.add_argument("--execute-all", action="store_true")
    mode.add_argument("--worker", metavar="CONDITION_ID")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    grid = conditions(config)
    if args.dry_run:
        authorized = authorized_conditions(config)
        output_root = args.output_root or ROOT / config["output_directory"]
        environment = validate_environment(config)
        resource_policy = config["resource_policy"]
        print(json.dumps({
            "optimization_calls": 0,
            "configured_conditions": len(grid),
            "formal_run_authorized": config["formal_run_authorized"],
            "formal_execution_permitted": config["formal_run_authorized"] is True and environment["pass"],
            "authorized_conditions": [row["condition_id"] for row in authorized],
            "next_attempts": {
                row["condition_id"]: f"attempt-{next_attempt_number(output_root, row['condition_id']):03d}"
                for row in authorized
            },
            "resource_gates": {
                "minimum_available_memory_gib_by_size": resource_policy["minimum_available_memory_gib_by_size"],
                "maximum_process_tree_memory_gib_by_size": resource_policy["maximum_process_tree_memory_gib_by_size"],
                "minimum_system_available_memory_gib": resource_policy["minimum_system_available_memory_gib"],
                "minimum_free_disk_gib": resource_policy["minimum_free_disk_gib"],
                "condition_time_limit_seconds": resource_policy["condition_time_limit_seconds"],
                "memory_monitor_interval_seconds": resource_policy.get("memory_monitor_interval_seconds", 0.25),
                "parallel_workers": resource_policy["parallel_workers"],
            },
            "current_available_memory_gib": psutil.virtual_memory().available / 2**30,
            "environment": environment,
        }, indent=2))
        return
    output_root = args.output_root or ROOT / config["output_directory"]
    if args.worker:
        solve_condition(config, next(row for row in grid if row["condition_id"] == args.worker), output_root)
        return
    selected = authorized_conditions(config) if args.execute_all else [next(row for row in grid if row["condition_id"] == args.execute)]
    for condition in selected:
        if verified_existing_result(config, condition, output_root):
            print(f"[RESUME VERIFIED] {condition['condition_id']}")
            continue
        run_monitored(args.config, config, condition, output_root)


if __name__ == "__main__":
    main()
