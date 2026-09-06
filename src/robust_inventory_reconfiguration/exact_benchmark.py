from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .instance import InventoryInstance
from .reconfiguration_model import (
    ReconfigurationSolution,
    build_exact_reconfiguration_model,
)
from .scenarios import enumerate_scenario_components, scenario_count
from .solver_profile import apply_formal_solver_profile


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


def solve_global_scenario_benchmark(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    max_recourse_variables: int = 1_000_000,
) -> ExactBenchmarkResult:
    """Literal global-scenario extensive form for small validation instances."""
    import gurobipy as gp
    from gurobipy import GRB

    scenarios = enumerate_scenario_components(instance, gamma)
    recourse_per_scenario = (
        instance.num_depots * instance.num_regions * instance.num_products
        + instance.num_regions * instance.num_products
        + instance.num_products
    )
    if len(scenarios) * recourse_per_scenario > max_recourse_variables:
        raise MemoryError("projected literal extensive form exceeds the declared size cap")
    depots = range(instance.num_depots)
    regions = range(instance.num_regions)
    products = range(instance.num_products)
    model = gp.Model(f"global_exact_{instance.name}")
    model.Params.OutputFlag = 0
    apply_formal_solver_profile(model, mixed_integer=True)
    y = model.addVars(depots, vtype=GRB.BINARY, name="y")
    x = model.addVars(depots, products, lb=0, name="x")
    a_plus = model.addVars(depots, products, lb=0, name="a_plus")
    a_minus = model.addVars(depots, products, lb=0, name="a_minus")
    for i in depots:
        model.addConstr(
            gp.quicksum(instance.product_volume[j] * x[i, j] for j in products)
            <= instance.capacity[i] * y[i]
        )
        for j in products:
            model.addConstr(x[i, j] <= instance.inventory_upper_bound[i][j] * y[i])
            model.addConstr(x[i, j] - x0[i][j] == a_plus[i, j] - a_minus[i, j])
    reconfiguration_cost = lambda_r * gp.quicksum(
        instance.inventory_cost[i][j] * (a_plus[i, j] + a_minus[i, j])
        for i in depots for j in products
    )
    first_stage = gp.quicksum(instance.fixed_depot_cost[i] * y[i] for i in depots)
    first_stage += gp.quicksum(
        instance.inventory_cost[i][j] * x[i, j] for i in depots for j in products
    )
    first_stage += reconfiguration_cost
    model.addConstr(first_stage <= budget)
    theta = model.addVar(lb=0, name="theta")
    for scenario_index, scenario in enumerate(scenarios):
        q = model.addVars(depots, regions, products, lb=0, name=f"q_{scenario_index}")
        u = model.addVars(regions, products, lb=0, name=f"u_{scenario_index}")
        e = model.addVars(products, lb=0, name=f"e_{scenario_index}")
        active = set(scenario)
        demand = [
            [
                instance.base_demand[r][j]
                + (instance.demand_deviation[r][j] if (r, j) in active else 0.0)
                for j in products
            ]
            for r in regions
        ]
        for r in regions:
            for j in products:
                model.addConstr(gp.quicksum(q[i, r, j] for i in depots) + u[r, j] >= demand[r][j])
        for i in depots:
            for j in products:
                model.addConstr(gp.quicksum(q[i, r, j] for r in regions) <= x[i, j])
        for j in products:
            model.addConstr(
                gp.quicksum(u[r, j] for r in regions) - e[j]
                <= (1.0 - instance.service_level[j]) * sum(demand[r][j] for r in regions)
            )
        cost = gp.quicksum(
            instance.transport_cost[i][r][j] * q[i, r, j]
            for i in depots for r in regions for j in products
        )
        cost += gp.quicksum(
            instance.shortage_penalty[r][j] * u[r, j]
            for r in regions for j in products
        )
        cost += gp.quicksum(instance.service_penalty[j] * e[j] for j in products)
        model.addConstr(theta >= cost)
    model.setObjective(first_stage + theta)
    model.optimize()
    status = "OPTIMAL" if model.Status == GRB.OPTIMAL else "ERROR"
    variables = {
        "y": y, "x": x, "a_plus": a_plus, "a_minus": a_minus,
        "first_stage": first_stage, "reconfiguration_cost": reconfiguration_cost,
        "theta": theta,
    }
    solution = _extract_solution(instance, x0, lambda_r, True, model, variables) if status == "OPTIMAL" else None
    return ExactBenchmarkResult(
        status,
        solution,
        float(model.ObjBound) if model.SolCount else None,
        float(model.MIPGap) if model.SolCount else None,
        float(model.Runtime),
        float(model.NodeCount),
        len(scenarios),
        int(model.NumVars),
        int(model.NumConstrs),
        int(model.NumNZs),
        None,
        "literal_global_scenario_extensive_form",
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
