from __future__ import annotations

import math
from itertools import combinations
from typing import Any

from .instance import InventoryInstance
from .robust_service import (
    ScenarioServiceResult,
    UnifiedServiceResult,
    evaluate_robust_service_detailed,
    select_worst_reporting_identity,
)
from .risk_budget_composition import enumerate_gamma_allocations
from .scenarios import enumerate_scenario_components
from .solver_profile import apply_formal_solver_profile


SUBOPTIMAL_TIEBREAK_ERROR = "Recourse reporting tie-break failed: 13"


def _attribute(model: Any, name: str) -> float | int | None:
    try:
        return getattr(model, name)
    except Exception:
        return None


def _scenario_results(
    instance: InventoryInstance,
    gamma: int,
    optimum_by_block: dict,
    transportation_costs: dict,
    shortage_costs: dict,
    service_penalty_costs: dict,
    shortages: dict,
) -> UnifiedServiceResult:
    regions = range(instance.num_regions)
    shortage_values = {
        key: [shortages[key][r].X for r in regions]
        for key in shortages
    }
    scenarios = enumerate_scenario_components(instance, gamma)
    results = []
    fill_rates_by_scenario = []
    for scenario in scenarios:
        by_product = tuple(
            tuple(r for r, product_index in scenario if product_index == j)
            for j in range(instance.num_products)
        )
        keys = [(j, by_product[j]) for j in range(instance.num_products)]
        region_fill_rates = []
        total_shortage = 0.0
        for r in regions:
            demand = sum(
                instance.base_demand[r][j]
                + (instance.demand_deviation[r][j] if (r, j) in scenario else 0.0)
                for j in range(instance.num_products)
            )
            shortage = sum(shortage_values[(j, by_product[j])][r] for j in range(instance.num_products))
            total_shortage += shortage
            region_fill_rates.append(1.0 if demand == 0 else 1.0 - shortage / demand)
        fill_rates_by_scenario.append(region_fill_rates)
        _, worst_region, minimum_fill = select_worst_reporting_identity([region_fill_rates])
        results.append(ScenarioServiceResult(
            shock_set=tuple((instance.region_ids[r], instance.product_ids[j]) for r, j in scenario),
            recourse_cost=sum(optimum_by_block[key] for key in keys),
            transportation_cost=sum(transportation_costs[key].getValue() for key in keys),
            shortage_cost=sum(shortage_costs[key].getValue() for key in keys),
            service_penalty_cost=sum(service_penalty_costs[key].getValue() for key in keys),
            total_shortage=total_shortage,
            minimum_fill_rate=minimum_fill,
            average_fill_rate=sum(region_fill_rates) / instance.num_regions,
            worst_region_id=instance.region_ids[worst_region],
        ))
    scenario_index, worst_region, worst_fill = select_worst_reporting_identity(fill_rates_by_scenario)
    worst_service = results[scenario_index]
    if worst_service.worst_region_id != instance.region_ids[worst_region] or abs(worst_service.minimum_fill_rate - worst_fill) > 1e-12:
        raise RuntimeError("service reporting identity is inconsistent")
    worst_recourse = max(results, key=lambda value: value.recourse_cost)
    return UnifiedServiceResult(
        robust_recourse_cost=worst_recourse.recourse_cost,
        worst_recourse_scenario=worst_recourse,
        worst_shortage_scenario=max(results, key=lambda value: value.total_shortage),
        worst_service_scenario=worst_service,
        scenario_count=len(scenarios),
        scenarios=tuple(results),
    )


