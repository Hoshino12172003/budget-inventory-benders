from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .instance import InventoryInstance
from .reconfiguration_model import (
    ReconfigurationSolution,
    build_exact_reconfiguration_model,
)
from .scenarios import scenario_count


@dataclass(frozen=True)
class ExactBenchmarkResult:
    status: str
    solution: ReconfigurationSolution | None
    best_bound: float | None
    mip_gap: float | None
    runtime: float
    node_count: float
    scenario_count: int
    variable_count: int
    constraint_count: int
    nonzero_count: int
    peak_memory_gb: float | None
    method: str


def solve_exact_benchmark(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    include_reconfiguration: bool = True,
    time_limit: float | None = None,
) -> ExactBenchmarkResult:
    """Solve the exact finite robust counterpart used only as ground truth."""
    from gurobipy import GRB

    model, variables = build_exact_reconfiguration_model(
        instance,
        x0,
        budget,
        gamma,
        lambda_r,
        include_reconfiguration=include_reconfiguration,
    )
    if time_limit is not None:
        model.Params.TimeLimit = time_limit
    model.optimize()
    status = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.MEM_LIMIT: "MEMORY_LIMIT",
    }.get(model.Status, "ERROR")
    solution = None
    if status == "OPTIMAL":
        solution = _extract_solution(
            instance,
            x0,
            lambda_r,
            include_reconfiguration,
            model,
            variables,
        )
    return ExactBenchmarkResult(
        status=status,
        solution=solution,
        best_bound=float(model.ObjBound) if model.SolCount else None,
        mip_gap=float(model.MIPGap) if model.SolCount else None,
        runtime=float(model.Runtime),
        node_count=float(model.NodeCount),
        scenario_count=scenario_count(instance, gamma),
        variable_count=int(model.NumVars),
        constraint_count=int(model.NumConstrs),
        nonzero_count=int(model.NumNZs),
        peak_memory_gb=None,
        method="factorized_exact_extensive_form",
    )


def _extract_solution(
    instance: InventoryInstance,
    x0: list[list[float]],
    lambda_r: float,
    include_reconfiguration: bool,
    model: Any,
    variables: dict[str, Any],
) -> ReconfigurationSolution:
    y = variables["y"]
    x = variables["x"]
    solved_x = [
        [x[i, j].X for j in range(instance.num_products)]
        for i in range(instance.num_depots)
    ]
    if include_reconfiguration and lambda_r > 0:
        plus_values = [
            [variables["a_plus"][i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
        minus_values = [
            [variables["a_minus"][i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
    else:
        plus_values = [
            [max(solved_x[i][j] - x0[i][j], 0.0) for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
        minus_values = [
            [max(x0[i][j] - solved_x[i][j], 0.0) for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
    return ReconfigurationSolution(
        objective=float(model.ObjVal),
        first_stage_expenditure=float(variables["first_stage"].getValue()),
        robust_recourse_cost=float(variables["theta"].X),
        y=[int(round(y[i].X)) for i in range(instance.num_depots)],
        x=solved_x,
        a_plus=plus_values,
        a_minus=minus_values,
        reconfiguration_cost=float(variables["reconfiguration_cost"].getValue()),
    )
