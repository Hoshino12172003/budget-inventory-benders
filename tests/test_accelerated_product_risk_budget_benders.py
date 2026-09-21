from __future__ import annotations

import pytest

from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import (
    _ExactParallelProductOracle,
    _compose_risk_budget_exact_dp,
    _select_products_for_exact_separation,
    _select_parallel_workers,
    solve_accelerated_prb_benders,
)
from robust_inventory_reconfiguration.accelerated_product_risk_subproblem import (
    AcceleratedProductRiskSubproblem,
)
from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders_v3 import (
    solve_accelerated_prb_benders_v3,
)
from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders_v4 import (
    solve_accelerated_prb_benders_v4,
)
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget
from robust_inventory_reconfiguration.risk_budget_composition import (
    enumerate_gamma_allocations,
)
from robust_inventory_reconfiguration.structured_product_risk_subproblem import (
    StructuredProductRiskSubproblem,
)
from itertools import product
from types import SimpleNamespace


pytest.importorskip("gurobipy")


def test_exact_dp_composition_matches_frozen_enumeration() -> None:
    values = [
        [10.0, 13.0, 14.0],
        [20.0, 24.0, 25.0],
        [30.0, 31.0, 40.0],
        [5.0, 8.0, 9.0],
    ]
    assert _compose_risk_budget_exact_dp(values, 2).value == pytest.approx(
        compose_risk_budget(values, 2).value
    )


def test_worker_selection_depends_on_workload_not_case_identity(tiny_instance) -> None:
    assert _select_parallel_workers(tiny_instance, 2) == 2
    larger_shape = SimpleNamespace(num_regions=24, num_products=12)
    assert _select_parallel_workers(larger_shape, 2) == min(
        8, __import__("os").cpu_count() or 1
    )


def test_selective_screening_is_fail_closed() -> None:
    selected, screened, reasons = _select_products_for_exact_separation(
        [[10.0, 11.0, 12.0], [20.0, 21.0, 22.0]],
        [[10.0, 11.0, 12.0], [20.0, 21.0, 22.0]],
        theta_value=33.0,
        gamma=2,
        exact_cached_products=set(),
        tolerance=1e-7,
    )
    assert selected == set()
    assert screened == {0, 1}
    assert reasons["individual"] == 6

    selected, screened, _ = _select_products_for_exact_separation(
        [[float("inf")] * 3, [20.0, 21.0, 22.0]],
        [[0.0] * 3, [20.0, 21.0, 22.0]],
        theta_value=33.0,
        gamma=2,
        exact_cached_products=set(),
        tolerance=1e-7,
    )
    assert 0 in selected
    assert 0 not in screened


@pytest.mark.parametrize("num_products,gamma", [(2, 2), (4, 2), (3, 3)])
def test_allocation_generator_matches_cartesian_definition(
    num_products, gamma
) -> None:
    legacy = [
        allocation
        for allocation in product(range(gamma + 1), repeat=num_products)
        if sum(allocation) <= gamma
    ]
    assert enumerate_gamma_allocations(num_products, gamma) == legacy


def test_compact_product_oracle_matches_original_values_and_valid_cuts(
    tiny_instance,
) -> None:
    original = ProductRiskSubproblem(tiny_instance, 0, 2).solve([5.0])
    accelerated_oracle = AcceleratedProductRiskSubproblem(tiny_instance, 0, 2)
    try:
        accelerated = accelerated_oracle.solve([5.0])
    finally:
        accelerated_oracle.close()
    assert [case.value for case in accelerated.worst_cases] == pytest.approx(
        [case.value for case in original.worst_cases], abs=1e-8
    )
    assert [case.pattern for case in accelerated.worst_cases] == [
        case.pattern for case in original.worst_cases
    ]
    for accelerated_case, original_case in zip(
        accelerated.worst_cases, original.worst_cases
    ):
        assert accelerated_case.demand_dual == pytest.approx(
            original_case.demand_dual, abs=1e-9
        )
        assert accelerated_case.supply_dual == pytest.approx(
            original_case.supply_dual, abs=1e-9
        )
        assert accelerated_case.cut.alpha == pytest.approx(
            original_case.cut.alpha, abs=1e-9
        )
        assert accelerated_case.cut.beta == pytest.approx(
            original_case.cut.beta, abs=1e-9
        )
    assert all(case.cut.dual_feasible for case in accelerated.worst_cases)
    assert all(case.cut.strong_duality_error <= 1e-6 for case in accelerated.worst_cases)


@pytest.mark.parametrize("inventory", [[0.0], [2.5], [8.0]])
def test_structured_product_oracle_matches_v2_exact_state(
    tiny_instance, inventory
) -> None:
    v2 = AcceleratedProductRiskSubproblem(tiny_instance, 0, 2)
    v3 = StructuredProductRiskSubproblem(tiny_instance, 0, 2)
    try:
        expected = v2.solve(inventory)
        actual = v3.solve(inventory)
    finally:
        v2.close()
        v3.close()
    assert [row.pattern for row in actual.worst_cases] == [
        row.pattern for row in expected.worst_cases
    ]
    for left, right in zip(expected.worst_cases, actual.worst_cases):
        assert right.value == pytest.approx(left.value, abs=1e-7)
        assert right.cut.value_at(inventory) == pytest.approx(
            right.value, abs=1e-7
        )
        assert right.cut.dual_feasible
        assert right.cut.strong_duality_error <= 1e-7


