from __future__ import annotations

from time import perf_counter
from typing import Any

from .enhanced_basic_benders import EnhancedGlobalEnumeratedLPOracle
from .scenario_generation_single_cut import Pattern, ScenarioEvaluation


class ExactScenarioLPEvaluator:
    """Exact single-scenario LP evaluator used only by the SG diagnostic."""

    def __init__(
        self,
        instance: Any,
        gamma: int,
        x: list[list[float]],
        *,
        threads: int | None,
    ) -> None:
        from gurobipy import GRB

        self.oracle = EnhancedGlobalEnumeratedLPOracle(instance, gamma)
        if threads is not None:
            self.oracle.model.Params.Threads = threads
        self.instance = instance
        self.I = instance.num_depots
        self.R = instance.num_regions
        self.J = instance.num_products
        self.x = tuple(tuple(max(0.0, float(value)) for value in row) for row in x)
        self.supply_rhs = tuple(
            self.x[i][j] for i in range(self.I) for j in range(self.J)
        )
        self.oracle.model.setAttr(
            GRB.Attr.RHS, self.oracle.supply_constraints, self.supply_rhs
        )
        self.plans = {tuple(plan.pattern): plan for plan in self.oracle.plans}
        self.lp_seconds = 0.0
        self.deadline: float | None = None

    def set_first_stage(self, x: list[list[float]]) -> None:
        from gurobipy import GRB

        if len(x) != self.I or any(len(row) != self.J for row in x):
            raise ValueError("first-stage inventory dimensions do not match the instance")
        self.x = tuple(tuple(max(0.0, float(value)) for value in row) for row in x)
        self.supply_rhs = tuple(
            self.x[i][j] for i in range(self.I) for j in range(self.J)
        )
        self.oracle.model.setAttr(
            GRB.Attr.RHS, self.oracle.supply_constraints, self.supply_rhs
        )

    def begin_call(self, time_limit: float | None) -> None:
        self.lp_seconds = 0.0
        self.deadline = None if time_limit is None else perf_counter() + time_limit

    def evaluate(self, pattern: Pattern) -> ScenarioEvaluation:
        from gurobipy import GRB

        plan = self.plans.get(tuple(pattern))
        if plan is None:
            raise ValueError(f"pattern is outside the frozen uncertainty set: {pattern}")
        model = self.oracle.model
        model.setAttr(GRB.Attr.RHS, self.oracle.demand_constraints, plan.demand_rhs)
        model.setAttr(GRB.Attr.RHS, self.oracle.service_constraints, plan.service_rhs)
        if self.deadline is not None:
            from .pure_benders import PureBendersTimeout

            remaining = self.deadline - perf_counter()
            if remaining <= 0.0:
                raise PureBendersTimeout("SG-BD exact separation reached its time limit")
            model.Params.TimeLimit = max(0.001, remaining)
        started = perf_counter()
        model.optimize()
        self.lp_seconds += perf_counter() - started
        if model.Status == GRB.TIME_LIMIT:
            from .pure_benders import PureBendersTimeout

            raise PureBendersTimeout("SG-BD scenario LP reached its time limit")
        if model.Status != GRB.OPTIMAL:
            raise RuntimeError(f"SG scenario LP status={model.Status}, pattern={pattern}")
        value = float(model.ObjVal)
        beta_flat = tuple(
            float(item)
            for item in model.getAttr(GRB.Attr.Pi, self.oracle.supply_constraints)
        )
        demand_dual = tuple(
            float(item)
            for item in model.getAttr(GRB.Attr.Pi, self.oracle.demand_constraints)
        )
        service_dual = tuple(
            float(item)
            for item in model.getAttr(GRB.Attr.Pi, self.oracle.service_constraints)
        )
        beta = tuple(
            tuple(beta_flat[i * self.J + j] for j in range(self.J))
            for i in range(self.I)
        )
        rhs_dual = sum(
            rhs * dual
            for rhs, dual in zip(plan.demand_rhs, demand_dual, strict=True)
        )
        rhs_dual += sum(
            rhs * dual
            for rhs, dual in zip(plan.service_rhs, service_dual, strict=True)
        )
        rhs_dual += sum(
            rhs * dual for rhs, dual in zip(self.supply_rhs, beta_flat, strict=True)
        )
        alpha = rhs_dual - sum(
            self.x[i][j] * beta[i][j]
            for i in range(self.I)
            for j in range(self.J)
        )
        violations = [
            *(-demand_dual[index] for index in range(self.R * self.J)),
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
        anchor_value = alpha + sum(
            self.x[i][j] * beta[i][j]
            for i in range(self.I)
            for j in range(self.J)
        )
        return ScenarioEvaluation(value, {
            "alpha": alpha,
            "beta": beta,
            "dual_feasibility_max_violation": max(0.0, max(violations)),
            "strong_duality_residual": abs(value - rhs_dual),
            "cut_anchor_value": anchor_value,
            "cut_anchor_residual": abs(value - anchor_value),
        })

    def close(self) -> None:
        self.oracle.close()
