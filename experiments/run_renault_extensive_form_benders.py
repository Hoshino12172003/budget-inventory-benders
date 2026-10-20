from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from experiments import run_renault_enhanced_basic_benders as base
from experiments.run_renault_vanilla_bd_pilot import load_frozen_renault_case
from robust_inventory_reconfiguration.enhanced_basic_benders import (
    EnhancedGlobalEnumeratedLPOracle,
)
from robust_inventory_reconfiguration.extensive_form_benders import (
    solve_extensive_form_benders,
)


DEFAULT_CONFIG = ROOT / "experiments/configs/development/renault_extensive_form_benders_v1.yaml"
EXPECTED_CASES = base.EXPECTED_CASES
EXPECTED_CONDITIONS = tuple(f"EF_RENAULT_{case}" for case in EXPECTED_CASES)
_BASE_LOAD_CONFIG = base.load_config
_BASE_ACTIVE_WORKERS = base.active_workers
_BASE_RESOURCE_POLICY = _BASE_LOAD_CONFIG()["resource_policy"]


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("protocol_id") != "RENAULT_EF_BD_8CASE_V1":
        raise RuntimeError("unexpected EF-BD protocol identity")
    if tuple(config.get("case_ids", ())) != EXPECTED_CASES:
        raise RuntimeError("EF-BD case scope differs from the frozen Renault order")
    if tuple(config.get("authorized_condition_ids", ())) != EXPECTED_CONDITIONS:
        raise RuntimeError("EF-BD condition allowlist differs from the frozen scope")
    if config.get("fixed_scientific_parameters") != {"Gamma": 2, "lambda_R": 0.05}:
        raise RuntimeError("EF-BD scientific parameters differ from the frozen protocol")
    if config.get("resource_policy") != _BASE_RESOURCE_POLICY:
        raise RuntimeError("EF-BD resource contract differs from the audited Renault contract")
    algorithm = config["algorithm"]
    required = {
        "global_theta_count": 1,
        "cuts_per_iteration_maximum": 1,
        "monolithic_direct_recourse_lp": True,
        "optimizer_calls_per_oracle": 1,
        "scenario_pruning": False,
        "product_subproblem_decomposition": False,
        "product_multicut": False,
        "compact_global_robust_milp_oracle": False,
        "independent_global_certification_required": True,
    }
    if any(algorithm.get(key) != value for key, value in required.items()):
        raise RuntimeError("EF-BD algorithm boundary differs from the audited design")
    return config


def condition_identity(config: dict[str, Any], case_id: str) -> dict[str, Any]:
    loaded = load_frozen_renault_case(case_id)
    instance = loaded["instance"]
    expected = config["frozen_case_identity"][case_id]
    checks = {
        key: loaded["identity"][key] == expected[key]
        for key in ("instance_hash", "x0_hash", "calibration_hash", "mapping_hash")
    }
    checks.update({"Gamma": loaded["gamma"] == 2, "lambda_R": loaded["lambda_r"] == 0.05})
    return {
        "case_id": case_id,
        "condition_id": f"EF_RENAULT_{case_id}",
        "dimensions": [instance.num_depots, instance.num_regions, instance.num_products],
        "budget": loaded["budget"],
        "Gamma": loaded["gamma"],
        "lambda_R": loaded["lambda_r"],
        "global_scenario_count": sum(
            math.comb(instance.num_regions * instance.num_products, size)
            for size in range(loaded["gamma"] + 1)
        ),
        "identity": loaded["identity"],
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


def active_workers() -> list[dict[str, Any]]:
    found = _BASE_ACTIVE_WORKERS()
    for process in base.psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or []).lower()
            if "run_renault_extensive_form_benders.py" in command and "--worker" in command:
                found.append({"pid": process.info["pid"], "name": process.info.get("name")})
        except base.psutil.Error:
            continue
    return found


def certify_solution(instance: Any, solution: Any, gamma: int, time_limit: float) -> dict[str, Any]:
    oracle = EnhancedGlobalEnumeratedLPOracle(instance, gamma)
    try:
        certified = oracle.solve(solution.x, time_limit=time_limit)
    finally:
        oracle.close()
    objective = solution.first_stage_expenditure + certified.value
    residual = abs(objective - solution.objective)
    return {
        "certified_recourse": certified.value,
        "certified_objective": objective,
        "objective_residual": residual,
        "dual_feasible": certified.cut.dual_feasible,
        "strong_duality_residual": certified.cut.strong_duality_error,
        "pass": certified.cut.dual_feasible
        and certified.cut.strong_duality_error <= 1e-4
        and residual <= 1e-4,
    }


