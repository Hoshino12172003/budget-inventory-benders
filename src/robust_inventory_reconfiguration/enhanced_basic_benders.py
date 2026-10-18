from __future__ import annotations

from dataclasses import dataclass
import itertools
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Any

from .pure_benders import GlobalAdversarialResult, PureAggregateCut, PureBendersTimeout
from .solver_profile import apply_formal_solver_profile


@dataclass(frozen=True)
class ScenarioRhsPlan:
    pattern: tuple[tuple[int, int], ...]
    demand_rhs: tuple[float, ...]
    service_rhs: tuple[float, ...]


def enumerate_global_patterns(
    num_regions: int, num_products: int, gamma: int
) -> tuple[tuple[tuple[int, int], ...], ...]:
    if gamma < 0 or gamma > num_regions * num_products:
        raise ValueError("gamma exceeds the global cardinality uncertainty set")
    components = tuple(
        (region, product)
        for region in range(num_regions)
        for product in range(num_products)
    )
    return tuple(
        pattern
        for active_count in range(gamma + 1)
        for pattern in itertools.combinations(components, active_count)
    )


def build_scenario_rhs_plans(instance: Any, gamma: int) -> tuple[ScenarioRhsPlan, ...]:
    pairs = tuple(
        (region, product)
        for region in range(instance.num_regions)
        for product in range(instance.num_products)
    )
    base_totals = tuple(
        sum(float(instance.base_demand[region][product]) for region in range(instance.num_regions))
        for product in range(instance.num_products)
    )
    plans = []
    for pattern in enumerate_global_patterns(instance.num_regions, instance.num_products, gamma):
        active = frozenset(pattern)
        demand_rhs = tuple(
            float(instance.base_demand[region][product])
            + (
                float(instance.demand_deviation[region][product])
                if (region, product) in active
                else 0.0
            )
            for region, product in pairs
        )
        service_rhs = tuple(
            (1.0 - float(instance.service_level[product]))
            * (
                base_totals[product]
                + sum(
                    float(instance.demand_deviation[region][product])
                    for region, shocked_product in pattern
                    if shocked_product == product
                )
            )
            for product in range(instance.num_products)
        )
        plans.append(ScenarioRhsPlan(pattern, demand_rhs, service_rhs))
    return tuple(plans)


