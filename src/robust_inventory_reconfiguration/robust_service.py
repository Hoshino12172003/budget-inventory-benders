from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .instance import InventoryInstance
from .scenarios import enumerate_scenario_components
from .solver_profile import apply_formal_solver_profile


@dataclass(frozen=True)
class RobustServiceResult:
    robust_recourse_cost: float
    minimum_fill_rate: float
    average_fill_rate: float
    worst_region_id: str
    worst_scenario: tuple[tuple[str, str], ...]
    total_shortage: float
    scenario_count: int


def select_worst_reporting_identity(
    fill_rates_by_scenario: list[list[float]],
    tolerance: float = 1e-12,
) -> tuple[int, int, float]:
    """Lowest fill rate, then canonical scenario, then canonical region."""
    best_scenario = 0
    best_region = 0
    best_fill_rate = float("inf")
    for scenario_index, region_fill_rates in enumerate(fill_rates_by_scenario):
        for region_index, fill_rate in enumerate(region_fill_rates):
            if fill_rate < best_fill_rate - tolerance:
                best_scenario = scenario_index
                best_region = region_index
                best_fill_rate = fill_rate
    return best_scenario, best_region, best_fill_rate


def evaluate_robust_service(
    instance: InventoryInstance,
    x: list[list[float]],
    gamma: int,
    *,
    optimality_tolerance: float = 1e-7,
) -> RobustServiceResult:
    """Evaluate every global scenario using cached exact product recourse blocks."""
    import gurobipy as gp
    from gurobipy import GRB

    depots = range(instance.num_depots)
    regions = range(instance.num_regions)
    model = gp.Model(f"service_evaluation_{instance.name}_g{gamma}")
    model.Params.OutputFlag = 0
    apply_formal_solver_profile(model, mixed_integer=False)
    costs = {}
    shortages = {}

    for j in range(instance.num_products):
        for product_gamma in range(gamma + 1):
            for shocked_regions in combinations(regions, product_gamma):
                key = (j, shocked_regions)
                q = model.addVars(depots, regions, lb=0, name=f"q_{j}_{'_'.join(map(str, shocked_regions))}")
                u = model.addVars(regions, lb=0, name=f"u_{j}_{'_'.join(map(str, shocked_regions))}")
                e = model.addVar(lb=0, name=f"e_{j}_{'_'.join(map(str, shocked_regions))}")
                shocked = set(shocked_regions)
                scenario_demand = []
                for r in regions:
                    demand = instance.base_demand[r][j]
                    if r in shocked:
                        demand += instance.demand_deviation[r][j]
                    scenario_demand.append(demand)
                    model.addConstr(gp.quicksum(q[i, r] for i in depots) + u[r] >= demand)
                for i in depots:
                    model.addConstr(gp.quicksum(q[i, r] for r in regions) <= x[i][j])
                model.addConstr(
                    gp.quicksum(u[r] for r in regions) - e
                    <= (1.0 - instance.service_level[j]) * sum(scenario_demand)
                )
                cost = gp.quicksum(
                    instance.transport_cost[i][r][j] * q[i, r]
                    for i in depots
                    for r in regions
                )
                cost += gp.quicksum(instance.shortage_penalty[r][j] * u[r] for r in regions)
                cost += instance.service_penalty[j] * e
                costs[key] = cost
                shortages[key] = u

    model.setObjective(gp.quicksum(costs.values()), GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"Fixed-inventory recourse evaluation failed: {model.Status}")
    optimum_by_block = {key: cost.getValue() for key, cost in costs.items()}
    for key, cost in costs.items():
        model.addConstr(cost <= optimum_by_block[key] + optimality_tolerance)
    model.setObjective(
        gp.quicksum(
            shortages[key][r] * shortages[key][r]
            for key in shortages
            for r in regions
        ),
        GRB.MINIMIZE,
    )
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"Recourse reporting tie-break failed: {model.Status}")

    shortage_values = {
        key: [shortages[key][r].X for r in regions]
        for key in shortages
    }
    scenarios = enumerate_scenario_components(instance, gamma)
    robust_cost = 0.0
    fill_rates_by_scenario = []
    total_shortage_by_scenario = []
    for scenario in scenarios:
        by_product = tuple(
            tuple(r for r, product_index in scenario if product_index == j)
            for j in range(instance.num_products)
        )
        scenario_cost = sum(
            optimum_by_block[(j, by_product[j])]
            for j in range(instance.num_products)
        )
        robust_cost = max(robust_cost, scenario_cost)
        region_fill_rates = []
        total_shortage = 0.0
        for r in regions:
            demand = sum(
                instance.base_demand[r][j]
                + (instance.demand_deviation[r][j] if (r, j) in scenario else 0.0)
                for j in range(instance.num_products)
            )
            shortage = sum(
                shortage_values[(j, by_product[j])][r]
                for j in range(instance.num_products)
            )
            total_shortage += shortage
            region_fill_rates.append(1.0 if demand == 0 else 1.0 - shortage / demand)
        fill_rates_by_scenario.append(region_fill_rates)
        total_shortage_by_scenario.append(total_shortage)

    worst_scenario_index, worst_region, worst_fill_rate = select_worst_reporting_identity(
        fill_rates_by_scenario
    )
    worst_scenario = scenarios[worst_scenario_index]
    worst_average = sum(fill_rates_by_scenario[worst_scenario_index]) / instance.num_regions
    worst_shortage = total_shortage_by_scenario[worst_scenario_index]

    return RobustServiceResult(
        robust_recourse_cost=robust_cost,
        minimum_fill_rate=worst_fill_rate,
        average_fill_rate=worst_average,
        worst_region_id=instance.region_ids[worst_region],
        worst_scenario=tuple(
            (instance.region_ids[r], instance.product_ids[j]) for r, j in worst_scenario
        ),
        total_shortage=worst_shortage,
        scenario_count=len(scenarios),
    )
