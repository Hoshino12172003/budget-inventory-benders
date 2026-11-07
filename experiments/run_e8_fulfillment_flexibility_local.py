"""E8 fixed-first-stage ex-post fulfillment flexibility evaluation.

The runner never re-optimizes first-stage variables.  It loads the certified
E1 PRB coordinates, freezes the scenario-independent arc sets, solves one
product-local recourse model at a time, and recomposes the 4,657 global
Gamma=2 scenarios.  Both pilot and formal solve paths are fail-closed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
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
from robust_inventory_reconfiguration.e8_fulfillment_flexibility import (
    MODES,
    ProductBlockResult,
    arc_manifest,
    build_mode_arcs,
    canonical_hash,
    checkpoint_payload,
    compose_scenario_results,
    policy_coordinates_hash,
    resource_estimate,
    scenario_manifest,
    solve_product_blocks,
    summarize_scenarios,
    validate_checkpoint,
    validate_mode_order,
    validate_nested_arcs,
)
from robust_inventory_reconfiguration.first_stage_solution import (
    load_first_stage_solution_artifact,
    matrix_from_artifact,
)
from robust_inventory_reconfiguration.formal_execution_freeze import (
    require_experiment_not_frozen,
    require_protocol_not_frozen,
)
from robust_inventory_reconfiguration.solver_profile import (
    FORMAL_SOLVER_NATIVE_PROFILE,
    FORMAL_SOLVER_PROFILE_ID,
)


EXPERIMENT_ID = "E8_EX_POST_FULFILLMENT_FLEXIBILITY_V1"
CONFIG = ROOT / "experiments/configs/formal/e8_ex_post_fulfillment_flexibility_v1.json"
OUTPUT_ROOT = ROOT / "experiments/results/e8_ex_post_fulfillment_flexibility_v1"
ANALYSIS_ROOT = ROOT / "experiments/analysis/e8_fulfillment_flexibility_v1"
E1_ROOT = ROOT / "experiments/results/e1_empirical_8case_v1"
E2_ROOT = ROOT / "experiments/results/e2_existing_nominal_robust_v1"
RUNNER_PATH = Path(__file__).resolve()
EVALUATOR_PATH = SRC / "robust_inventory_reconfiguration/e8_fulfillment_flexibility.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_config() -> dict[str, Any]:
    value = read_json(CONFIG)
    immutable = value.get("immutable_protocol")
    if value.get("immutable_protocol_sha256") != canonical_hash(immutable):
        raise RuntimeError("BLOCK_E8_IMMUTABLE_PROTOCOL_HASH")
    if immutable.get("experiment_id") != EXPERIMENT_ID:
        raise RuntimeError("BLOCK_E8_EXPERIMENT_ID")
    return value


def current_environment() -> dict[str, Any]:
    import gurobipy as gp
    import numpy

    return {
        "os": platform.platform(),
        "cpu": platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "physical_memory_gib": psutil.virtual_memory().total / 2**30,
        "python": platform.python_version(),
        "gurobi": ".".join(map(str, gp.gurobi.version())),
        "gurobipy": getattr(gp, "__version__", None),
        "numpy": numpy.__version__,
        "psutil": psutil.__version__,
    }


def validate_environment(config: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    current = current_environment()
    target = config["immutable_protocol"]["target_environment"]
    checks = {
        "python": current["python"] == target["python"],
        "gurobi": current["gurobi"] == target["gurobi"],
        "gurobipy": current["gurobipy"] == target["gurobipy"],
        "ram_floor": current["physical_memory_gib"]
        >= target["minimum_physical_memory_gib"],
    }
    if strict and not all(checks.values()):
        raise RuntimeError(f"BLOCK_E8_ENVIRONMENT_MISMATCH:{checks}")
    return {"observed": current, "target": target, "checks": checks}


def _identity_rows() -> dict[str, dict[str, str]]:
    with (ROOT / "table_empirical_8case_identity.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


def load_certified_policy(case_id: str, config: dict[str, Any]) -> dict[str, Any]:
    loaded = load_frozen_renault_case(case_id)
    instance = loaded["instance"]
    directory = E1_ROOT / f"E1-{case_id}-PRB"
    paths = {
        "result": directory / "result.json",
        "provenance": directory / "provenance.json",
        "first_stage_solution": directory / "first_stage_solution.json",
        "e2_robust_result": E2_ROOT / f"E2-{case_id}-ROBUST/result.json",
    }
    if any(not path.is_file() for path in paths.values()):
        missing = [str(path) for path in paths.values() if not path.is_file()]
        raise RuntimeError(f"BLOCK_E8_MISSING_FORMAL_SOURCE:{missing}")
    result = read_json(paths["result"])
    provenance = read_json(paths["provenance"])
    e2_result = read_json(paths["e2_robust_result"])
    artifact = load_first_stage_solution_artifact(
        paths["first_stage_solution"], instance
    )
    x = matrix_from_artifact(artifact, instance)
    y = [int(entry["value"]) for entry in artifact["y"]]
    expected = config["immutable_protocol"]["case_identities"][case_id]
    actual_hashes = {key: sha256(path) for key, path in paths.items()}
    actual_policy_hash = policy_coordinates_hash(y, x)
    required_result = {
        "status": "OPTIMAL",
        "exact_certification_status": "CERTIFIED_PRB_EXACT",
        "Gamma": 2,
        "beta": 1.0,
        "lambda_R": 0.05,
        "solver_profile": FORMAL_SOLVER_PROFILE_ID,
        "instance_hash": loaded["identity"]["instance_hash"],
        "x0_hash": loaded["identity"]["x0_hash"],
        "calibration_hash": loaded["identity"]["calibration_hash"],
    }
    if any(result.get(key) != value for key, value in required_result.items()):
        raise RuntimeError(f"BLOCK_E8_E1_RESULT_IDENTITY:{case_id}")
    if provenance.get("first_stage_solution_sha256") != actual_hashes[
        "first_stage_solution"
    ]:
        raise RuntimeError(f"BLOCK_E8_E1_PROVENANCE:{case_id}")
    if e2_result.get("reused_from_E1") is not True:
        raise RuntimeError(f"BLOCK_E8_E2_LINEAGE:{case_id}")
    tolerance = float(config["immutable_protocol"]["full_vs_e2_tolerance"])
    if abs(float(e2_result["objective_eval"]) - float(result["objective"])) > tolerance:
        raise RuntimeError(f"BLOCK_E8_E1_E2_OBJECTIVE:{case_id}")
    actual = {
        **loaded["identity"],
        **actual_hashes,
        "solution_payload_sha256": artifact["solution_payload_sha256"],
        "policy_coordinates_sha256": actual_policy_hash,
        "scenario_manifest_sha256": scenario_manifest(instance, 2)[
            "entries_sha256"
        ],
    }
    expected_policy_identity = {
        key: value for key, value in expected.items() if key != "arc_manifest_sha256"
    }
    if actual != expected_policy_identity:
        raise RuntimeError(f"BLOCK_E8_CASE_IDENTITY:{case_id}")
    return {
        **loaded,
        "y": y,
        "x": x,
        "artifact": artifact,
        "e1_result": result,
        "e2_result": e2_result,
        "formal_paths": paths,
        "formal_hashes": actual_hashes,
        "policy_hash": actual_policy_hash,
    }


def case_protocol(case_id: str, config: dict[str, Any]) -> dict[str, Any]:
    loaded = load_certified_policy(case_id, config)
    arcs = {
        mode: build_mode_arcs(loaded["instance"], loaded["y"], loaded["x"], mode)
        for mode in MODES
    }
    validate_nested_arcs(arcs["k1"], arcs["k2"], arcs["full"])
    manifests = {
        mode: arc_manifest(loaded["instance"], arcs[mode]) for mode in MODES
    }
    expected_arcs = config["immutable_protocol"]["case_identities"][case_id][
        "arc_manifest_sha256"
    ]
    if {mode: manifests[mode]["entries_sha256"] for mode in MODES} != expected_arcs:
        raise RuntimeError(f"BLOCK_E8_ARC_IDENTITY:{case_id}")
    return {"loaded": loaded, "arcs": arcs, "arc_manifests": manifests}


def validate_static_protocol() -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_config()
    require_protocol_not_frozen(ROOT, CONFIG)
    require_experiment_not_frozen(ROOT, EXPERIMENT_ID)
    immutable = config["immutable_protocol"]
    if tuple(immutable["cases"]) != CASE_IDS or tuple(immutable["modes"]) != MODES:
        raise RuntimeError("BLOCK_E8_SCOPE")
    if immutable["solver_profile_id"] != FORMAL_SOLVER_PROFILE_ID:
        raise RuntimeError("BLOCK_E8_SOLVER_PROFILE")
    if immutable["solver_native_profile"] != FORMAL_SOLVER_NATIVE_PROFILE:
        raise RuntimeError("BLOCK_E8_SOLVER_NATIVE_PROFILE")
    source_hashes = {
        "runner_sha256": sha256(RUNNER_PATH),
        "evaluator_sha256": sha256(EVALUATOR_PATH),
        "solver_profile_sha256": sha256(
            SRC / "robust_inventory_reconfiguration/solver_profile.py"
        ),
        "robust_service_sha256": sha256(
            SRC / "robust_inventory_reconfiguration/robust_service.py"
        ),
    }
    if source_hashes != immutable["source_hashes"]:
        raise RuntimeError("BLOCK_E8_SOURCE_IDENTITY")
    audits = {}
    for case_id in CASE_IDS:
        protocol = case_protocol(case_id, config)
        audits[case_id] = {
            "input_identity": config["immutable_protocol"]["case_identities"][case_id],
            "arc_counts": {
                mode: protocol["arc_manifests"][mode]["arc_count"] for mode in MODES
            },
            "resource_estimates": {
                mode: resource_estimate(
                    protocol["loaded"]["instance"], protocol["arcs"][mode], 2
                )
                for mode in MODES
            },
        }
    return config, {"source_hashes": source_hashes, "cases": audits}


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _is_ancestor(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT
        ).returncode
        == 0
    )


def validate_execution_gate(
    case_id: str, mode: str, *, pilot: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    config, audit = validate_static_protocol()
    authorization = config["authorization"]
    prefix = "pilot" if pilot else "formal"
    if authorization.get(f"{prefix}_run_authorized") is not True:
        raise PermissionError(f"E8_{prefix.upper()}_RUN_NOT_AUTHORIZED")
    if authorization.get(f"{prefix}_authorization_state") != "MANUAL_AUTHORIZATION":
        raise PermissionError(f"E8_{prefix.upper()}_AUTHORIZATION_STATE_INVALID")
    run_id = f"E8-{case_id}-{mode.upper()}"
    if run_id not in authorization.get(f"authorized_{prefix}_run_ids", []):
        raise PermissionError(f"E8_RUN_ID_NOT_AUTHORIZED:{run_id}")
    if pilot and case_id not in config["immutable_protocol"]["pilot_cases"]:
        raise PermissionError(f"E8_CASE_NOT_IN_PILOT_SCOPE:{case_id}")
    authorized_commit = authorization.get("authorized_code_commit")
    if not authorized_commit or not _is_ancestor(authorized_commit):
        raise RuntimeError("BLOCK_E8_AUTHORIZED_CODE_COMMIT")
    tracked = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True
    ).strip()
    if tracked:
        raise RuntimeError("BLOCK_E8_TRACKED_WORKTREE_NOT_CLEAN")
    validate_environment(config, strict=True)
    return config, audit


def condition_identity(
    case_id: str, mode: str, config: dict[str, Any], protocol: dict[str, Any], *, pilot: bool
) -> dict[str, Any]:
    immutable = config["immutable_protocol"]
    return {
        "experiment_id": EXPERIMENT_ID,
        "publication_status": "PILOT_NON_PUBLISHABLE" if pilot else "FORMAL",
        "case": case_id,
        "mode": mode,
        "git_commit": git_commit(),
        "immutable_protocol_sha256": config["immutable_protocol_sha256"],
        "config_sha256": sha256(CONFIG),
        "runner_sha256": immutable["source_hashes"]["runner_sha256"],
        "evaluator_sha256": immutable["source_hashes"]["evaluator_sha256"],
        "case_identity": immutable["case_identities"][case_id],
        "arc_manifest_sha256": protocol["arc_manifests"][mode]["entries_sha256"],
        "solver_profile_id": FORMAL_SOLVER_PROFILE_ID,
        "gurobi_threads": immutable["gurobi_threads"],
        "reporting_optimality_tolerance": immutable[
            "reporting_optimality_tolerance"
        ],
    }


def condition_id(case_id: str, mode: str, *, pilot: bool) -> str:
    suffix = "-PILOT" if pilot else ""
    return f"E8-{case_id}-{mode.upper()}{suffix}"


def result_dir(case_id: str, mode: str, *, pilot: bool) -> Path:
    root = OUTPUT_ROOT / ("pilot" if pilot else "formal")
    return root / condition_id(case_id, mode, pilot=pilot)


def _write_scenario_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


def _read_scenario_rows(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def verified_result(target: Path, expected_identity: dict[str, Any]) -> bool:
    if not target.exists():
        return False
    required = ("summary.json", "scenario_results.jsonl.gz", "provenance.json")
    if any(not (target / name).is_file() for name in required):
        raise RuntimeError(f"BLOCK_E8_PARTIAL_RESULT:{target}")
    provenance = read_json(target / "provenance.json")
    if provenance.get("identity") != expected_identity:
        raise RuntimeError(f"BLOCK_E8_RESULT_IDENTITY:{target}")
    for name in ("summary.json", "scenario_results.jsonl.gz"):
        if provenance.get("sha256", {}).get(name) != sha256(target / name):
            raise RuntimeError(f"BLOCK_E8_RESULT_HASH:{target / name}")
    rows = _read_scenario_rows(target / "scenario_results.jsonl.gz")
    if len(rows) != 4657 or summarize_scenarios(rows) != read_json(
        target / "summary.json"
    ):
        raise RuntimeError(f"BLOCK_E8_RESULT_COMPLETENESS:{target}")
    return True


def run_condition(
    case_id: str, mode: str, *, pilot: bool, resume: bool
) -> None:
    config, _ = validate_execution_gate(case_id, mode, pilot=pilot)
    protocol = case_protocol(case_id, config)
    identity = condition_identity(case_id, mode, config, protocol, pilot=pilot)
    target = result_dir(case_id, mode, pilot=pilot)
    if verified_result(target, identity):
        print(f"[VERIFIED SKIP] {target.name}", flush=True)
        return
    checkpoint_root = OUTPUT_ROOT / "checkpoints" / target.name
    if checkpoint_root.exists() and not resume:
        raise RuntimeError(f"BLOCK_E8_CHECKPOINT_REQUIRES_RESUME:{checkpoint_root}")
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    instance = protocol["loaded"]["instance"]
    expected_block_count = resource_estimate(instance, protocol["arcs"][mode], 2)[
        "local_blocks_per_product"
    ]
    blocks: list[ProductBlockResult] = []
    product_diagnostics = []
    solve_started = perf_counter()
    for product_index in range(instance.num_products):
        checkpoint_path = checkpoint_root / f"product_{product_index:02d}.json"
        checkpoint_identity = {**identity, "product_index": product_index}
        if checkpoint_path.is_file():
            restored = validate_checkpoint(
                read_json(checkpoint_path),
                checkpoint_identity,
                product_index,
                expected_block_count,
            )
            blocks.extend(restored)
            product_diagnostics.append(
                {"product_index": product_index, "resumed": True}
            )
            continue
        solved, diagnostics = solve_product_blocks(
            instance,
            protocol["loaded"]["x"],
            protocol["arcs"][mode],
            product_index,
            2,
            threads=config["immutable_protocol"]["gurobi_threads"],
            optimality_tolerance=config["immutable_protocol"][
                "reporting_optimality_tolerance"
            ],
        )
        write_json(
            checkpoint_path,
            checkpoint_payload(
                checkpoint_identity, product_index, solved, diagnostics
            ),
        )
        blocks.extend(solved)
        product_diagnostics.append(
            {"product_index": product_index, "resumed": False, **diagnostics}
        )
    rows = compose_scenario_results(instance, 2, blocks)
    if len(rows) != 4657:
        raise RuntimeError("BLOCK_E8_SCENARIO_COMPLETENESS")
    summary = summarize_scenarios(rows)
    if mode == "full":
        expected = float(protocol["loaded"]["e2_result"]["robust_recourse_cost"])
        observed = float(summary["worst_economic_cost"]["value"])
        tolerance = float(config["immutable_protocol"]["full_vs_e2_tolerance"])
        if abs(observed - expected) > tolerance:
            raise RuntimeError(
                f"BLOCK_E8_FULL_E2_MISMATCH:{observed}:{expected}:{tolerance}"
            )
    temporary = target.parent / f".tmp-{target.name}-{uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        write_json(temporary / "summary.json", summary)
        _write_scenario_rows(temporary / "scenario_results.jsonl.gz", rows)
        write_json(temporary / "arc_manifest.json", protocol["arc_manifests"][mode])
        write_json(
            temporary / "run_metrics.json",
            {
                "runtime_seconds": perf_counter() - solve_started,
                "product_models": product_diagnostics,
                "environment": current_environment(),
            },
        )
        provenance = {
            "identity": identity,
            "sha256": {
                name: sha256(temporary / name)
                for name in ("summary.json", "scenario_results.jsonl.gz")
            },
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(temporary / "provenance.json", provenance)
        if target.exists():
            raise FileExistsError(f"refusing to overwrite {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    if not verified_result(target, identity):
        raise RuntimeError(f"BLOCK_E8_POST_WRITE_VALIDATION:{target}")


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


def monitored_run(
    case_id: str, mode: str, *, pilot: bool, resume: bool
) -> None:
    config, _ = validate_execution_gate(case_id, mode, pilot=pilot)
    resource = config["immutable_protocol"]["resource_limits"]
    available = psutil.virtual_memory().available / 2**30
    if available < resource["minimum_available_memory_gib"]:
        raise RuntimeError("BLOCK_E8_LOW_AVAILABLE_MEMORY")
    command = [
        sys.executable,
        str(RUNNER_PATH),
        "--worker-condition",
        case_id,
        mode,
    ]
    if pilot:
        command.append("--pilot")
    if resume:
        command.append("--resume")
    log_root = OUTPUT_ROOT / "logs" / condition_id(case_id, mode, pilot=pilot)
    attempt = 1
    while (log_root / f"attempt-{attempt:03d}").exists():
        attempt += 1
    log_dir = log_root / f"attempt-{attempt:03d}"
    log_dir.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    peak = 0.0
    stop_reason = None
    timeout = resource[
        "pilot_timeout_seconds" if pilot else "formal_condition_timeout_seconds"
    ]
    with (log_dir / "stdout.log").open("w", encoding="utf-8") as stdout, (
        log_dir / "stderr.log"
    ).open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            peak = max(peak, tree_rss_gib(process.pid))
            available_now = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - started
            if peak >= resource["maximum_process_tree_rss_gib"]:
                stop_reason = "PROCESS_MEMORY_CAP"
            elif available_now <= resource["system_memory_floor_gib"]:
                stop_reason = "SYSTEM_MEMORY_FLOOR"
            elif elapsed >= timeout:
                stop_reason = "TIME_LIMIT"
            if stop_reason:
                terminate_tree(process.pid)
                break
            sleep(resource["monitor_interval_seconds"])
        return_code = process.poll()
    write_json(
        log_dir / "monitor.json",
        {
            "command": command,
            "return_code": return_code,
            "stop_reason": stop_reason,
            "peak_process_tree_rss_gib": peak,
            "wall_seconds": perf_counter() - started,
            "available_memory_before_gib": available,
        },
    )
    if stop_reason or return_code != 0:
        raise RuntimeError(f"E8_CONDITION_FAILED:{stop_reason or return_code}:{log_dir}")


def dry_run(*, preflight: bool) -> dict[str, Any]:
    config, audit = validate_static_protocol()
    report = {
        "experiment_id": EXPERIMENT_ID,
        "formal_run_authorized": config["authorization"]["formal_run_authorized"],
        "pilot_run_authorized": config["authorization"]["pilot_run_authorized"],
        "optimization_calls": 0,
        "environment": validate_environment(config, strict=False),
        "case_audit": audit["cases"],
        "preflight": preflight,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E8 fixed-policy post hoc fulfillment flexibility"
    )
    parser.add_argument("--case", choices=CASE_IDS)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--worker-condition", nargs=2, metavar=("CASE", "MODE"), help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    if args.worker_condition:
        case_id, mode = args.worker_condition
        run_condition(case_id, mode, pilot=args.pilot, resume=args.resume)
        return
    if args.dry_run or args.preflight:
        report = dry_run(preflight=args.preflight)
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        return
    if not args.case or not args.mode:
        parser.error("execution requires both --case and --mode")
    monitored_run(args.case, args.mode, pilot=args.pilot, resume=args.resume)


if __name__ == "__main__":
    main()
