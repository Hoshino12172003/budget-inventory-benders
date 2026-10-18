"""Development-only Vanilla Benders pilot for Renault case 210202.

The Vanilla oracle enumerates every admissible global shock scenario and solves
one all-product recourse LP per scenario.  It reuses the unchanged Pure master,
but not Pure's adversarial MILP oracle or Aggregate/PRB risk composition.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter, sleep
import traceback
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CASE_IDS = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
CASE_ID = CASE_IDS[0]
GAMMA = 2
LAMBDA_R = 0.05
TIME_LIMIT_SECONDS = 300.0
MAX_SCENARIOS = 5000
PROCESS_MEMORY_GIB = 4.0
SYSTEM_MEMORY_FLOOR_GIB = 3.0
START_AVAILABLE_MEMORY_GIB = 8.0
MONITOR_INTERVAL_SECONDS = 0.25
OBJECTIVE_TOLERANCE = 1e-4


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_frozen_renault_case(case_id: str = CASE_ID) -> dict[str, Any]:
    """Load and hash-check the paper-final Renault 8-case identity."""
    from robust_inventory_reconfiguration.instance import load_instance
    from robust_inventory_reconfiguration.renault_empirical import MAPPING_SHA256

    case_id = str(case_id)
    if case_id not in CASE_IDS:
        raise ValueError(f"case is outside the frozen Renault 8-case set: {case_id}")
    identity_path = ROOT / "table_empirical_8case_identity.csv"
    with identity_path.open(encoding="utf-8", newline="") as stream:
        identities = {row["case"]: row for row in csv.DictReader(stream)}
    identity = identities[case_id]
    instance_path = ROOT / f"data/formal_instances_v2/{case_id}.json"
    x0_path = ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case_id}.json"
    calibration_path = ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case_id}.json"
    actual = {
        "instance_hash": _sha256(instance_path),
        "x0_hash": _sha256(x0_path),
        "calibration_hash": _sha256(calibration_path),
    }
    for key, value in actual.items():
        if value != identity[key]:
            raise RuntimeError(f"frozen Renault identity mismatch: {key}")
    if identity["mapping_hash"] != MAPPING_SHA256:
        raise RuntimeError("frozen Renault mapping identity mismatch")

    instance = load_instance(instance_path)
    x0_artifact = json.loads(x0_path.read_text(encoding="utf-8"))
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    x0 = x0_artifact["x0"]
    if instance.initial_inventory != x0:
        raise RuntimeError("instance initial inventory differs from frozen x0 artifact")
    if calibration["instance_sha256"] != actual["instance_hash"]:
        raise RuntimeError("calibration references a different instance")
    if calibration["x0_sha256"] != actual["x0_hash"]:
        raise RuntimeError("calibration references a different x0")
    return {
        "instance": instance,
        "x0": x0,
        "budget": float(calibration["B_ref"]),
        "gamma": GAMMA,
        "lambda_r": LAMBDA_R,
        "identity": {**actual, "mapping_hash": identity["mapping_hash"]},
        "paths": {
            "instance": str(instance_path),
            "x0": str(x0_path),
            "calibration": str(calibration_path),
        },
    }


class GlobalEnumeratedLPOracle:
    """Exact global-scenario oracle using sequential all-product primal LPs."""

    max_scenarios = MAX_SCENARIOS
    trace_path: Path | None = None

    def __init__(self, instance: Any, gamma: int):
        import gurobipy as gp
        from gurobipy import GRB
        from robust_inventory_reconfiguration.solver_profile import apply_formal_solver_profile

        self.instance = instance
        self.gamma = gamma
        self.I = instance.num_depots
        self.R = instance.num_regions
        self.J = instance.num_products
        self.total_scenarios = sum(
            math.comb(self.R * self.J, size) for size in range(gamma + 1)
        )
        if self.total_scenarios > self.max_scenarios:
            raise RuntimeError(
                f"{self.total_scenarios} global scenarios exceed safety cap {self.max_scenarios}"
            )
        model = gp.Model("vanilla_global_scenario_lp")
        model.Params.OutputFlag = 0
        apply_formal_solver_profile(model, mixed_integer=False)
        q = model.addVars(
            range(self.I), range(self.R), range(self.J), lb=0.0, name="q"
        )
        u = model.addVars(range(self.R), range(self.J), lb=0.0, name="u")
        e = model.addVars(range(self.J), lb=0.0, name="e")
        self.demand = {
            (r, j): model.addConstr(
                gp.quicksum(q[i, r, j] for i in range(self.I)) + u[r, j] >= 0.0
            )
            for r in range(self.R)
            for j in range(self.J)
        }
        self.supply = {
            (i, j): model.addConstr(
                gp.quicksum(q[i, r, j] for r in range(self.R)) <= 0.0
            )
            for i in range(self.I)
            for j in range(self.J)
        }
        self.service = {
            j: model.addConstr(
                gp.quicksum(u[r, j] for r in range(self.R)) - e[j] <= 0.0
            )
            for j in range(self.J)
        }
        objective = gp.quicksum(
            instance.transport_cost[i][r][j] * q[i, r, j]
            for i in range(self.I)
            for r in range(self.R)
            for j in range(self.J)
        )
        objective += gp.quicksum(
            instance.shortage_penalty[r][j] * u[r, j]
            for r in range(self.R)
            for j in range(self.J)
        )
        objective += gp.quicksum(
            instance.service_penalty[j] * e[j] for j in range(self.J)
        )
        model.setObjective(objective, GRB.MINIMIZE)
        self.model = model

    def solve(
        self, x: list[list[float]], *, time_limit: float | None = None, certify: bool = True
    ) -> Any:
        from gurobipy import GRB
        from robust_inventory_reconfiguration.pure_benders import (
            GlobalAdversarialResult,
            PureAggregateCut,
            PureBendersTimeout,
        )

        started = perf_counter()
        for i in range(self.I):
            for j in range(self.J):
                self.supply[i, j].RHS = max(0.0, float(x[i][j]))
        baseline = [
            [float(self.instance.base_demand[r][j]) for j in range(self.J)]
            for r in range(self.R)
        ]
        base_totals = [
            sum(baseline[r][j] for r in range(self.R)) for j in range(self.J)
        ]
        pairs = [(r, j) for r in range(self.R) for j in range(self.J)]
        previous: set[tuple[int, int]] = set()
        best = -float("inf")
        best_payload: tuple[Any, ...] | None = None
        solved = 0
        for size in range(self.gamma + 1):
            for pattern_tuple in itertools.combinations(pairs, size):
                if time_limit is not None:
                    remaining = time_limit - (perf_counter() - started)
                    if remaining <= 0:
                        raise PureBendersTimeout(
                            f"Vanilla oracle expired after {solved}/{self.total_scenarios} scenarios"
                        )
                    self.model.Params.TimeLimit = max(0.001, remaining)
                pattern = set(pattern_tuple)
                for r, j in previous ^ pattern:
                    self.demand[r, j].RHS = baseline[r][j] + (
                        float(self.instance.demand_deviation[r][j])
                        if (r, j) in pattern
                        else 0.0
                    )
                if solved == 0:
                    for r, j in pairs:
                        self.demand[r, j].RHS = baseline[r][j]
                for j in range(self.J):
                    shocked_total = base_totals[j] + sum(
                        float(self.instance.demand_deviation[r][jj])
                        for r, jj in pattern
                        if jj == j
                    )
                    self.service[j].RHS = (
                        1.0 - float(self.instance.service_level[j])
                    ) * shocked_total
                self.model.optimize()
                if self.model.Status == GRB.TIME_LIMIT:
                    raise PureBendersTimeout(
                        f"Vanilla oracle LP time limit at scenario {solved + 1}"
                    )
                if self.model.Status != GRB.OPTIMAL:
                    raise RuntimeError(
                        f"Vanilla oracle LP status={self.model.Status}, scenario={pattern_tuple}"
                    )
                solved += 1
                previous = pattern
                value = float(self.model.ObjVal)
                if value > best + 1e-9 or best_payload is None:
                    beta = tuple(
                        tuple(float(self.supply[i, j].Pi) for j in range(self.J))
                        for i in range(self.I)
                    )
                    demand_dual = {
                        (r, j): float(self.demand[r, j].Pi) for r, j in pairs
                    }
                    service_dual = {
                        j: float(self.service[j].Pi) for j in range(self.J)
                    }
                    rhs_dual = sum(
                        self.demand[r, j].RHS * demand_dual[r, j] for r, j in pairs
                    )
                    rhs_dual += sum(
                        self.service[j].RHS * service_dual[j] for j in range(self.J)
                    )
                    rhs_dual += sum(
                        float(x[i][j]) * beta[i][j]
                        for i in range(self.I)
                        for j in range(self.J)
                    )
                    alpha = rhs_dual - sum(
                        float(x[i][j]) * beta[i][j]
                        for i in range(self.I)
                        for j in range(self.J)
                    )
                    violations = [
                        *(-demand_dual[r, j] for r, j in pairs),
                        *(beta[i][j] for i in range(self.I) for j in range(self.J)),
                        *(service_dual[j] for j in range(self.J)),
                        *(
                            demand_dual[r, j]
                            + beta[i][j]
                            - self.instance.transport_cost[i][r][j]
                            for i in range(self.I)
                            for r in range(self.R)
                            for j in range(self.J)
                        ),
                        *(
                            demand_dual[r, j]
                            + service_dual[j]
                            - self.instance.shortage_penalty[r][j]
                            for r, j in pairs
                        ),
                        *(
                            -service_dual[j] - self.instance.service_penalty[j]
                            for j in range(self.J)
                        ),
                    ]
                    maximum_violation = max(0.0, max(violations))
                    best = value
                    best_payload = (
                        pattern_tuple,
                        alpha,
                        beta,
                        maximum_violation,
                        abs(value - rhs_dual),
                    )
        assert best_payload is not None
        pattern, alpha, beta, dual_violation, residual = best_payload
        cut = PureAggregateCut(
            alpha,
            beta,
            best,
            tuple(tuple(row) for row in x),
            pattern,
            dual_violation <= 1e-7,
            residual,
        )
        elapsed = perf_counter() - started
        if self.trace_path is not None:
            with self.trace_path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {
                            "scenarios_solved": solved,
                            "oracle_seconds": elapsed,
                            "value": best,
                            "dual_feasibility_max_violation": dual_violation,
                            "strong_duality_residual": residual,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        return GlobalAdversarialResult(
            best,
            cut,
            best,
            elapsed,
            0.0,
            0,
            self.I * self.R * self.J + self.R * self.J + self.J,
            len(self.demand) + len(self.supply) + len(self.service),
        )


def _tiny_inputs() -> tuple[Any, list[list[float]], float, int, float]:
    from robust_inventory_reconfiguration.instance import InventoryInstance

    instance = InventoryInstance(
        name="vanilla-validation-tiny",
        depot_ids=["D1"],
        region_ids=["R1", "R2"],
        product_ids=["P1", "P2"],
        base_demand=[[4.0, 3.0], [2.0, 1.0]],
        demand_deviation=[[1.0, 2.0], [3.0, 4.0]],
        transport_cost=[[[1.0, 2.0], [3.0, 4.0]]],
        shortage_penalty=[[10.0, 20.0], [30.0, 40.0]],
        service_level=[0.5, 0.5],
        service_penalty=[100.0, 200.0],
        capacity=[20.0],
        inventory_upper_bound=[[10.0, 10.0]],
        fixed_depot_cost=[5.0],
        inventory_cost=[[1.0, 1.0]],
        product_volume=[1.0, 2.0],
        initial_inventory=None,
        reconfiguration_cost_multiplier=None,
        provenance={"fixture": "vanilla-development-validation"},
    )
    return instance, [[2.0, 1.0]], 18.0, 2, LAMBDA_R


def _install_vanilla_oracle(trace_path: Path) -> Any:
    import robust_inventory_reconfiguration.pure_benders as pure

    original = pure.GlobalRobustAdversarialSubproblem
    GlobalEnumeratedLPOracle.max_scenarios = MAX_SCENARIOS
    GlobalEnumeratedLPOracle.trace_path = trace_path
    pure.GlobalRobustAdversarialSubproblem = GlobalEnumeratedLPOracle
    return original


def _certify_solution(
    instance: Any,
    solution: Any,
    *,
    remaining_seconds: float,
) -> dict[str, Any]:
    oracle = GlobalEnumeratedLPOracle(instance, GAMMA)
    certified = oracle.solve(solution.x, time_limit=remaining_seconds)
    objective = solution.first_stage_expenditure + certified.value
    return {
        "certified_recourse": certified.value,
        "certified_objective": objective,
        "objective_residual": abs(objective - solution.objective),
        "dual_feasible": certified.cut.dual_feasible,
        "strong_duality_residual": certified.cut.strong_duality_error,
        "pass": (
            certified.cut.dual_feasible
            and certified.cut.strong_duality_error <= OBJECTIVE_TOLERANCE
            and abs(objective - solution.objective) <= OBJECTIVE_TOLERANCE
        ),
    }


def _run_micro(output_dir: Path) -> dict[str, Any]:
    import robust_inventory_reconfiguration.pure_benders as pure
    from robust_inventory_reconfiguration.exact_benchmark import solve_global_scenario_benchmark

    instance, x0, budget, gamma, lambda_r = _tiny_inputs()
    direct = solve_global_scenario_benchmark(instance, x0, budget, gamma, lambda_r)
    original = _install_vanilla_oracle(output_dir / "oracle_trace.jsonl")
    try:
        vanilla = pure.solve_pure_benders(
            instance, x0, budget, gamma, lambda_r, time_limit=120.0
        )
    finally:
        pure.GlobalRobustAdversarialSubproblem = original
    if direct.solution is None:
        raise RuntimeError("tiny Direct validation did not return a solution")
    points = [cut.generation_x for cut in vanilla.cuts]
    points.append(tuple(tuple(row) for row in vanilla.solution.x))
    unique_points = list(dict.fromkeys(points))
    recourse_by_point: dict[tuple[tuple[float, ...], ...], float] = {}
    for point in unique_points:
        checked = GlobalEnumeratedLPOracle(instance, gamma).solve(
            [list(row) for row in point], time_limit=30.0
        )
        recourse_by_point[point] = checked.value
    max_cut_excess = max(
        (
            cut.value_at([list(row) for row in point]) - recourse_by_point[point]
            for cut in vanilla.cuts
            for point in unique_points
        ),
        default=0.0,
    )
    result = {
        "status": "PASS",
        "direct_status": direct.status,
        "direct_objective": direct.solution.objective,
        "vanilla_status": vanilla.status,
        "vanilla_objective": vanilla.solution.objective,
        "objective_difference": abs(direct.solution.objective - vanilla.solution.objective),
        "dual_feasibility_pass": all(cut.dual_feasible for cut in vanilla.cuts),
        "maximum_strong_duality_residual": max(
            (cut.strong_duality_error for cut in vanilla.cuts), default=0.0
        ),
        "maximum_cut_validity_excess": max(0.0, max_cut_excess),
        "cut_count": vanilla.aggregate_cut_count,
        "iteration_count": len(vanilla.iterations),
    }
    passed = (
        direct.status == "OPTIMAL"
        and vanilla.status == "OPTIMAL"
        and result["objective_difference"] <= OBJECTIVE_TOLERANCE
        and result["dual_feasibility_pass"]
        and result["maximum_strong_duality_residual"] <= OBJECTIVE_TOLERANCE
        and result["maximum_cut_validity_excess"] <= OBJECTIVE_TOLERANCE
    )
    result["status"] = "PASS" if passed else "FAIL"
    return result


def _run_method(method: str, output_dir: Path, case_id: str) -> dict[str, Any]:
    import gurobipy as gp
    import robust_inventory_reconfiguration.pure_benders as pure
    from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders

    loaded = load_frozen_renault_case(case_id)
    instance = loaded["instance"]
    x0 = loaded["x0"]
    budget = loaded["budget"]
    started = perf_counter()
    if method == "vanilla":
        original = _install_vanilla_oracle(output_dir / "oracle_trace.jsonl")
        try:
            solved = pure.solve_pure_benders(
                instance,
                x0,
                budget,
                GAMMA,
                LAMBDA_R,
                time_limit=TIME_LIMIT_SECONDS,
                log_file=output_dir / "solver.log",
            )
        finally:
            pure.GlobalRobustAdversarialSubproblem = original
        iterations = len(solved.iterations)
        cuts = solved.aggregate_cut_count
        oracle_seconds = solved.global_oracle_runtime
        cut_validity_pass = solved.cut_validity_pass
        maximum_cut_strong_duality_residual = max(
            (cut.strong_duality_error for cut in solved.cuts), default=0.0
        )
        internal_exact = solved.exact_certification_pass and cut_validity_pass
    else:
        solved = solve_prb_benders(instance, x0, budget, GAMMA, LAMBDA_R)
        iterations = len(solved.iterations)
        cuts = solved.unique_product_cuts
        oracle_seconds = solved.separation_runtime
        cut_validity_pass = all(
            cut.dual_feasible and cut.strong_duality_error <= OBJECTIVE_TOLERANCE
            for cut in solved.cuts
        )
        maximum_cut_strong_duality_residual = max(
            (cut.strong_duality_error for cut in solved.cuts), default=0.0
        )
        internal_exact = (
            solved.exact_certification_pass and solved.global_risk_budget_coupling_pass
            and cut_validity_pass
        )
    elapsed_before_certification = perf_counter() - started
    remaining = TIME_LIMIT_SECONDS - elapsed_before_certification
    if remaining <= 0:
        raise TimeoutError("no time remains for independent global certification")
    certification_started = perf_counter()
    independent = _certify_solution(
        instance, solved.solution, remaining_seconds=remaining
    )
    certification_seconds = perf_counter() - certification_started
    total = perf_counter() - started
    exact = solved.status == "OPTIMAL" and internal_exact and independent["pass"]
    return {
        "method": "Vanilla-BD" if method == "vanilla" else "PRB-BD",
        "status": solved.status,
        "objective": solved.solution.objective,
        "iterations": iterations,
        "oracle_seconds": oracle_seconds,
        "cut_count": cuts,
        "cut_validity_pass": cut_validity_pass,
        "maximum_cut_strong_duality_residual": maximum_cut_strong_duality_residual,
        "algorithm_seconds": elapsed_before_certification,
        "independent_certification_seconds": certification_seconds,
        "total_seconds": total,
        "internal_exact_certification_pass": internal_exact,
        "independent_global_certification": independent,
        "exact_certification_pass": exact,
        "solver_profile": "gurobi-balanced-1e-8-v1",
        "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        "identity": loaded["identity"],
    }


def _worker(mode: str, output_dir: Path, case_id: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        result = (
            _run_micro(output_dir)
            if mode == "micro"
            else _run_method(mode, output_dir, case_id)
        )
        _write_json(output_dir / "result.json", result)
        return 0 if result.get("status") in {"PASS", "OPTIMAL"} else 1
    except Exception as error:
        (output_dir / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _write_json(
            output_dir / "result.json",
            {
                "method": mode,
                "status": "FAILED",
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        return 1


def _process_tree_rss(pid: int) -> int:
    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0
    total = 0
    for process in processes:
        try:
            total += process.memory_info().rss
        except psutil.Error:
            pass
    return total


def _stop_process_tree(pid: int) -> None:
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
    psutil.wait_procs(alive, timeout=3)


def _run_monitored(
    mode: str, root: Path, limit: float, case_id: str = CASE_ID
) -> dict[str, Any]:
    available = psutil.virtual_memory().available / 2**30
    if available < START_AVAILABLE_MEMORY_GIB:
        raise RuntimeError(
            f"start memory gate failed: {available:.3f} GiB < {START_AVAILABLE_MEMORY_GIB:.3f} GiB"
        )
    target = root / mode
    stdout_path = root / f"{mode}_stdout.log"
    stderr_path = root / f"{mode}_stderr.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        mode,
        "--output-dir",
        str(target),
        "--case",
        case_id,
    ]
    started = perf_counter()
    peak = 0
    stop_reason = None
    samples = []
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            elapsed = perf_counter() - started
            rss = _process_tree_rss(process.pid)
            available = psutil.virtual_memory().available
            peak = max(peak, rss)
            samples.append(
                {
                    "elapsed_seconds": elapsed,
                    "process_tree_rss_gib": rss / 2**30,
                    "system_available_gib": available / 2**30,
                }
            )
            if elapsed >= limit:
                stop_reason = "TIME_LIMIT"
            elif rss / 2**30 > PROCESS_MEMORY_GIB:
                stop_reason = "RESOURCE_PROCESS_CAP"
            elif available / 2**30 < SYSTEM_MEMORY_FLOOR_GIB:
                stop_reason = "RESOURCE_SYSTEM_CAP"
            if stop_reason is not None:
                _stop_process_tree(process.pid)
                break
            sleep(MONITOR_INTERVAL_SECONDS)
        return_code = process.poll()
    monitor = {
        "mode": mode,
        "elapsed_seconds": perf_counter() - started,
        "peak_process_tree_rss_gib": peak / 2**30,
        "stop_reason": stop_reason,
        "worker_return_code": return_code,
        "limits": {
            "time_seconds": limit,
            "process_tree_gib": PROCESS_MEMORY_GIB,
            "system_available_floor_gib": SYSTEM_MEMORY_FLOOR_GIB,
            "start_available_gib": START_AVAILABLE_MEMORY_GIB,
            "monitor_interval_seconds": MONITOR_INTERVAL_SECONDS,
        },
        "samples": samples,
    }
    _write_json(root / f"{mode}_resource_monitor.json", monitor)
    result_path = target / "result.json"
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else {"method": mode, "status": stop_reason or "WORKER_FAILED"}
    )
    result["peak_process_tree_rss_gib"] = monitor["peak_process_tree_rss_gib"]
    result["resource_stop_reason"] = stop_reason
    result["worker_return_code"] = return_code
    _write_json(root / f"{mode}_outcome.json", result)
    return result


def _write_hashes(output_dir: Path) -> None:
    files = sorted(
        path for path in output_dir.rglob("*") if path.is_file() and path.name != "sha256.txt"
    )
    lines = [f"{_sha256(path)}  {path.relative_to(output_dir).as_posix()}" for path in files]
    (output_dir / "sha256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pilot(output_dir: Path, case_id: str = CASE_ID) -> dict[str, Any]:
    import gurobipy as gp

    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite development output: {output_dir}")
    output_dir.mkdir(parents=True)
    loaded = load_frozen_renault_case(case_id)
    scenarios = sum(
        math.comb(loaded["instance"].num_regions * loaded["instance"].num_products, size)
        for size in range(GAMMA + 1)
    )
    protocol = {
        "classification": "DEVELOPMENT_ONLY_NOT_FORMAL_EVIDENCE",
        "case_id": case_id,
        "dimensions": {
            "I": loaded["instance"].num_depots,
            "R": loaded["instance"].num_regions,
            "J": loaded["instance"].num_products,
        },
        "budget": loaded["budget"],
        "Gamma": GAMMA,
        "lambda_R": LAMBDA_R,
        "global_scenario_count": scenarios,
        "maximum_scenarios": MAX_SCENARIOS,
        "time_limit_seconds_per_method": TIME_LIMIT_SECONDS,
        "resource_limits": {
            "process_tree_gib": PROCESS_MEMORY_GIB,
            "system_available_floor_gib": SYSTEM_MEMORY_FLOOR_GIB,
            "start_available_gib": START_AVAILABLE_MEMORY_GIB,
            "monitor_interval_seconds": MONITOR_INTERVAL_SECONDS,
            "sequential_single_process": True,
        },
        "python": sys.version,
        "python_executable": sys.executable,
        "gurobi_version": ".".join(map(str, gp.gurobi.version())),
        "platform": platform.platform(),
        "identity": loaded["identity"],
        "source_paths": loaded["paths"],
        "implementation_note": (
            "Vanilla reuses only the unchanged Pure single-theta master; its oracle "
            "is exhaustive global scenario enumeration and does not call Pure's "
            "global adversarial MILP or Aggregate/PRB product-risk composition."
        ),
    }
    _write_json(output_dir / "protocol.json", protocol)
    if scenarios > MAX_SCENARIOS:
        raise RuntimeError(f"scenario safety cap failed: {scenarios} > {MAX_SCENARIOS}")
    micro = _run_monitored("micro", output_dir, 120.0)
    if micro.get("status") != "PASS":
        summary = {"status": "BLOCKED_BY_MICRO_VALIDATION", "micro": micro}
        _write_json(output_dir / "summary.json", summary)
        _write_hashes(output_dir)
        return summary
    vanilla = _run_monitored("vanilla", output_dir, TIME_LIMIT_SECONDS, case_id)
    prb = _run_monitored("prb", output_dir, TIME_LIMIT_SECONDS, case_id)
    paired = bool(
        vanilla.get("status") == "OPTIMAL"
        and vanilla.get("exact_certification_pass") is True
        and vanilla.get("resource_stop_reason") is None
        and prb.get("status") == "OPTIMAL"
        and prb.get("exact_certification_pass") is True
        and prb.get("resource_stop_reason") is None
    )
    summary = {
        "status": "COMPLETE",
        "micro_validation": micro,
        "vanilla": vanilla,
        "prb": prb,
        "valid_exact_pair": paired,
        "interpretation": (
            "A method failure or resource stop is not evidence that the other method won."
        ),
    }
    _write_json(output_dir / "summary.json", summary)
    _write_hashes(output_dir)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "experiments/results/renault_vanilla_bd_pilot_210202_development_v1",
    )
    parser.add_argument("--worker", choices=("micro", "vanilla", "prb"))
    parser.add_argument("--case", choices=CASE_IDS, default=CASE_ID)
    args = parser.parse_args()
    if args.worker:
        return _worker(args.worker, args.output_dir, args.case)
    summary = run_pilot(args.output_dir.resolve(), args.case)
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
