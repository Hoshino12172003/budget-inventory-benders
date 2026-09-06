from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Any

from .instance import InventoryInstance


@dataclass(frozen=True)
class ReconfigurationSolution:
    objective: float
    first_stage_expenditure: float
    robust_recourse_cost: float
    y: list[int]
    x: list[list[float]]
    a_plus: list[list[float]]
    a_minus: list[list[float]]
    reconfiguration_cost: float


def reconfiguration_cost_value(
    instance: InventoryInstance,
    a_plus: list[list[float]],
    a_minus: list[list[float]],
    lambda_r: float,
) -> float:
    return lambda_r * sum(
        instance.inventory_cost[i][j] * (a_plus[i][j] + a_minus[i][j])
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )


def first_stage_expenditure_value(
    instance: InventoryInstance,
    y: list[int],
    x: list[list[float]],
    a_plus: list[list[float]],
    a_minus: list[list[float]],
    lambda_r: float,
) -> float:
    activation = sum(
        instance.fixed_depot_cost[i] * y[i] for i in range(instance.num_depots)
    )
    inventory = sum(
        instance.inventory_cost[i][j] * x[i][j]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    return activation + inventory + reconfiguration_cost_value(
        instance, a_plus, a_minus, lambda_r
    )


def reconfiguration_index(
    x: list[list[float]],
    x0: list[list[float]],
    a_plus: list[list[float]],
    a_minus: list[list[float]],
) -> tuple[float, float]:
    denominator = sum(map(sum, x0))
    direct = sum(
        abs(x[i][j] - x0[i][j])
        for i in range(len(x0))
        for j in range(len(x0[i]))
    ) / denominator
    represented = (sum(map(sum, a_plus)) + sum(map(sum, a_minus))) / denominator
    return direct, represented


def gamma_allocations(num_products: int, gamma: int) -> list[tuple[int, ...]]:
    """All product risk-budget allocations with total use at most gamma."""
    return [
        allocation
        for allocation in product(range(gamma + 1), repeat=num_products)
        if sum(allocation) <= gamma
    ]


def product_risk_budget_value(values: list[list[float]], gamma: int) -> float:
    """Exact max over integer product risk-budget allocations."""
    return max(
        sum(values[j][allocation[j]] for j in range(len(values)))
        for allocation in gamma_allocations(len(values), gamma)
    )


def build_exact_reconfiguration_model(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    include_reconfiguration: bool = True,
) -> tuple[Any, dict[str, Any]]:
    """Build a finite exact robust model; this is not a Benders implementation."""
    if gamma < 0:
        raise ValueError("gamma must be nonnegative")
    if lambda_r < 0:
        raise ValueError("lambda_r must be nonnegative")
    if len(x0) != instance.num_depots or any(
        len(row) != instance.num_products for row in x0
    ):
        raise ValueError("x0 has incompatible dimensions")

    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as exc:  # pragma: no cover - optional licensed solver
        raise RuntimeError("Reconfiguration calibration requires gurobipy") from exc

    depots = range(instance.num_depots)
    regions = range(instance.num_regions)
    products_index = range(instance.num_products)
    model = gp.Model(f"reconfiguration_{instance.name}_g{gamma}_l{lambda_r:g}")
    model.Params.OutputFlag = 0
    model.Params.MIPGap = 0
    model.Params.FeasibilityTol = 1e-8
    model.Params.OptimalityTol = 1e-8
    model.Params.IntFeasTol = 1e-8

    y = model.addVars(depots, vtype=GRB.BINARY, name="y")
    x = model.addVars(depots, products_index, lb=0, name="x")
    for i in depots:
        model.addConstr(
            gp.quicksum(instance.product_volume[j] * x[i, j] for j in products_index)
            <= instance.capacity[i] * y[i],
            name=f"capacity[{i}]",
        )
        for j in products_index:
            model.addConstr(
                x[i, j] <= instance.inventory_upper_bound[i][j] * y[i],
                name=f"inventory_bound[{i},{j}]",
            )

    base_spending = gp.quicksum(instance.fixed_depot_cost[i] * y[i] for i in depots)
    base_spending += gp.quicksum(
        instance.inventory_cost[i][j] * x[i, j]
        for i in depots
        for j in products_index
    )
    if include_reconfiguration:
        a_plus = model.addVars(depots, products_index, lb=0, name="a_plus")
        a_minus = model.addVars(depots, products_index, lb=0, name="a_minus")
        for i in depots:
            for j in products_index:
                model.addConstr(
                    x[i, j] - x0[i][j] == a_plus[i, j] - a_minus[i, j],
                    name=f"reconfiguration_balance[{i},{j}]",
                )
        reconfiguration_cost = lambda_r * gp.quicksum(
            instance.inventory_cost[i][j] * (a_plus[i, j] + a_minus[i, j])
            for i in depots
            for j in products_index
        )
    else:
        a_plus = None
        a_minus = None
        reconfiguration_cost = gp.LinExpr(0.0)
    first_stage = base_spending + reconfiguration_cost
    model.addConstr(first_stage <= budget, name="financial_budget")

    eta = model.addVars(products_index, range(gamma + 1), lb=0, name="eta")
    for j in products_index:
        for product_gamma in range(gamma + 1):
            for scenario_number, shocked_regions in enumerate(combinations(regions, product_gamma)):
                q = model.addVars(
                    depots,
                    regions,
                    lb=0,
                    name=f"q_{j}_{product_gamma}_{scenario_number}",
                )
                u = model.addVars(
                    regions, lb=0, name=f"u_{j}_{product_gamma}_{scenario_number}"
                )
                e = model.addVar(lb=0, name=f"e_{j}_{product_gamma}_{scenario_number}")
                shocked = set(shocked_regions)
                scenario_demand: list[float] = []
                for r in regions:
                    demand = instance.base_demand[r][j]
                    if r in shocked:
                        demand += instance.demand_deviation[r][j]
                    scenario_demand.append(demand)
                    model.addConstr(
                        gp.quicksum(q[i, r] for i in depots) + u[r] >= demand,
                        name=f"demand[{j},{product_gamma},{scenario_number},{r}]",
                    )
                for i in depots:
                    model.addConstr(
                        gp.quicksum(q[i, r] for r in regions) <= x[i, j],
                        name=f"supply[{j},{product_gamma},{scenario_number},{i}]",
                    )
                model.addConstr(
                    gp.quicksum(u[r] for r in regions) - e
                    <= (1.0 - instance.service_level[j]) * sum(scenario_demand),
                    name=f"service[{j},{product_gamma},{scenario_number}]",
                )
                scenario_cost = gp.quicksum(
                    instance.transport_cost[i][r][j] * q[i, r]
                    for i in depots
                    for r in regions
                )
                scenario_cost += gp.quicksum(
                    instance.shortage_penalty[r][j] * u[r] for r in regions
                )
                scenario_cost += instance.service_penalty[j] * e
                model.addConstr(
                    eta[j, product_gamma] >= scenario_cost,
                    name=f"product_worst_case[{j},{product_gamma},{scenario_number}]",
                )

    theta = model.addVar(lb=0, name="theta")
    for allocation_number, allocation in enumerate(
        gamma_allocations(instance.num_products, gamma)
    ):
        model.addConstr(
            theta >= gp.quicksum(eta[j, allocation[j]] for j in products_index),
            name=f"risk_budget[{allocation_number}]",
        )
    model.setObjective(first_stage + theta, GRB.MINIMIZE)
    return model, {
        "y": y,
        "x": x,
        "a_plus": a_plus,
        "a_minus": a_minus,
        "first_stage": first_stage,
        "reconfiguration_cost": reconfiguration_cost,
        "theta": theta,
    }


def solve_exact_reconfiguration(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    include_reconfiguration: bool = True,
) -> ReconfigurationSolution:
    model, variables = build_exact_reconfiguration_model(
        instance,
        x0,
        budget,
        gamma,
        lambda_r,
        include_reconfiguration=include_reconfiguration,
    )
    model.optimize()
    if model.Status != 2:
        raise RuntimeError(f"Reconfiguration model did not solve to optimality: {model.Status}")
    y = variables["y"]
    x = variables["x"]
    a_plus = variables["a_plus"]
    a_minus = variables["a_minus"]
    solved_x = [
        [x[i, j].X for j in range(instance.num_products)]
        for i in range(instance.num_depots)
    ]
    if include_reconfiguration and lambda_r > 0:
        plus_values = [
            [a_plus[i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
        minus_values = [
            [a_minus[i, j].X for j in range(instance.num_products)]
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
        objective=model.ObjVal,
        first_stage_expenditure=variables["first_stage"].getValue(),
        robust_recourse_cost=variables["theta"].X,
        y=[int(round(y[i].X)) for i in range(instance.num_depots)],
        x=solved_x,
        a_plus=plus_values,
        a_minus=minus_values,
        reconfiguration_cost=variables["reconfiguration_cost"].getValue(),
    )