def solve_condition(config_path: Path, condition_id: str, attempt_root: Path) -> dict[str, Any]:
    import gurobipy as gp

    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: Renault EF-BD execution is disabled")
    if condition_id not in EXPECTED_CONDITIONS:
        raise RuntimeError("condition is outside the EF-BD allowlist")
    if attempt_root.exists():
        raise FileExistsError(f"refusing to overwrite attempt: {attempt_root}")
    attempt_root.mkdir(parents=True)
    case_id = condition_id.rsplit("_", 1)[1]
    identity = condition_identity(config, case_id)
    if identity["status"] != "PASS":
        raise RuntimeError(f"IDENTITY_FAILURE: {identity['checks']}")
    loaded = load_frozen_renault_case(case_id)
    started = perf_counter()
    solved, diagnostics = solve_extensive_form_benders(
        loaded["instance"], loaded["x0"], loaded["budget"], loaded["gamma"], loaded["lambda_r"],
        relative_gap_tolerance=config["solver_tolerances"]["relative_gap"],
        cut_tolerance=config["solver_tolerances"]["cut_violation"],
        objective_certification_tolerance=config["solver_tolerances"]["objective_certification"],
        max_iterations=config["algorithm"]["max_iterations"],
        time_limit=config["resource_policy"]["condition_time_limit_seconds"],
        log_file=attempt_root / "solver.log",
        trace_path=attempt_root / "oracle_trace.jsonl",
    )
    algorithm_seconds = perf_counter() - started
    remaining = config["resource_policy"]["condition_time_limit_seconds"] - algorithm_seconds
    if remaining <= 0:
        raise TimeoutError("no time remains for independent global certification")
    certification_started = perf_counter()
    independent = certify_solution(loaded["instance"], solved.solution, loaded["gamma"], remaining)
    certification_seconds = perf_counter() - certification_started
    exact = bool(solved.status == "OPTIMAL" and solved.exact_certification_pass and solved.cut_validity_pass and independent["pass"])
    base.write_json(attempt_root / "iteration_trajectory.json", [asdict(row) for row in solved.iterations])
    base.write_json(attempt_root / "first_stage_solution.json", {
        "y": solved.solution.y, "x": solved.solution.x,
        "a_plus": solved.solution.a_plus, "a_minus": solved.solution.a_minus,
    })
    result = {
        "schema": "renault_ef_bd_result_v1", "experiment_id": config["experiment_id"],
        "protocol_id": config["protocol_id"], "condition_id": condition_id,
        "case_id": case_id, "attempt": "attempt-001", "method": "EF-BD",
        "solver_status": solved.status, "exact_certification": exact,
        "cut_validity": solved.cut_validity_pass, "objective": solved.solution.objective,
        "final_lower_bound": solved.final_lower_bound, "final_upper_bound": solved.final_upper_bound,
        "final_absolute_gap": solved.final_absolute_gap, "final_relative_gap": solved.final_relative_gap,
        "iterations": len(solved.iterations), "cuts_added": solved.aggregate_cut_count,
        "master_seconds": solved.master_runtime, "oracle_seconds": solved.global_oracle_runtime,
        "algorithm_core_time_seconds": algorithm_seconds,
        "independent_certification_seconds": certification_seconds,
        "total_time_seconds": algorithm_seconds + certification_seconds,
        "independent_global_certification": independent, "oracle_engineering": diagnostics,
        "solver_profile": config["solver_profile"],
        "gurobi_version": ".".join(map(str, gp.gurobi.version())), "identity": loaded["identity"],
    }
    base.write_json(attempt_root / "result.json", result)
    provenance = {
        "schema": "renault_ef_bd_provenance_v1", "condition_id": condition_id,
        "attempt": "attempt-001", "formal_run_authorized": True,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "config_path": str(config_path), "config_sha256": base.sha256(config_path),
        "implementation_sha256": base.sha256(ROOT / "src/robust_inventory_reconfiguration/extensive_form_benders.py"),
        "runner_sha256": base.sha256(Path(__file__).resolve()),
        "result_sha256": base.sha256(attempt_root / "result.json"),
        "trajectory_sha256": base.sha256(attempt_root / "iteration_trajectory.json"),
        "first_stage_sha256": base.sha256(attempt_root / "first_stage_solution.json"),
        "identity": loaded["identity"],
    }
    base.write_json(attempt_root / "provenance.json", provenance)
    if not exact:
        raise RuntimeError("NUMERICAL_CERTIFICATION_FAILURE: EF-BD result is not exact-certified")
    return result


base.DEFAULT_CONFIG = DEFAULT_CONFIG
base.EXPECTED_CASES = EXPECTED_CASES
base.EXPECTED_CONDITIONS = EXPECTED_CONDITIONS
base.load_config = load_config
base.condition_identity = condition_identity
base.active_workers = active_workers
base.solve_condition = solve_condition
base.__file__ = __file__


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--worker", choices=EXPECTED_CONDITIONS)
    parser.add_argument("--attempt-root", type=Path)
    args = parser.parse_args()
    if args.worker:
        if args.attempt_root is None:
            parser.error("--worker requires --attempt-root")
        return base.worker_main(args.config, args.worker, args.attempt_root)
    result = base.execute_batch(args.config) if args.execute else base.build_dry_run(args.config)
    result["schema"] = "renault_ef_bd_dry_run_v1" if not args.execute else "renault_ef_bd_batch_v1"
    result["environment"] = result.get("environment", {}) | {"platform": platform.platform(), "python_version": platform.python_version()}
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
