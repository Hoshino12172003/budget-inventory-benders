from __future__ import annotations

from robust_inventory_reconfiguration.nominal_baseline import NominalBaseline, baseline_feasibility


def test_baseline_feasibility_accepts_capacity_and_ub_compatible_plan(tiny_instance) -> None:
    baseline = NominalBaseline(
        y=[1],
        x=[[2.0, 1.0]],
        first_stage_spending=0.0,
        recourse_cost=0.0,
        objective=0.0,
    )
    result = baseline_feasibility(tiny_instance, baseline)
    assert result["capacity_compatible"] is True
    assert result["ub_compatible"] is True


def test_baseline_feasibility_detects_capacity_and_ub_excess(tiny_instance) -> None:
    baseline = NominalBaseline(
        y=[0],
        x=[[2.0, 1.0]],
        first_stage_spending=0.0,
        recourse_cost=0.0,
        objective=0.0,
    )
    result = baseline_feasibility(tiny_instance, baseline)
    assert result["capacity_violation_count"] == 1
    assert result["ub_violation_count"] == 2
