from __future__ import annotations

import pytest

from robust_inventory_reconfiguration.scenarios import build_budgeted_binary_scenario


def test_uncertainty_set_integrity(tiny_instance) -> None:
    scenario = build_budgeted_binary_scenario(tiny_instance, {("R1", "P2")}, gamma=1)
    assert scenario.demand == [[4.0, 5.0], [2.0, 1.0]]
    assert len(scenario.active_components) == 1


def test_uncertainty_budget_is_enforced(tiny_instance) -> None:
    with pytest.raises(ValueError, match="budget"):
        build_budgeted_binary_scenario(tiny_instance, {("R1", "P1"), ("R2", "P2")}, gamma=1)


def test_uncertainty_identity_is_enforced(tiny_instance) -> None:
    with pytest.raises(ValueError, match="unknown"):
        build_budgeted_binary_scenario(tiny_instance, {("R3", "P1")}, gamma=1)
