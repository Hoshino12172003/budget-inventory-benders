import pytest

from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem


pytest.importorskip("gurobipy")


def test_exact_g_product_cuts_are_dual_valid_and_tight(tiny_instance) -> None:
    subproblem = ProductRiskSubproblem(tiny_instance, 0, 2)
    generated = subproblem.solve([5.0])
    assert [case.local_gamma for case in generated.worst_cases] == [0, 1, 2]
    assert generated.pattern_evaluations == 4
    for case in generated.worst_cases:
        assert len(case.pattern) == case.local_gamma
        assert case.cut.dual_feasible
        assert case.cut.strong_duality_error <= 1e-6
        assert abs(case.cut.value_at([5.0]) - case.value) <= 1e-6
        for sample in ([0.0], [2.5], [10.0]):
            exact = subproblem.solve(list(sample)).worst_cases[case.local_gamma].value
            assert case.cut.value_at(sample) <= exact + 1e-6


def test_solver_scale_negative_inventory_noise_is_projected(tiny_instance) -> None:
    subproblem = ProductRiskSubproblem(tiny_instance, 0, 0)
    assert subproblem.solve([-1e-10]).worst_cases[0].value >= 0
    with pytest.raises(ValueError, match="materially negative"):
        subproblem.solve([-1e-3])
