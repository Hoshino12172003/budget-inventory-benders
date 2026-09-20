from __future__ import annotations

import pytest

from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import (
    _ExactParallelProductOracle,
    _compose_risk_budget_exact_dp,
    solve_accelerated_prb_benders,
)
from robust_inventory_reconfiguration.accelerated_product_risk_subproblem import (
    AcceleratedProductRiskSubproblem,
)
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget


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


def test_final_certification_bypasses_exact_cache(tiny_instance) -> None:
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
