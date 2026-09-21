from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from time import perf_counter

from .instance import InventoryInstance
from .product_risk_subproblem import ProductCut
from .solver_profile import apply_formal_solver_profile


@dataclass(frozen=True)
class AcceleratedProductWorstCase:
    product_index: int
    local_gamma: int
    value: float
    pattern: tuple[int, ...]
    demand_dual: tuple[float, ...]
    supply_dual: tuple[float, ...]
    service_dual: float
    cut: ProductCut


@dataclass(frozen=True)
class AcceleratedProductSeparationResult:
    worst_cases: tuple[AcceleratedProductWorstCase, ...]
    runtime: float
    pattern_evaluations: int
    simplex_iterations: float
    warm_starts: int
    cold_solve_runtime: float
    warm_solve_runtime: float
    model_update_runtime: float
    result_extraction_runtime: float


class AcceleratedProductRiskSubproblem:
    """Original exact product oracle in an independent single-thread environment."""

    def __init__(self, instance: InventoryInstance, product_index: int, gamma: int):
        import gurobipy as gp

        self.instance = instance
        self.product_index = product_index
        self.gamma = gamma
        self.environment = gp.Env(empty=True)
        self.environment.setParam("OutputFlag", 0)
        self.environment.start()
        self.model = gp.Model(
            f"accelerated_product_{product_index}_risk_subproblem",
            env=self.environment,
        )
        self.model.Params.OutputFlag = 0
        self.model.Params.Threads = 1
        self.model.Params.LPWarmStart = 2
        apply_formal_solver_profile(self.model, mixed_integer=False)
        self.blocks = {}
        objectives = []
        for local_gamma in range(gamma + 1):
            for pattern in combinations(range(instance.num_regions), local_gamma):
                block = self._add_pattern(local_gamma, pattern)
                self.blocks[(local_gamma, pattern)] = block
                objectives.append(block["cost"])
        self.model.setObjective(gp.quicksum(objectives))
        self._has_basis = False

    def _add_pattern(self, local_gamma: int, pattern: tuple[int, ...]):
        import gurobipy as gp

        j = self.product_index
        depots = range(self.instance.num_depots)
        regions = range(self.instance.num_regions)
        suffix = f"{local_gamma}_{'_'.join(map(str, pattern))}"
        q = self.model.addVars(depots, regions, lb=0, name=f"q_{suffix}")
        u = self.model.addVars(regions, lb=0, name=f"u_{suffix}")
        e = self.model.addVar(lb=0, name=f"e_{suffix}")
        shocked = set(pattern)
        demand = [
            self.instance.base_demand[r][j]
            + (self.instance.demand_deviation[r][j] if r in shocked else 0.0)
            for r in regions
        ]
        demand_constraints = [
            self.model.addConstr(gp.quicksum(q[i, r] for i in depots) + u[r] >= demand[r])
            for r in regions
        ]
        supply_constraints = [
            self.model.addConstr(gp.quicksum(q[i, r] for r in regions) <= 0.0)
            for i in depots
        ]
        allowance = (1.0 - self.instance.service_level[j]) * sum(demand)
        service_constraint = self.model.addConstr(
            gp.quicksum(u[r] for r in regions) - e <= allowance
        )
        cost = gp.quicksum(
            self.instance.transport_cost[i][r][j] * q[i, r]
            for i in depots
            for r in regions
        )
        cost += gp.quicksum(
            self.instance.shortage_penalty[r][j] * u[r] for r in regions
        )
        cost += self.instance.service_penalty[j] * e
        cost_value = self.model.addVar(lb=0, name=f"cost_{suffix}")
        self.model.addConstr(cost_value == cost, name=f"cost_identity_{suffix}")
        return {
            "q": q,
            "u": u,
            "e": e,
            "demand": demand,
            "allowance": allowance,
            "demand_constraints": demand_constraints,
            "supply_constraints": supply_constraints,
            "service_constraint": service_constraint,
            "cost": cost_value,
        }

    def solve(self, x: list[float]) -> AcceleratedProductSeparationResult:
        from gurobipy import GRB

        if len(x) != self.instance.num_depots:
            raise ValueError("product inventory vector has incompatible length")
        if min(x) < -1e-7:
            raise ValueError("product inventory contains a materially negative value")
        x = [max(value, 0.0) for value in x]
        update_started = perf_counter()
        for block in self.blocks.values():
            for i, constraint in enumerate(block["supply_constraints"]):
                constraint.RHS = x[i]
        update_runtime = perf_counter() - update_started
        started = perf_counter()
        warm_start_used = self._has_basis
        self.model.optimize()
        elapsed = perf_counter() - started
        if self.model.Status != GRB.OPTIMAL:
            raise RuntimeError(
                f"Product recourse is unexpectedly infeasible: {self.model.Status}"
            )
        self._has_basis = True
        block_keys = list(self.blocks)
        block_values = self.model.getAttr(
            "X", [self.blocks[key]["cost"] for key in block_keys]
        )
        values_by_key = dict(zip(block_keys, block_values))
        extraction_started = perf_counter()
        worst_cases = []
        for local_gamma in range(self.gamma + 1):
            patterns = [
                pattern
                for candidate_gamma, pattern in self.blocks
                if candidate_gamma == local_gamma
            ]
            pattern = max(
                patterns,
                key=lambda candidate: values_by_key[(local_gamma, candidate)],
            )
            worst_cases.append(
                self._extract(
                    local_gamma,
                    pattern,
                    x,
                    values_by_key[(local_gamma, pattern)],
                )
            )
        extraction_runtime = perf_counter() - extraction_started
        return AcceleratedProductSeparationResult(
            tuple(worst_cases),
            elapsed,
            len(self.blocks),
            float(self.model.IterCount),
            int(warm_start_used),
            0.0 if warm_start_used else elapsed,
            elapsed if warm_start_used else 0.0,
            update_runtime,
            extraction_runtime,
        )

    def _extract(
        self,
        local_gamma: int,
        pattern: tuple[int, ...],
        x: list[float],
        value: float,
    ) -> AcceleratedProductWorstCase:
        block = self.blocks[(local_gamma, pattern)]
        demand_dual = tuple(
            self.model.getAttr("Pi", block["demand_constraints"])
        )
        supply_dual = tuple(
            self.model.getAttr("Pi", block["supply_constraints"])
        )
        service_dual = block["service_constraint"].Pi
        alpha = sum(value * dual for value, dual in zip(block["demand"], demand_dual))
        alpha += block["allowance"] * service_dual
        dual_value = alpha + sum(
            coefficient * amount for coefficient, amount in zip(supply_dual, x)
        )
        j = self.product_index
        dual_feasible = (
            all(value >= -1e-8 for value in demand_dual)
            and all(value <= 1e-8 for value in supply_dual)
            and service_dual <= 1e-8
            and all(
                demand_dual[r] + supply_dual[i]
                <= self.instance.transport_cost[i][r][j] + 1e-7
                for i in range(self.instance.num_depots)
                for r in range(self.instance.num_regions)
            )
            and all(
                demand_dual[r] + service_dual
                <= self.instance.shortage_penalty[r][j] + 1e-7
                for r in range(self.instance.num_regions)
            )
            and -service_dual <= self.instance.service_penalty[j] + 1e-7
        )
        cut = ProductCut(
            j,
            local_gamma,
            alpha,
            supply_dual,
            value,
            tuple(x),
            pattern,
            dual_feasible,
            abs(value - dual_value),
        )
        return AcceleratedProductWorstCase(
            j,
            local_gamma,
            value,
            pattern,
            demand_dual,
            supply_dual,
            service_dual,
            cut,
        )

    def close(self) -> None:
        self.model.dispose()
        self.environment.dispose()