def _diagnose_and_recover(
    instance: InventoryInstance,
    x: list[list[float]],
    gamma: int,
    optimality_tolerance: float,
    diagnostics_only: bool = False,
) -> tuple[UnifiedServiceResult | None, dict[str, Any]]:
    import gurobipy as gp
    from gurobipy import GRB

    depots = range(instance.num_depots)
    regions = range(instance.num_regions)
    model = gp.Model(f"e4_reporting_diagnostic_{instance.name}_g{gamma}")
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
                demand = []
                for r in regions:
                    value = instance.base_demand[r][j]
                    if r in shocked:
                        value += instance.demand_deviation[r][j]
                    demand.append(value)
                    model.addConstr(gp.quicksum(q[i, r] for i in depots) + u[r] >= value)
                for i in depots:
                    model.addConstr(gp.quicksum(q[i, r] for r in regions) <= x[i][j])
                model.addConstr(gp.quicksum(u[r] for r in regions) - e <= (1.0 - instance.service_level[j]) * sum(demand))
                transportation = gp.quicksum(instance.transport_cost[i][r][j] * q[i, r] for i in depots for r in regions)
                shortage = gp.quicksum(instance.shortage_penalty[r][j] * u[r] for r in regions)
                service = instance.service_penalty[j] * e
                costs[key] = transportation + shortage + service
                transportation_costs[key] = transportation
                shortage_costs[key] = shortage
                service_penalty_costs[key] = service
                shortages[key] = u

    model.setObjective(gp.quicksum(costs.values()), GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"Fixed-inventory recourse diagnostic failed: {model.Status}")
    optimum_by_block = {key: cost.getValue() for key, cost in costs.items()}
    for key, cost in costs.items():
        model.addConstr(cost <= optimum_by_block[key] + optimality_tolerance)

    quadratic = gp.quicksum(shortages[key][r] * shortages[key][r] for key in shortages for r in regions)
    model.setObjective(quadratic, GRB.MINIMIZE)
    model.optimize()
    status = int(model.Status)
    solution_count = int(model.SolCount)
    if solution_count == 0:
        raise RuntimeError(f"Recourse reporting tie-break has no feasible incumbent: {status}")
    maximum_cost_deviation = max(
        abs(cost.getValue() - optimum_by_block[key]) for key, cost in costs.items()
    )
    product_values = []
    product_tie_counts = []
    for j in range(instance.num_products):
        values = []
        tie_counts = []
        for product_gamma in range(gamma + 1):
            candidates = [
                value for (product, shocked_regions), value in optimum_by_block.items()
                if product == j and len(shocked_regions) == product_gamma
            ]
            best = max(candidates)
            values.append(best)
            tie_counts.append(sum(abs(value - best) <= optimality_tolerance for value in candidates))
        product_values.append(values)
        product_tie_counts.append(tie_counts)
    allocations = enumerate_gamma_allocations(instance.num_products, gamma)
    allocation_values = [
        sum(product_values[j][allocation[j]] for j in range(instance.num_products))
        for allocation in allocations
    ]
    robust_target = max(allocation_values)
    tied_allocations = [
        allocation for allocation, value in zip(allocations, allocation_values)
        if abs(value - robust_target) <= optimality_tolerance
    ]
    diagnostic = {
        "original_status": status,
        "original_status_name": "SUBOPTIMAL" if status == GRB.SUBOPTIMAL else "OPTIMAL" if status == GRB.OPTIMAL else "OTHER",
        "solution_count": solution_count,
        "objective_value": _attribute(model, "ObjVal"),
        "objective_bound": _attribute(model, "ObjBound"),
        "mip_gap": _attribute(model, "MIPGap"),
        "constraint_violation": _attribute(model, "ConstrVio"),
        "bound_violation": _attribute(model, "BoundVio"),
        "dual_violation": _attribute(model, "DualVio"),
        "kappa": _attribute(model, "Kappa"),
        "runtime_seconds": _attribute(model, "Runtime"),
        "node_count": _attribute(model, "NodeCount"),
        "simplex_iterations": _attribute(model, "IterCount"),
        "barrier_iterations": _attribute(model, "BarIterCount"),
        "is_mip": bool(model.IsMIP),
        "variable_count": int(model.NumVars),
        "constraint_count": int(model.NumConstrs),
        "quadratic_nonzeros": int(model.NumQNZs),
        "matrix_coefficient_min": _attribute(model, "MinCoeff"),
        "matrix_coefficient_max": _attribute(model, "MaxCoeff"),
        "objective_coefficient_min": _attribute(model, "MinObjCoeff"),
        "objective_coefficient_max": _attribute(model, "MaxObjCoeff"),
        "block_count": len(costs),
        "sum_of_fixed_block_recourse_targets": sum(optimum_by_block.values()),
        "minimum_block_recourse_target": min(optimum_by_block.values()),
        "maximum_block_recourse_target": max(optimum_by_block.values()),
        "maximum_absolute_block_recourse_deviation": maximum_cost_deviation,
        "certified_robust_recourse_target": robust_target,
        "tied_Gamma_allocation_count": len(tied_allocations),
        "tied_worst_scenario_count": sum(
            math.prod(product_tie_counts[j][allocation[j]] for j in range(instance.num_products))
            for allocation in tied_allocations
        ),
        "economic_band_tolerance": optimality_tolerance,
        "parameters": {
            "FeasibilityTol": model.Params.FeasibilityTol,
            "OptimalityTol": model.Params.OptimalityTol,
            "NumericFocus": model.Params.NumericFocus,
            "Method": model.Params.Method,
        },
        "secondary_objective": "minimize sum of squared shortage quantities across all product-risk blocks",
    }
    if diagnostics_only:
        return None, diagnostic
    if status == GRB.OPTIMAL:
        result = _scenario_results(
            instance, gamma, optimum_by_block, transportation_costs,
            shortage_costs, service_penalty_costs, shortages,
        )
        diagnostic["fallback_used"] = False
        return result, diagnostic
    if status != GRB.SUBOPTIMAL:
        raise RuntimeError(f"Unsupported recourse reporting tie-break status: {status}")

    total_shortages = {key: gp.quicksum(shortages[key][r] for r in regions) for key in shortages}
    model.setObjective(gp.quicksum(total_shortages.values()), GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"Linear total-shortage tie-break failed: {model.Status}")
    minimum_shortage_by_block = {key: expression.getValue() for key, expression in total_shortages.items()}
    for key, expression in total_shortages.items():
        model.addConstr(expression <= minimum_shortage_by_block[key] + optimality_tolerance)
    model.setObjective(
        gp.quicksum((r + 1) * shortages[key][r] for key in shortages for r in regions),
        GRB.MINIMIZE,
    )
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"Canonical linear reporting tie-break failed: {model.Status}")
    result = _scenario_results(
        instance, gamma, optimum_by_block, transportation_costs,
        shortage_costs, service_penalty_costs, shortages,
    )
    fallback_maximum_cost_deviation = max(
        abs(cost.getValue() - optimum_by_block[key]) for key, cost in costs.items()
    )
    diagnostic.update({
        "fallback_used": True,
        "fallback_rule": "minimize each block total shortage, then minimize region-order-weighted shortage",
        "fallback_status": int(model.Status),
        "fallback_status_name": "OPTIMAL",
        "fallback_runtime_seconds": _attribute(model, "Runtime"),
        "fallback_constraint_violation": _attribute(model, "ConstrVio"),
        "fallback_bound_violation": _attribute(model, "BoundVio"),
        "fallback_maximum_absolute_block_recourse_deviation": fallback_maximum_cost_deviation,
        "certified_robust_recourse": result.robust_recourse_cost,
        "selected_worst_recourse_shock_set": [list(pair) for pair in result.worst_recourse_scenario.shock_set],
        "selected_Gamma_allocation_count": len(result.worst_recourse_scenario.shock_set),
        "Gamma_feasible": len(result.worst_recourse_scenario.shock_set) <= gamma,
        "original_suboptimal_incumbent_preserved_primary_recourse": maximum_cost_deviation <= optimality_tolerance + model.Params.FeasibilityTol,
        "primary_economic_recourse_preserved": fallback_maximum_cost_deviation <= optimality_tolerance + model.Params.FeasibilityTol,
    })
    return result, diagnostic


def evaluate_e4_service(
    instance: InventoryInstance,
    x: list[list[float]],
    gamma: int,
    *,
    optimality_tolerance: float = 1e-7,
) -> tuple[UnifiedServiceResult, dict[str, Any]]:
    try:
        result = evaluate_robust_service_detailed(
            instance, x, gamma, optimality_tolerance=optimality_tolerance
        )
        return result, {
            "original_status": 2,
            "original_status_name": "OPTIMAL",
            "fallback_used": False,
            "economic_band_tolerance": optimality_tolerance,
        }
    except RuntimeError as error:
        if str(error) != SUBOPTIMAL_TIEBREAK_ERROR:
            raise
        return _diagnose_and_recover(instance, x, gamma, optimality_tolerance)


def diagnose_reporting_tiebreak(
    instance: InventoryInstance,
    x: list[list[float]],
    gamma: int,
    *,
    optimality_tolerance: float = 1e-7,
) -> dict[str, Any]:
    _, diagnostic = _diagnose_and_recover(
        instance, x, gamma, optimality_tolerance, diagnostics_only=True
    )
    return diagnostic
