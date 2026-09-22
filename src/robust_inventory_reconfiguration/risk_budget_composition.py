from __future__ import annotations

from dataclasses import dataclass


def enumerate_gamma_allocations(num_products: int, gamma: int) -> list[tuple[int, ...]]:
    """Canonical allocations including every vector whose sum is at most Gamma."""
    if num_products <= 0 or gamma < 0:
        raise ValueError("num_products must be positive and gamma nonnegative")
    allocations = []

    def extend(prefix: tuple[int, ...], remaining: int) -> None:
        if len(prefix) == num_products:
            allocations.append(prefix)
            return
        for local_gamma in range(remaining + 1):
            extend(prefix + (local_gamma,), remaining - local_gamma)

    extend((), gamma)
    return allocations


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
