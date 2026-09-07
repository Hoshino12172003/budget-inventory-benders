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


@dataclass(frozen=True)
class ScenarioServiceResult:
    shock_set: tuple[tuple[str, str], ...]
    recourse_cost: float
    transportation_cost: float
    shortage_cost: float
    service_penalty_cost: float
    total_shortage: float
    minimum_fill_rate: float
    average_fill_rate: float
    worst_region_id: str


@dataclass(frozen=True)
class UnifiedServiceResult:
    robust_recourse_cost: float
    worst_recourse_scenario: ScenarioServiceResult
    worst_shortage_scenario: ScenarioServiceResult
    worst_service_scenario: ScenarioServiceResult
    scenario_count: int
    scenarios: tuple[ScenarioServiceResult, ...]


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
    """Return the frozen service-reporting view of the exact unified evaluation."""
    result = evaluate_robust_service_detailed(
        instance, x, gamma, optimality_tolerance=optimality_tolerance
    )
    service = result.worst_service_scenario
    return RobustServiceResult(
        robust_recourse_cost=result.robust_recourse_cost,
        minimum_fill_rate=service.minimum_fill_rate,
        average_fill_rate=service.average_fill_rate,
        worst_region_id=service.worst_region_id,
        worst_scenario=service.shock_set,
        total_shortage=service.total_shortage,
        scenario_count=result.scenario_count,
    )


def evaluate_robust_service_detailed(
    instance: InventoryInstance,
    x: list[list[float]],
    gamma: int,
    *,
    optimality_tolerance: float = 1e-7,
) -> UnifiedServiceResult:
    """Evaluate every scenario with the frozen exact recourse and service tie-break."""
    import gurobipy as gp
    from gurobipy import GRB

    depots = range(instance.num_depots)
    regions = range(instance.num_regions)
    model = gp.Model(f"service_evaluation_{instance.name}_g{gamma}")
    model.Params.OutputFlag = 0
    apply_formal_solver_profile(model, mixed_integer=False)
    costs = {}
    transportation_costs = {}
    shortage_costs = {}
    service_penalty_costs = {}
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
                transportation_cost = gp.quicksum(
                    instance.transport_cost[i][r][j] * q[i, r]
                    for i in depots
                    for r in regions
                )
                shortage_cost = gp.quicksum(
                    instance.shortage_penalty[r][j] * u[r] for r in regions
                )
                service_penalty_cost = instance.service_penalty[j] * e
                cost = transportation_cost + shortage_cost + service_penalty_cost
                costs[key] = cost
                transportation_costs[key] = transportation_cost
                shortage_costs[key] = shortage_cost
                service_penalty_costs[key] = service_penalty_cost
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
    scenario_results = []
    fill_rates_by_scenario = []
    for scenario in scenarios:
        by_product = tuple(
            tuple(r for r, product_index in scenario if product_index == j)
            for j in range(instance.num_products)
        )
        scenario_cost = sum(
            optimum_by_block[(j, by_product[j])]
            for j in range(instance.num_products)
        )
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
        _, worst_region, scenario_minimum_fill = select_worst_reporting_identity(
            [region_fill_rates]
        )
        scenario_keys = [(j, by_product[j]) for j in range(instance.num_products)]
        scenario_results.append(
            ScenarioServiceResult(
                shock_set=tuple(
                    (instance.region_ids[r], instance.product_ids[j])
                    for r, j in scenario
                ),
                recourse_cost=scenario_cost,
                transportation_cost=sum(
                    transportation_costs[key].getValue() for key in scenario_keys
                ),
                shortage_cost=sum(shortage_costs[key].getValue() for key in scenario_keys),
                service_penalty_cost=sum(
                    service_penalty_costs[key].getValue() for key in scenario_keys
                ),
                total_shortage=total_shortage,
                minimum_fill_rate=scenario_minimum_fill,
                average_fill_rate=sum(region_fill_rates) / instance.num_regions,
                worst_region_id=instance.region_ids[worst_region],
            )
        )

    worst_scenario_index, worst_region, worst_fill_rate = select_worst_reporting_identity(
        fill_rates_by_scenario
    )
    worst_service = scenario_results[worst_scenario_index]
    if (
        worst_service.worst_region_id != instance.region_ids[worst_region]
        or abs(worst_service.minimum_fill_rate - worst_fill_rate) > 1e-12
    ):
        raise RuntimeError("service reporting identity is inconsistent")
    worst_recourse = max(scenario_results, key=lambda value: value.recourse_cost)
    worst_shortage = max(scenario_results, key=lambda value: value.total_shortage)
    return UnifiedServiceResult(
        robust_recourse_cost=worst_recourse.recourse_cost,
        worst_recourse_scenario=worst_recourse,
        worst_shortage_scenario=worst_shortage,
        worst_service_scenario=worst_service,
        scenario_count=len(scenarios),
        scenarios=tuple(scenario_results),
    )
