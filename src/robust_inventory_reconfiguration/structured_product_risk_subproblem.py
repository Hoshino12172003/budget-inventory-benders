from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from time import perf_counter

import numpy as np
from scipy.sparse import coo_matrix

from .accelerated_product_risk_subproblem import (
    AcceleratedProductSeparationResult,
    AcceleratedProductWorstCase,
)
from .instance import InventoryInstance
from .product_risk_subproblem import ProductCut
from .solver_profile import apply_formal_solver_profile


@dataclass(frozen=True)
class _ScenarioBlock:
    local_gamma: int
    pattern: tuple[int, ...]
    demand: tuple[float, ...]
    allowance: float
    variable_start: int
    constraint_start: int


class StructuredProductRiskSubproblem:
    """Exact batched sparse-matrix implementation of the product recourse LPs."""

    def __init__(
        self,
        instance: InventoryInstance,
        product_index: int,
        gamma: int,
        *,
        method: int = 1,
        presolve: int = 0,
    ):
        import gurobipy as gp

        self.instance = instance
        self.product_index = product_index
        self.gamma = gamma
        self.method = method
        self.presolve = presolve
        self.environment = gp.Env(empty=True)
        self.environment.setParam("OutputFlag", 0)
        self.environment.start()
        self.model = gp.Model(
            f"structured_product_{product_index}_risk_subproblem",
            env=self.environment,
        )
        self.model.Params.OutputFlag = 0
        self.model.Params.Threads = 1
        self.model.Params.LPWarmStart = 2
        self.model.Params.Method = method
        self.model.Params.Presolve = presolve
        apply_formal_solver_profile(self.model, mixed_integer=False)
        self._build_sparse_model(gp)
        self._has_basis = False

    def _build_sparse_model(self, gp) -> None:
        instance = self.instance
        j = self.product_index
        depots = instance.num_depots
        regions = instance.num_regions
        variables_per_block = depots * regions + regions + 1
        constraints_per_block = regions + depots + 1
        patterns = [
            (local_gamma, pattern)
            for local_gamma in range(self.gamma + 1)
            for pattern in combinations(range(regions), local_gamma)
        ]
        block_count = len(patterns)
        variable_count = block_count * variables_per_block
        constraint_count = block_count * constraints_per_block

        rows: list[int] = []
        columns: list[int] = []
        coefficients: list[float] = []
        rhs = np.empty(constraint_count, dtype=float)
        senses = np.empty(constraint_count, dtype="U1")
        objective_block = np.empty(variables_per_block, dtype=float)
        for i in range(depots):
            for r in range(regions):
                objective_block[i * regions + r] = instance.transport_cost[i][r][j]
        shortage_start = depots * regions
        for r in range(regions):
            objective_block[shortage_start + r] = instance.shortage_penalty[r][j]
        objective_block[-1] = instance.service_penalty[j]
        objective = np.tile(objective_block, block_count)

        blocks: list[_ScenarioBlock] = []
        supply_rows: list[int] = []
        for block_index, (local_gamma, pattern) in enumerate(patterns):
            variable_start = block_index * variables_per_block
            constraint_start = block_index * constraints_per_block
            shocked = set(pattern)
            demand = tuple(
                instance.base_demand[r][j]
                + (instance.demand_deviation[r][j] if r in shocked else 0.0)
                for r in range(regions)
            )
            allowance = (1.0 - instance.service_level[j]) * sum(demand)
            blocks.append(
                _ScenarioBlock(
                    local_gamma,
                    pattern,
                    demand,
                    allowance,
                    variable_start,
                    constraint_start,
                )
            )

            for r in range(regions):
                row = constraint_start + r
                for i in range(depots):
                    rows.append(row)
                    columns.append(variable_start + i * regions + r)
                    coefficients.append(1.0)
                rows.append(row)
                columns.append(variable_start + shortage_start + r)
                coefficients.append(1.0)
                rhs[row] = demand[r]
                senses[row] = ">"

            for i in range(depots):
                row = constraint_start + regions + i
                supply_rows.append(row)
                for r in range(regions):
                    rows.append(row)
                    columns.append(variable_start + i * regions + r)
                    coefficients.append(1.0)
                rhs[row] = 0.0
                senses[row] = "<"

            service_row = constraint_start + regions + depots
            for r in range(regions):
                rows.append(service_row)
                columns.append(variable_start + shortage_start + r)
                coefficients.append(1.0)
            rows.append(service_row)
            columns.append(variable_start + variables_per_block - 1)
            coefficients.append(-1.0)
            rhs[service_row] = allowance
            senses[service_row] = "<"

        matrix = coo_matrix(
            (coefficients, (rows, columns)),
            shape=(constraint_count, variable_count),
        ).tocsr()
        self.variables = self.model.addMVar(variable_count, lb=0.0, name="recourse")
        self.constraints = self.model.addMConstr(
            matrix, self.variables, senses, rhs, name="recourse_constraints"
        )
        self.model.setObjective(objective @ self.variables)
        self.model.update()
        self.blocks = tuple(blocks)
        self._rhs = rhs
        self._supply_rows = np.asarray(supply_rows, dtype=int)
        self._objective_block = objective_block
        self._variables_per_block = variables_per_block
        self._constraints_per_block = constraints_per_block
        self._block_indices_by_gamma = tuple(
            tuple(
                index
                for index, block in enumerate(self.blocks)
                if block.local_gamma == local_gamma
            )
            for local_gamma in range(self.gamma + 1)
        )

    def solve(self, x: list[float]) -> AcceleratedProductSeparationResult:
        from gurobipy import GRB

        if len(x) != self.instance.num_depots:
            raise ValueError("product inventory vector has incompatible length")
        if min(x) < -1e-7:
            raise ValueError("product inventory contains a materially negative value")
        clean_x = np.maximum(np.asarray(x, dtype=float), 0.0)
        update_started = perf_counter()
        rhs = self._rhs.copy()
        rhs[self._supply_rows] = np.tile(clean_x, len(self.blocks))
        self.constraints.RHS = rhs
        update_runtime = perf_counter() - update_started

        solve_started = perf_counter()
        warm_start_used = self._has_basis
        self.model.optimize()
        solve_runtime = perf_counter() - solve_started
        if self.model.Status != GRB.OPTIMAL:
            raise RuntimeError(
                f"Product recourse is unexpectedly infeasible: {self.model.Status}"
            )
        self._has_basis = True

        extraction_started = perf_counter()
        primal = np.asarray(self.variables.X, dtype=float).reshape(
            len(self.blocks), self._variables_per_block
        )
        block_values = primal @ self._objective_block
        duals = np.asarray(self.constraints.Pi, dtype=float).reshape(
            len(self.blocks), self._constraints_per_block
        )
        worst_cases = []
        for local_gamma, block_indices in enumerate(self._block_indices_by_gamma):
            block_index = max(block_indices, key=lambda index: block_values[index])
            worst_cases.append(
                self._extract(
                    block_index,
                    float(block_values[block_index]),
                    duals[block_index],
                    clean_x,
                )
            )
        extraction_runtime = perf_counter() - extraction_started
        return AcceleratedProductSeparationResult(
            tuple(worst_cases),
            solve_runtime,
            len(self.blocks),
            float(self.model.IterCount),
            int(warm_start_used),
            0.0 if warm_start_used else solve_runtime,
            solve_runtime if warm_start_used else 0.0,
            update_runtime,
            extraction_runtime,
        )

    def _extract(
        self,
        block_index: int,
        value: float,
        duals: np.ndarray,
        x: np.ndarray,
    ) -> AcceleratedProductWorstCase:
        instance = self.instance
        block = self.blocks[block_index]
        regions = instance.num_regions
        depots = instance.num_depots
        demand_dual = tuple(float(v) for v in duals[:regions])
        supply_dual = tuple(float(v) for v in duals[regions : regions + depots])
        service_dual = float(duals[-1])
        alpha = sum(v * dual for v, dual in zip(block.demand, demand_dual))
        alpha += block.allowance * service_dual
        dual_value = alpha + sum(
            coefficient * amount for coefficient, amount in zip(supply_dual, x)
        )
        j = self.product_index
        dual_feasible = (
            all(v >= -1e-8 for v in demand_dual)
            and all(v <= 1e-8 for v in supply_dual)
            and service_dual <= 1e-8
            and all(
                demand_dual[r] + supply_dual[i]
                <= instance.transport_cost[i][r][j] + 1e-7
                for i in range(depots)
                for r in range(regions)
            )
            and all(
                demand_dual[r] + service_dual
                <= instance.shortage_penalty[r][j] + 1e-7
                for r in range(regions)
            )
            and -service_dual <= instance.service_penalty[j] + 1e-7
        )
        cut = ProductCut(
            j,
            block.local_gamma,
            alpha,
            supply_dual,
            value,
            tuple(float(v) for v in x),
            block.pattern,
            dual_feasible,
            abs(value - dual_value),
        )
        return AcceleratedProductWorstCase(
            j,
            block.local_gamma,
            value,
            block.pattern,
            demand_dual,
            supply_dual,
            service_dual,
            cut,
        )

    def close(self) -> None:
        self.model.dispose()
        self.environment.dispose()
