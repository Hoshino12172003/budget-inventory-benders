from math import comb

from robust_inventory_reconfiguration.risk_budget_composition import (
    compose_risk_budget,
    enumerate_gamma_allocations,
)


def test_canonical_gamma_allocations_include_slack_budget() -> None:
    allocations = enumerate_gamma_allocations(8, 2)
    assert len(allocations) == comb(10, 2) == 45
    assert allocations == sorted(allocations)
    assert (0,) * 8 in allocations
    assert any(sum(allocation) == 1 for allocation in allocations)
    assert all(sum(allocation) <= 2 for allocation in allocations)


def test_risk_budget_composition_selects_exact_maximum() -> None:
    result = compose_risk_budget([[1.0, 5.0, 6.0], [2.0, 3.0, 10.0]], 2)
    assert result.value == 11.0
    assert result.allocation == (0, 2)
