from __future__ import annotations

import inspect
import os

import pytest

from robust_inventory_reconfiguration.prb_ablation import (
    ExactProductScenarioBranchAndBound,
    select_adaptive_cuts,
    solve_prb_ablation,
)
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.exact_benchmark import solve_global_scenario_benchmark


def test_ablation_source_preserves_algorithm_boundaries() -> None:
    source = inspect.getsource(__import__(
        "robust_inventory_reconfiguration.prb_ablation", fromlist=["dummy"]
    ))
    assert "pure_benders" not in source
    assert "standard_benders" not in source
    assert "ProductRiskSubproblem" in source
    assert "theta" in source
    assert "select_adaptive_cuts" in source


def test_adaptive_selection_is_deterministic_nonempty_and_not_all() -> None:
    class Case:
        def __init__(self, gamma: int):
            self.local_gamma = gamma

    violations = [
        (float(20 - index), index % 5, Case(index % 3))
        for index in range(16)
    ]
    first = select_adaptive_cuts(
        violations, iteration=1, relative_gap=0.1, existing_cut_count=0
    )
    second = select_adaptive_cuts(
        violations, iteration=1, relative_gap=0.1, existing_cut_count=0
    )
    assert first == second
    assert 1 <= len(first) < len(violations)
    assert first[0][0] == max(row[0] for row in violations)
    closure = select_adaptive_cuts(
        violations, iteration=20, relative_gap=1e-4, existing_cut_count=100
    )
    assert len(closure) == len(violations)


@pytest.mark.skipif(
    os.environ.get("RUN_PRB_ABLATION_OPTIMIZATION_TESTS") != "1",
    reason="requires explicit authorization because it calls Gurobi optimize",
)
def test_product_screening_matches_full_enumeration(tiny_instance) -> None:
    pytest.importorskip("gurobipy")
    for product in range(tiny_instance.num_products):
        screened = ExactProductScenarioBranchAndBound(tiny_instance, product, 2)
        full = ProductRiskSubproblem(tiny_instance, product, 2)
        try:
            screened_result = screened.solve([5.0])
            full_result = full.solve([5.0])
        finally:
            screened.close()
            full.model.dispose()
        assert [case.pattern for case in screened_result.worst_cases] == [
            case.pattern for case in full_result.worst_cases
        ]
        for screened_case, full_case in zip(
            screened_result.worst_cases, full_result.worst_cases, strict=True
        ):
            assert screened_case.value == pytest.approx(full_case.value, abs=1e-7)
            assert screened_case.cut.dual_feasible
            assert screened_case.cut.strong_duality_error <= 1e-6
        assert (
            screened_result.screening.lp_solves
            + screened_result.screening.safely_pruned_patterns
            == screened_result.screening.total_patterns
        )


@pytest.mark.skipif(
    os.environ.get("RUN_PRB_ABLATION_OPTIMIZATION_TESTS") != "1",
    reason="requires explicit authorization because it calls Gurobi optimize",
)
@pytest.mark.parametrize(
    ("method_id", "screening", "adaptive"),
    [
        ("PRB-SG", True, False),
        ("A-PRB", False, True),
        ("A-PRB-SG", True, True),
    ],
)
def test_full_ablation_matches_direct_and_original_prb(
    tiny_instance, method_id, screening, adaptive
) -> None:
    pytest.importorskip("gurobipy")
    x0 = [[2.0, 1.0]]
    direct = solve_global_scenario_benchmark(tiny_instance, x0, 18.0, 2, 0.05)
    original = solve_prb_benders(tiny_instance, x0, 18.0, 2, 0.05)
    tested = solve_prb_ablation(
        tiny_instance,
        x0,
        18.0,
        2,
        0.05,
        method_id=method_id,
        scenario_screening=screening,
        adaptive_cut_selection=adaptive,
    )
    assert tested.status == "OPTIMAL"
    assert tested.exact_certification_pass
    assert tested.global_risk_budget_coupling_pass
    assert tested.solution.objective == pytest.approx(direct.solution.objective, abs=1e-6)
    assert tested.solution.objective == pytest.approx(original.solution.objective, abs=1e-6)
    assert all(cut.dual_feasible for cut in tested.cuts)
    assert max((cut.strong_duality_error for cut in tested.cuts), default=0.0) <= 1e-6
