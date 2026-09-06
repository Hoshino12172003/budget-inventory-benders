from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb

from .instance import InventoryInstance


@dataclass(frozen=True)
class DemandScenario:
    active_components: frozenset[tuple[str, str]]
    demand: list[list[float]]


def scenario_count(instance: InventoryInstance, gamma: int) -> int:
    if gamma < 0 or gamma > instance.num_regions * instance.num_products:
        raise ValueError("gamma is outside the uncertainty-set dimension")
    components = instance.num_regions * instance.num_products
    return sum(comb(components, k) for k in range(gamma + 1))


def enumerate_scenario_components(
    instance: InventoryInstance, gamma: int
) -> list[tuple[tuple[int, int], ...]]:
    """Canonical region-major enumeration of all binary shocks up to gamma."""
    if gamma < 0 or gamma > instance.num_regions * instance.num_products:
        raise ValueError("gamma is outside the uncertainty-set dimension")
    components = [
        (r, j)
        for r in range(instance.num_regions)
        for j in range(instance.num_products)
    ]
    return [
        scenario
        for active_count in range(gamma + 1)
        for scenario in combinations(components, active_count)
    ]


def build_budgeted_binary_scenario(
    instance: InventoryInstance,
    active_components: set[tuple[str, str]],
    gamma: int,
) -> DemandScenario:
    valid = {(region, product) for region in instance.region_ids for product in instance.product_ids}
    if not active_components <= valid:
        raise ValueError("scenario contains an unknown region-product identity")
    if gamma < 0 or len(active_components) > gamma:
        raise ValueError("scenario violates the uncertainty budget")
    active = frozenset(active_components)
    demand = []
    for r, region in enumerate(instance.region_ids):
        row = []
        for j, product in enumerate(instance.product_ids):
            z = 1.0 if (region, product) in active else 0.0
            row.append(instance.base_demand[r][j] + instance.demand_deviation[r][j] * z)
        demand.append(row)
    return DemandScenario(active, demand)
