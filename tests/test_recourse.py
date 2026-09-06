from __future__ import annotations

from robust_inventory_reconfiguration.recourse import (
    RecoursePlan,
    product_objective_components,
    recourse_objective,
    recourse_violations,
)


def _plan() -> RecoursePlan:
    return RecoursePlan(
        shipment=[[[4.0, 3.0], [2.0, 1.0]]],
        shortage=[[0.0, 0.0], [0.0, 0.0]],
        service_violation=[0.0, 0.0],
    )


def test_fixed_scenario_recourse_correctness(tiny_instance) -> None:
    plan = _plan()
    assert recourse_violations(tiny_instance, tiny_instance.base_demand, [[6.0, 4.0]], plan) == []
    assert recourse_objective(tiny_instance, plan) == 20.0


def test_recourse_detects_supply_violation(tiny_instance) -> None:
    violations = recourse_violations(tiny_instance, tiny_instance.base_demand, [[5.0, 4.0]], _plan())
    assert violations == ["supply[0,0]"]


def test_product_separability_static_identity(tiny_instance) -> None:
    plan = _plan()
    assert sum(product_objective_components(tiny_instance, plan)) == recourse_objective(tiny_instance, plan)
