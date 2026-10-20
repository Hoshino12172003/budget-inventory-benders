from __future__ import annotations

from itertools import combinations
from pathlib import Path
from time import perf_counter
from typing import Any

from .instance import InventoryInstance
from .pure_benders import GlobalAdversarialResult, PureAggregateCut
from .reconfiguration_model import gamma_allocations
from .solver_profile import apply_formal_solver_profile


class ExtensiveFormRecourseOracle:
    """The complete recourse block of the exact Direct model as one reusable LP."""

    def __init__(
        self,
        instance: InventoryInstance,
        gamma: int,
        *,
        trace_path: Path | None = None,
    ) -> None:
        import gurobipy as gp
        from gurobipy import GRB

        if gamma < 0 or gamma > instance.num_regions * instance.num_products:
            raise ValueError("gamma exceeds the global cardinality uncertainty set")
        self.instance = instance
        self.gamma = gamma
        self.trace_path = trace_path
        self.solve_count = 0
        self.scenario_blocks = 0
        depots = range(instance.num_depots)
        regions = range(instance.num_regions)
        products = range(instance.num_products)

        model = gp.Model(f"ef_bd_recourse_{instance.name}")
        model.Params.OutputFlag = 0
        apply_formal_solver_profile(model, mixed_integer=False)
        eta = model.addVars(products, range(gamma + 1), lb=0.0, name="eta")
        supply: dict[tuple[int, int], list[Any]] = {
            (i, j): [] for i in depots for j in products
        }
        block_patterns: dict[tuple[int, int, int], tuple[int, ...]] = {}
        block_constraints: dict[tuple[int, int, int], Any] = {}

        for j in products:
            for local_gamma in range(gamma + 1):
                for scenario_number, shocked_regions in enumerate(
                    combinations(regions, local_gamma)
                ):
                    key = (j, local_gamma, scenario_number)
                    block_patterns[key] = tuple(shocked_regions)
                    self.scenario_blocks += 1
                    q = model.addVars(
                        depots,
                        regions,
                        lb=0.0,
                        name=f"q_{j}_{local_gamma}_{scenario_number}",
                    )
                    u = model.addVars(
                        regions,
                        lb=0.0,
                        name=f"u_{j}_{local_gamma}_{scenario_number}",
                    )
                    e = model.addVar(
                        lb=0.0, name=f"e_{j}_{local_gamma}_{scenario_number}"
                    )
                    shocked = set(shocked_regions)
                    demand = []
                    for r in regions:
                        value = instance.base_demand[r][j]
                        if r in shocked:
                            value += instance.demand_deviation[r][j]
                        demand.append(value)
                        model.addConstr(
                            gp.quicksum(q[i, r] for i in depots) + u[r] >= value,
                            name=f"demand[{j},{local_gamma},{scenario_number},{r}]",
                        )
                    for i in depots:
                        constraint = model.addConstr(
                            gp.quicksum(q[i, r] for r in regions) <= 0.0,
                            name=f"supply[{j},{local_gamma},{scenario_number},{i}]",
                        )
                        supply[i, j].append(constraint)
                    model.addConstr(
                        gp.quicksum(u[r] for r in regions) - e
                        <= (1.0 - instance.service_level[j]) * sum(demand),
                        name=f"service[{j},{local_gamma},{scenario_number}]",
                    )
                    cost = gp.quicksum(
                        instance.transport_cost[i][r][j] * q[i, r]
                        for i in depots
                        for r in regions
                    )
                    cost += gp.quicksum(
                        instance.shortage_penalty[r][j] * u[r] for r in regions
                    )
                    cost += instance.service_penalty[j] * e
                    block_constraints[key] = model.addConstr(
                        eta[j, local_gamma] >= cost,
                        name=f"product_worst_case[{j},{local_gamma},{scenario_number}]",
                    )

        theta = model.addVar(lb=0.0, name="theta")
        allocation_constraints: dict[tuple[int, ...], Any] = {}
        for allocation_number, allocation in enumerate(
            gamma_allocations(instance.num_products, gamma)
        ):
            allocation_constraints[allocation] = model.addConstr(
                theta >= gp.quicksum(eta[j, allocation[j]] for j in products),
                name=f"risk_budget[{allocation_number}]",
            )
        model.setObjective(theta, GRB.MINIMIZE)
        model.update()
        self.model = model
        self.theta = theta
        self.supply = supply
        self.block_patterns = block_patterns
        self.block_constraints = block_constraints
        self.allocation_constraints = allocation_constraints

    def solve(
        self,
        x: list[list[float]],
        *,
        time_limit: float | None = None,
        certify: bool = True,
    ) -> GlobalAdversarialResult:
        import gurobipy as gp
        from gurobipy import GRB

        if len(x) != self.instance.num_depots or any(
            len(row) != self.instance.num_products for row in x
        ):
            raise ValueError("x has incompatible dimensions")
        if any(value < -1e-7 for row in x for value in row):
            raise ValueError("x must be nonnegative")
        for i in range(self.instance.num_depots):
            for j in range(self.instance.num_products):
                value = max(0.0, float(x[i][j]))
                for constraint in self.supply[i, j]:
                    constraint.RHS = value
        if time_limit is not None:
            self.model.Params.TimeLimit = max(0.001, time_limit)
        started = perf_counter()
        self.model.optimize()
        elapsed = perf_counter() - started
        if self.model.Status == GRB.TIME_LIMIT:
            from .pure_benders import PureBendersTimeout

            raise PureBendersTimeout("EF-BD recourse LP reached the wall-clock limit")
        if self.model.Status != GRB.OPTIMAL:
            raise RuntimeError(f"EF-BD recourse LP failed with status {self.model.Status}")

        self.solve_count += 1
        value = float(self.model.ObjVal)
        beta = tuple(
            tuple(
                sum(float(constraint.Pi) for constraint in self.supply[i, j])
                for j in range(self.instance.num_products)
            )
            for i in range(self.instance.num_depots)
        )
        alpha = value - sum(
            beta[i][j] * x[i][j]
            for i in range(self.instance.num_depots)
            for j in range(self.instance.num_products)
        )
        dual_objective = sum(
            float(constraint.RHS) * float(constraint.Pi)
            for constraint in self.model.getConstrs()
        )
        strong_duality_error = abs(value - dual_objective)
        minimum_reduced_cost = min(
            (float(variable.RC) for variable in self.model.getVars()), default=0.0
        )
        dual_feasible = minimum_reduced_cost >= -1e-7

        active_allocation = max(
            self.allocation_constraints,
            key=lambda allocation: float(self.allocation_constraints[allocation].Pi),
        )
        pattern: list[tuple[int, int]] = []
        for j, local_gamma in enumerate(active_allocation):
            candidates = [
                key
                for key in self.block_constraints
                if key[0] == j and key[1] == local_gamma
            ]
            active_block = max(
                candidates, key=lambda key: float(self.block_constraints[key].Pi)
            )
            pattern.extend((r, j) for r in self.block_patterns[active_block])

        if self.trace_path is not None:
            import json

            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "oracle_call": self.solve_count,
                            "optimizer_calls": 1,
                            "scenario_blocks": self.scenario_blocks,
                            "value": value,
                            "strong_duality_error": strong_duality_error,
                            "minimum_reduced_cost": minimum_reduced_cost,
                            "active_risk_allocation": active_allocation,
                            "active_global_pattern": pattern,
                            "runtime_seconds": elapsed,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        cut = PureAggregateCut(
            alpha=alpha,
            beta=beta,
            generation_value=value,
            generation_x=tuple(tuple(float(v) for v in row) for row in x),
            shock_pattern=tuple(pattern),
            dual_feasible=dual_feasible,
            strong_duality_error=strong_duality_error,
        )
        return GlobalAdversarialResult(
            value=value,
            cut=cut,
            fixed_scenario_value=value,
            mip_runtime=elapsed,
            certification_runtime=0.0,
            binary_variables=0,
            continuous_variables=int(self.model.NumVars),
            constraints=int(self.model.NumConstrs),
        )

    def close(self) -> None:
        self.model.dispose()


def solve_extensive_form_benders(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    trace_path: Path | None = None,
    **kwargs: Any,
) -> tuple[Any, dict[str, Any]]:
    """Solve the unchanged single-theta master with the monolithic Direct recourse LP."""
    from . import pure_benders as pure

    original = pure.GlobalRobustAdversarialSubproblem
    created: list[ExtensiveFormRecourseOracle] = []

    def factory(
        oracle_instance: InventoryInstance, oracle_gamma: int
    ) -> ExtensiveFormRecourseOracle:
        oracle = ExtensiveFormRecourseOracle(
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
            "optimizer_calls_per_oracle": 1,
            "scenario_blocks": created[0].scenario_blocks if created else 0,
            "continuous_variables": int(created[0].model.NumVars) if created else 0,
            "constraints": int(created[0].model.NumConstrs) if created else 0,
            "single_global_theta": True,
            "maximum_cuts_per_iteration": 1,
            "scenario_pruning": False,
            "product_subproblem_decomposition": False,
            "product_multicut": False,
            "compact_global_robust_milp_oracle": False,
        }
        return result, diagnostics
    finally:
        pure.GlobalRobustAdversarialSubproblem = original
        for oracle in created:
            oracle.close()
