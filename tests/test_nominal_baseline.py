from __future__ import annotations

import pytest

from robust_inventory_reconfiguration.instance import InventoryInstance
from robust_inventory_reconfiguration.nominal_baseline import (
    CANONICAL_NUMERICAL_REPAIR_PROFILE,
    CANONICAL_NOMINAL_RULE,
    OBJECTIVE_FACE_TOLERANCE,
    NominalBaseline,
    baseline_feasibility,
    solve_canonical_nominal_baseline,
)


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


def test_canonical_selector_is_deterministic_on_nonunique_primary_face() -> None:
    instance = InventoryInstance(
        name="nonunique_nominal_face",
        depot_ids=["west", "east"], region_ids=["region"], product_ids=["product"],
        base_demand=[[1.0]], demand_deviation=[[0.0]],
        transport_cost=[[[0.0]], [[0.0]]], shortage_penalty=[[100.0]],
        service_level=[1.0], service_penalty=[100.0], capacity=[1.0, 1.0],
        inventory_upper_bound=[[1.0], [1.0]], fixed_depot_cost=[0.0, 0.0],
        inventory_cost=[[1.0], [1.0]], product_volume=[1.0],
        initial_inventory=None, reconfiguration_cost_multiplier=None, provenance={},
    )
    first = solve_canonical_nominal_baseline(instance)
    second = solve_canonical_nominal_baseline(instance)
    assert first.rule == CANONICAL_NOMINAL_RULE
    assert first.baseline.y == second.baseline.y == [0, 1]
    assert first.baseline.x == second.baseline.x
    assert first.baseline.x[0][0] == pytest.approx(0.0, abs=1e-8)
    assert first.baseline.x[1][0] == pytest.approx(1.0, abs=1e-8)
    assert abs(first.objective_delta) <= OBJECTIVE_FACE_TOLERANCE
    assert first.primary_objective == second.primary_objective
    assert first.numerical_repair_used is False
    assert first.repair_profile is None


def test_canonical_numerical_retry_is_explicit(monkeypatch, tiny_instance) -> None:
    import robust_inventory_reconfiguration.nominal_baseline as nominal

    calls = []
    repaired = nominal.CanonicalNominalBaseline(
        baseline=nominal.NominalBaseline([1], [[0.0, 0.0]], 0.0, 0.0, 0.0),
        primary_objective=0.0,
        canonical_objective=0.0,
        objective_delta=0.0,
        solve_count=1,
        objective_face_tolerance=OBJECTIVE_FACE_TOLERANCE,
        numerical_repair_used=True,
        repair_profile=CANONICAL_NUMERICAL_REPAIR_PROFILE,
        continuous_fix_tolerance=nominal.CONTINUOUS_FIX_TOLERANCE,
    )

    def fake_once(_instance, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("Canonical nominal stage failed at position 1")
        return repaired

    monkeypatch.setattr(nominal, "_solve_canonical_nominal_baseline_once", fake_once)
    result = nominal.solve_canonical_nominal_baseline(tiny_instance)

    assert result is repaired
    assert calls[0]["fix_with_bounds"] is False
    assert calls[1]["fix_with_bounds"] is True
    assert calls[1]["objective_face_relative_tolerance"] == nominal.OBJECTIVE_FACE_RELATIVE_TOLERANCE
    assert calls[1]["continuous_fix_tolerance"] == nominal.CONTINUOUS_FIX_TOLERANCE
    assert calls[1]["repair_profile"] == CANONICAL_NUMERICAL_REPAIR_PROFILE


def test_canonical_numerical_retry_does_not_mask_structural_failure(
    monkeypatch, tiny_instance
) -> None:
    import robust_inventory_reconfiguration.nominal_baseline as nominal

    calls = 0

    def fake_once(_instance, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("Primary nominal model did not solve to optimality: 3")

    monkeypatch.setattr(nominal, "_solve_canonical_nominal_baseline_once", fake_once)
    with pytest.raises(RuntimeError, match="Primary nominal model"):
        nominal.solve_canonical_nominal_baseline(tiny_instance)
    assert calls == 1