class EnhancedGlobalEnumeratedLPOracle:
    """Exact global enumeration with cached RHS plans and batched RHS updates."""

    max_scenarios = 5000

    def __init__(
        self,
        instance: Any,
        gamma: int,
        *,
        trace_path: Path | None = None,
    ) -> None:
        import gurobipy as gp
        from gurobipy import GRB

        self.instance = instance
        self.gamma = gamma
        self.trace_path = trace_path
        self.I = instance.num_depots
        self.R = instance.num_regions
        self.J = instance.num_products
        self.pairs = tuple((r, j) for r in range(self.R) for j in range(self.J))
        self.plans = build_scenario_rhs_plans(instance, gamma)
        self.total_scenarios = len(self.plans)
        expected = sum(math.comb(self.R * self.J, size) for size in range(gamma + 1))
        if self.total_scenarios != expected:
            raise RuntimeError("global scenario plan is incomplete")
        if self.total_scenarios > self.max_scenarios:
            raise RuntimeError(
                f"{self.total_scenarios} global scenarios exceed safety cap {self.max_scenarios}"
            )

        model = gp.Model("enhanced_basic_global_scenario_lp")
        model.Params.OutputFlag = 0
        apply_formal_solver_profile(model, mixed_integer=False)
        q = model.addVars(range(self.I), range(self.R), range(self.J), lb=0.0, name="q")
        u = model.addVars(range(self.R), range(self.J), lb=0.0, name="u")
        e = model.addVars(range(self.J), lb=0.0, name="e")
        demand = {
            (r, j): model.addConstr(
                gp.quicksum(q[i, r, j] for i in range(self.I)) + u[r, j] >= 0.0
            )
            for r, j in self.pairs
        }
        supply = {
            (i, j): model.addConstr(
                gp.quicksum(q[i, r, j] for r in range(self.R)) <= 0.0
            )
            for i in range(self.I)
            for j in range(self.J)
        }
        service = {
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
            instance.shortage_penalty[r][j] * u[r, j] for r, j in self.pairs
        )
        objective += gp.quicksum(
            instance.service_penalty[j] * e[j] for j in range(self.J)
        )
        model.setObjective(objective, GRB.MINIMIZE)
        model.update()
        self.model = model
        self.demand_constraints = tuple(demand[pair] for pair in self.pairs)
        self.supply_constraints = tuple(
            supply[i, j] for i in range(self.I) for j in range(self.J)
        )
        self.service_constraints = tuple(service[j] for j in range(self.J))
        self.solve_count = 0
        self.scenarios_solved = 0
        self.last_solve_metrics: dict[str, Any] = {}

    def solve(
        self,
        x: list[list[float]],
        *,
        time_limit: float | None = None,
        certify: bool = True,
    ) -> GlobalAdversarialResult:
        from gurobipy import GRB

        if len(x) != self.I or any(len(row) != self.J for row in x):
            raise ValueError("first-stage inventory dimensions do not match the instance")
        supply_rhs = tuple(
            max(0.0, float(x[i][j])) for i in range(self.I) for j in range(self.J)
        )
        self.model.setAttr(GRB.Attr.RHS, self.supply_constraints, supply_rhs)
        started = perf_counter()
        best = -float("inf")
        best_payload: tuple[Any, ...] | None = None
        solved = 0
        for plan in self.plans:
            if time_limit is not None:
                remaining = time_limit - (perf_counter() - started)
                if remaining <= 0:
                    raise PureBendersTimeout(
                        f"EB-BD oracle expired after {solved}/{self.total_scenarios} scenarios"
                    )
                self.model.Params.TimeLimit = max(0.001, remaining)
            self.model.setAttr(GRB.Attr.RHS, self.demand_constraints, plan.demand_rhs)
            self.model.setAttr(GRB.Attr.RHS, self.service_constraints, plan.service_rhs)
            self.model.optimize()
            if self.model.Status == GRB.TIME_LIMIT:
                raise PureBendersTimeout(
                    f"EB-BD oracle LP time limit at scenario {solved + 1}"
                )
            if self.model.Status != GRB.OPTIMAL:
                raise RuntimeError(
                    f"EB-BD oracle LP status={self.model.Status}, scenario={plan.pattern}"
                )
            solved += 1
            value = float(self.model.ObjVal)
            if value > best + 1e-9 or best_payload is None:
                beta_flat = tuple(
                    float(value) for value in self.model.getAttr(GRB.Attr.Pi, self.supply_constraints)
                )
                demand_dual = tuple(
                    float(value) for value in self.model.getAttr(GRB.Attr.Pi, self.demand_constraints)
                )
                service_dual = tuple(
                    float(value) for value in self.model.getAttr(GRB.Attr.Pi, self.service_constraints)
                )
                beta = tuple(
                    tuple(beta_flat[i * self.J + j] for j in range(self.J))
                    for i in range(self.I)
                )
                rhs_dual = sum(
                    rhs * dual for rhs, dual in zip(plan.demand_rhs, demand_dual, strict=True)
                )
                rhs_dual += sum(
                    rhs * dual for rhs, dual in zip(plan.service_rhs, service_dual, strict=True)
                )
                rhs_dual += sum(
                    rhs * dual for rhs, dual in zip(supply_rhs, beta_flat, strict=True)
                )
                alpha = rhs_dual - sum(
                    float(x[i][j]) * beta[i][j]
                    for i in range(self.I)
                    for j in range(self.J)
                )
                violations = [
                    *(-demand_dual[index] for index in range(len(self.pairs))),
                    *beta_flat,
                    *service_dual,
                    *(
                        demand_dual[r * self.J + j]
                        + beta[i][j]
                        - self.instance.transport_cost[i][r][j]
                        for i in range(self.I)
                        for r in range(self.R)
                        for j in range(self.J)
                    ),
                    *(
                        demand_dual[r * self.J + j]
                        + service_dual[j]
                        - self.instance.shortage_penalty[r][j]
                        for r in range(self.R)
                        for j in range(self.J)
                    ),
                    *(
                        -service_dual[j] - self.instance.service_penalty[j]
                        for j in range(self.J)
                    ),
                ]
                best = value
                best_payload = (
                    plan.pattern,
                    alpha,
                    beta,
                    max(0.0, max(violations)),
                    abs(value - rhs_dual),
                )
        if best_payload is None:
            raise RuntimeError("EB-BD oracle evaluated no scenarios")
        pattern, alpha, beta, dual_violation, residual = best_payload
        elapsed = perf_counter() - started
        self.solve_count += 1
        self.scenarios_solved += solved
        self.last_solve_metrics = {
            "scenarios_solved": solved,
            "scenario_count": self.total_scenarios,
            "oracle_seconds": elapsed,
            "batched_rhs_calls": 1 + 2 * solved,
            "lp_model_reused": True,
            "scenario_rhs_plans_precomputed": True,
            "candidate_pruning": False,
        }
        if self.trace_path is not None:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    **self.last_solve_metrics,
                    "value": best,
                    "shock_pattern": pattern,
                    "dual_feasibility_max_violation": dual_violation,
                    "strong_duality_residual": residual,
                }, sort_keys=True) + "\n")
        cut = PureAggregateCut(
            alpha,
            beta,
            best,
            tuple(tuple(row) for row in x),
            pattern,
            dual_violation <= 1e-7,
            residual,
        )
        return GlobalAdversarialResult(
            best,
            cut,
            best,
            elapsed,
            0.0,
            0,
            self.I * self.R * self.J + self.R * self.J + self.J,
            len(self.demand_constraints) + len(self.supply_constraints) + len(self.service_constraints),
        )

    def close(self) -> None:
        self.model.dispose()


