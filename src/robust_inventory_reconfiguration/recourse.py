from __future__ import annotations

from dataclasses import dataclass

from .instance import InventoryInstance


@dataclass(frozen=True)
class RecoursePlan:
    shipment: list[list[list[float]]]
    shortage: list[list[float]]
    service_violation: list[float]


def recourse_objective(instance: InventoryInstance, plan: RecoursePlan) -> float:
    transport = sum(
        instance.transport_cost[i][r][j] * plan.shipment[i][r][j]
        for i in range(instance.num_depots)
        for r in range(instance.num_regions)
        for j in range(instance.num_products)
    )
    shortage = sum(
        instance.shortage_penalty[r][j] * plan.shortage[r][j]
        for r in range(instance.num_regions)
        for j in range(instance.num_products)
    )
    service = sum(
        instance.service_penalty[j] * plan.service_violation[j]
        for j in range(instance.num_products)
    )
    return transport + shortage + service


def recourse_violations(
    instance: InventoryInstance,
    demand: list[list[float]],
    inventory: list[list[float]],
    plan: RecoursePlan,
    tolerance: float = 1e-9,
) -> list[str]:
    violations: list[str] = []
    for r in range(instance.num_regions):
        for j in range(instance.num_products):
            served = sum(plan.shipment[i][r][j] for i in range(instance.num_depots))
            if served + plan.shortage[r][j] + tolerance < demand[r][j]:
                violations.append(f"demand[{r},{j}]")
    for i in range(instance.num_depots):
        for j in range(instance.num_products):
            shipped = sum(plan.shipment[i][r][j] for r in range(instance.num_regions))
            if shipped > inventory[i][j] + tolerance:
                violations.append(f"supply[{i},{j}]")
    for j in range(instance.num_products):
        total_shortage = sum(plan.shortage[r][j] for r in range(instance.num_regions))
        allowance = (1.0 - instance.service_level[j]) * sum(
            demand[r][j] for r in range(instance.num_regions)
        )
        if total_shortage - plan.service_violation[j] > allowance + tolerance:
            violations.append(f"service[{j}]")
    return violations


def product_objective_components(instance: InventoryInstance, plan: RecoursePlan) -> list[float]:
    return [
        sum(
            instance.transport_cost[i][r][j] * plan.shipment[i][r][j]
            for i in range(instance.num_depots)
            for r in range(instance.num_regions)
        )
        + sum(
            instance.shortage_penalty[r][j] * plan.shortage[r][j]
            for r in range(instance.num_regions)
        )
        + instance.service_penalty[j] * plan.service_violation[j]
        for j in range(instance.num_products)
    ]
