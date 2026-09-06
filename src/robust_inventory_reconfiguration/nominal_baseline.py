from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .instance import InventoryInstance


@dataclass(frozen=True)
class NominalBaseline:
    y: list[int]
    x: list[list[float]]
    first_stage_spending: float
    recourse_cost: float
    objective: float


def build_nominal_model(
    instance: InventoryInstance,
    budget: float | None = None,
) -> tuple[Any, dict[int, Any], dict[tuple[int, int], Any], Any, Any]:
    """Build the independent Gamma=0 incumbent planning model."""
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as exc:  # pragma: no cover - depends on licensed optional solver
        raise RuntimeError("Nominal baseline generation requires gurobipy") from exc

    depots = range(instance.num_depots)
    regions = range(instance.num_regions)
    products = range(instance.num_products)
    model = gp.Model(f"nominal_baseline_{instance.name}")
    model.Params.OutputFlag = 0
    model.Params.MIPGap = 0
    model.Params.FeasibilityTol = 1e-9
    model.Params.OptimalityTol = 1e-9
    model.Params.IntFeasTol = 1e-9

    y = model.addVars(depots, vtype=GRB.BINARY, name="y")
    x = model.addVars(depots, products, lb=0, name="x")
    q = model.addVars(depots, regions, products, lb=0, name="q")
    u = model.addVars(regions, products, lb=0, name="u")
    e = model.addVars(products, lb=0, name="e")

    for i in depots:
        model.addConstr(
            gp.quicksum(instance.product_volume[j] * x[i, j] for j in products)
            <= instance.capacity[i] * y[i],
            name=f"capacity[{i}]",
        )
        for j in products:
            model.addConstr(
                x[i, j] <= instance.inventory_upper_bound[i][j] * y[i],
                name=f"inventory_bound[{i},{j}]",
            )

    first_stage = gp.quicksum(instance.fixed_depot_cost[i] * y[i] for i in depots)
    first_stage += gp.quicksum(
        instance.inventory_cost[i][j] * x[i, j] for i in depots for j in products
    )
    if budget is not None:
        model.addConstr(first_stage <= budget, name="financial_budget")

    for r in regions:
        for j in products:
            model.addConstr(
                gp.quicksum(q[i, r, j] for i in depots) + u[r, j]
                >= instance.base_demand[r][j],
                name=f"demand[{r},{j}]",
            )
    for i in depots:
        for j in products:
            model.addConstr(
                gp.quicksum(q[i, r, j] for r in regions) <= x[i, j],
                name=f"supply[{i},{j}]",
            )
    for j in products:
        nominal_product_demand = sum(instance.base_demand[r][j] for r in regions)
        model.addConstr(
            gp.quicksum(u[r, j] for r in regions) - e[j]
            <= (1.0 - instance.service_level[j]) * nominal_product_demand,
            name=f"service[{j}]",
        )

    recourse = gp.quicksum(
        instance.transport_cost[i][r][j] * q[i, r, j]
        for i in depots
        for r in regions
        for j in products
    )
    recourse += gp.quicksum(
        instance.shortage_penalty[r][j] * u[r, j] for r in regions for j in products
    )
    recourse += gp.quicksum(instance.service_penalty[j] * e[j] for j in products)
    model.setObjective(first_stage + recourse, GRB.MINIMIZE)
    return model, y, x, first_stage, recourse


def solve_nominal_baseline(
    instance: InventoryInstance,
    budget: float | None = None,
) -> NominalBaseline:
    model, y, x, first_stage, recourse = build_nominal_model(instance, budget)
    model.optimize()
    if model.Status != 2:
        raise RuntimeError(f"Nominal model did not solve to optimality: status {model.Status}")
    return NominalBaseline(
        y=[int(round(y[i].X)) for i in range(instance.num_depots)],
        x=[
            [x[i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ],
        first_stage_spending=first_stage.getValue(),
        recourse_cost=recourse.getValue(),
        objective=model.ObjVal,
    )


def baseline_feasibility(
    instance: InventoryInstance,
    baseline: NominalBaseline,
    tolerance: float = 1e-7,
) -> dict[str, Any]:
    capacity_excesses = [
        sum(
            instance.product_volume[j] * baseline.x[i][j]
            for j in range(instance.num_products)
        )
        - instance.capacity[i] * baseline.y[i]
        for i in range(instance.num_depots)
    ]
    upper_bound_excesses = [
        baseline.x[i][j]
        - instance.inventory_upper_bound[i][j] * baseline.y[i]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    ]
    return {
        "capacity_compatible": max(capacity_excesses) <= tolerance,
        "capacity_violation_count": sum(value > tolerance for value in capacity_excesses),
        "maximum_capacity_excess": max(capacity_excesses),
        "ub_compatible": max(upper_bound_excesses) <= tolerance,
        "ub_violation_count": sum(value > tolerance for value in upper_bound_excesses),
        "maximum_ub_excess": max(upper_bound_excesses),
    }