def solve_enhanced_basic_benders(
    instance: Any,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    trace_path: Path | None = None,
    **kwargs: Any,
) -> tuple[Any, dict[str, Any]]:
    """Use the unchanged single-theta master with the exact EB-BD oracle."""
    from . import pure_benders as pure

    original = pure.GlobalRobustAdversarialSubproblem
    created: list[EnhancedGlobalEnumeratedLPOracle] = []

    def factory(oracle_instance: Any, oracle_gamma: int) -> EnhancedGlobalEnumeratedLPOracle:
        oracle = EnhancedGlobalEnumeratedLPOracle(
            oracle_instance, oracle_gamma, trace_path=trace_path
        )
        created.append(oracle)
        return oracle

    pure.GlobalRobustAdversarialSubproblem = factory
    try:
        result = pure.solve_pure_benders(
            instance, x0, budget, gamma, lambda_r, **kwargs
        )
        diagnostics = {
            "oracle_instances": len(created),
            "oracle_solve_calls": sum(oracle.solve_count for oracle in created),
            "scenario_lp_solves": sum(oracle.scenarios_solved for oracle in created),
            "scenario_count_per_oracle_call": created[0].total_scenarios if created else 0,
            "single_global_theta": True,
            "maximum_cuts_per_iteration": 1,
            "candidate_pruning": False,
            "product_risk_budget_decomposition": False,
            "product_multicut": False,
            "compact_global_robust_milp_oracle": False,
        }
        return result, diagnostics
    finally:
        pure.GlobalRobustAdversarialSubproblem = original
        for oracle in created:
            oracle.close()