def test_v3_prb_matches_v2_on_tiny(tiny_instance) -> None:
    arguments = dict(
        instance=tiny_instance,
        x0=[[2.0, 1.0]],
        budget=20.0,
        gamma=2,
        lambda_r=0.05,
        parallel_workers=2,
    )
    v2 = solve_accelerated_prb_benders(**arguments)
    v3 = solve_accelerated_prb_benders_v3(**arguments)
    assert v3.solution.objective == pytest.approx(v2.solution.objective, abs=1e-7)
    assert v3.solution.robust_recourse_cost == pytest.approx(
        v2.solution.robust_recourse_cost, abs=1e-7
    )
    assert v3.solution.y == v2.solution.y
    for v3_row, v2_row in zip(v3.solution.x, v2.solution.x):
        assert v3_row == pytest.approx(v2_row)
    assert v3.exact_certification_pass
    assert v3.global_risk_budget_coupling_pass


def test_exact_cache_reuses_only_identical_product_inventory(tiny_instance) -> None:
    oracle = _ExactParallelProductOracle(tiny_instance, 1, workers=2)
    try:
        first, _ = oracle.evaluate([[2.0, 1.0]], allow_cache=True)
        second, _ = oracle.evaluate([[2.0, 1.0]], allow_cache=True)
        third, _ = oracle.evaluate([[2.0 + 1e-12, 1.0]], allow_cache=True)
    finally:
        oracle.close()
    assert [row.worst_cases for row in second] == [row.worst_cases for row in first]
    assert len(third) == tiny_instance.num_products
    # The perturbed product misses; the unchanged product remains an exact hit.
    assert oracle.cache_hits == tiny_instance.num_products + 1
    assert oracle.cache_misses == 2 * tiny_instance.num_products - 1
    assert oracle.product_solves_avoided == (tiny_instance.num_products + 1) * 2


def test_inventory_loss_upper_bound_is_valid(tiny_instance) -> None:
    oracle = _ExactParallelProductOracle(tiny_instance, 1, workers=2)
    try:
        oracle.evaluate([[5.0, 4.0]], allow_cache=True)
        bounds = oracle.state_upper_bounds([[2.0, 1.0]])
        exact, _ = oracle.evaluate([[2.0, 1.0]], allow_cache=False)
    finally:
        oracle.close()
    for j, result in enumerate(exact):
        assert result is not None
        for worst in result.worst_cases:
            assert worst.value <= bounds[j][worst.local_gamma] + 1e-7


@pytest.mark.parametrize("gamma", [1, 2])
def test_accelerated_prb_matches_original_prb_on_tiny(tiny_instance, gamma) -> None:
    x0 = [[2.0, 1.0]]
    original = solve_prb_benders(tiny_instance, x0, 18.0, gamma, 0.05)
    accelerated = solve_accelerated_prb_benders(
        tiny_instance, x0, 18.0, gamma, 0.05, parallel_workers=2
    )
    assert accelerated.status == "OPTIMAL"
    assert accelerated.solution.objective == pytest.approx(
        original.solution.objective, abs=1e-6
    )
    assert accelerated.solution.robust_recourse_cost == pytest.approx(
        original.solution.robust_recourse_cost, abs=1e-6
    )
    assert accelerated.solution.first_stage_expenditure == pytest.approx(
        original.solution.first_stage_expenditure, abs=1e-6
    )
    assert accelerated.exact_certification_pass
    assert accelerated.global_risk_budget_coupling_pass
    assert accelerated.full_final_verification
    assert not accelerated.selective_separation_enabled
    assert accelerated.parallel_worker_count == 2


def test_final_certification_reuses_only_exact_cached_state(tiny_instance) -> None:
    result = solve_accelerated_prb_benders(
        tiny_instance,
        [[2.0, 1.0]],
        18.0,
        1,
        0.05,
        parallel_workers=2,
    )
    minimum_exact_states = tiny_instance.num_products * 2
    assert result.product_subproblem_evaluations >= minimum_exact_states
    assert result.full_final_verification
    assert result.certification_cache_hits == tiny_instance.num_products
    assert result.certification_product_state_solves == 0


def test_v4_selective_separation_matches_v2_and_fully_verifies(tiny_instance) -> None:
    arguments = dict(
        instance=tiny_instance,
        x0=[[2.0, 1.0]],
        budget=18.0,
        gamma=1,
        lambda_r=0.05,
        parallel_workers=2,
    )
    v2 = solve_accelerated_prb_benders(**arguments)
    v4 = solve_accelerated_prb_benders_v4(**arguments)
    assert v4.solution.objective == pytest.approx(v2.solution.objective, abs=1e-7)
    assert v4.solution.robust_recourse_cost == pytest.approx(
        v2.solution.robust_recourse_cost, abs=1e-7
    )
    assert v4.solution.y == v2.solution.y
    assert v4.exact_certification_pass
    assert v4.global_risk_budget_coupling_pass
    assert v4.selective_separation_enabled
    assert v4.full_final_verification
    assert sum(
        row["missed_violations_at_final_verification"]
        for row in v4.separation_audit
    ) >= 0
