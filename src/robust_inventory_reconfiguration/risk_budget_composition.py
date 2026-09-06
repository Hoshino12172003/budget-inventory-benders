from __future__ import annotations

from dataclasses import dataclass
from itertools import product


def enumerate_gamma_allocations(num_products: int, gamma: int) -> list[tuple[int, ...]]:
    """Canonical allocations including every vector whose sum is at most Gamma."""
    if num_products <= 0 or gamma < 0:
        raise ValueError("num_products must be positive and gamma nonnegative")
    return [
        allocation
        for allocation in product(range(gamma + 1), repeat=num_products)
        if sum(allocation) <= gamma
    ]


@dataclass(frozen=True)
class RiskBudgetComposition:
    value: float
    allocation: tuple[int, ...]


def compose_risk_budget(
    product_values: list[list[float]], gamma: int
) -> RiskBudgetComposition:
    allocations = enumerate_gamma_allocations(len(product_values), gamma)
    values = [
        sum(product_values[j][allocation[j]] for j in range(len(product_values)))
        for allocation in allocations
    ]
    best = max(range(len(allocations)), key=values.__getitem__)
    return RiskBudgetComposition(values[best], allocations[best])
