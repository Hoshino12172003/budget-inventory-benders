from __future__ import annotations

import inspect

import pytest

pytest.importorskip("gurobipy")

from robust_inventory_reconfiguration.exact_benchmark import solve_exact_benchmark
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget
from robust_inventory_reconfiguration.standard_benders import (
    AggregateCut,
    STANDARD_BENDERS_EXACT,
    _build_standard_master,
    evaluate_standard_benders_oracle,
    solve_standard_benders,
)


def test_aggregate_cut_is_tight_valid_and_preserves_gamma_coupling(tiny_instance) -> None:
    generating_x = [[2.0, 1.0]]
    oracle = evaluate_standard_benders_oracle(tiny_instance, generating_x, 2)
    assert oracle.cut.dual_feasible
    assert oracle.cut.strong_duality_error <= 1e-7
    assert oracle.cut.value_at(generating_x) == pytest.approx(oracle.value, abs=1e-7)
    assert sum(oracle.gamma_allocation) <= 2

    for candidate_x in ([[0.5, 0.5]], [[3.0, 2.0]], [[8.0, 6.0]]):
        candidate = evaluate_standard_benders_oracle(tiny_instance, candidate_x, 2)
        assert oracle.cut.value_at(candidate_x) <= candidate.value + 1e-7


def test_standard_oracle_matches_exact_product_budget_composition(tiny_instance) -> None:
    oracle = evaluate_standard_benders_oracle(tiny_instance, [[2.0, 1.0]], 1)
    product_values = []
    for j in range(tiny_instance.num_products):
        result = ProductRiskSubproblem(tiny_instance, j, 1).solve(
            [2.0 if j == 0 else 1.0]
        )
        product_values.append([worst.value for worst in result.worst_cases])
    independently_composed = compose_risk_budget(product_values, 1)
    assert oracle.value == pytest.approx(independently_composed.value)
    assert oracle.gamma_allocation == independently_composed.allocation
    assert oracle.product_subproblem_evaluations == 4


def test_standard_master_has_one_theta_and_no_prb_surrogates(tiny_instance) -> None:
    master, variables = _build_standard_master(tiny_instance, [[2.0, 1.0]], 18.0, 0.05)
    master.update()
    names = {variable.VarName for variable in master.getVars()}
    assert "theta" in names
    assert not any(name.startswith("eta[") for name in names)
    assert "eta" not in variables


def test_standard_solver_has_no_prb_cut_pool_input() -> None:
    assert STANDARD_BENDERS_EXACT
    parameters = inspect.signature(solve_standard_benders).parameters
    assert "cuts" not in parameters
    assert "warm_start" not in parameters


@pytest.mark.parametrize("gamma", [1, 2])
def test_direct_standard_and_prb_match_on_tiny(tiny_instance, gamma) -> None:
    x0 = [[2.0, 1.0]]
    direct = solve_exact_benchmark(tiny_instance, x0, 18.0, gamma, 0.05)
    standard = solve_standard_benders(tiny_instance, x0, 18.0, gamma, 0.05)
    prb = solve_prb_benders(tiny_instance, x0, 18.0, gamma, 0.05)
    assert direct.solution is not None
    objectives = [direct.solution.objective, standard.solution.objective, prb.solution.objective]
    assert max(objectives) - min(objectives) <= 1e-6
    assert standard.status == "OPTIMAL"
    assert standard.exact_certification_pass
    assert standard.cut_validity_pass
    assert standard.iterations[-1].relative_gap <= 1e-6
    assert not standard.iterations[-1].cut_added
    assert standard.final_absolute_gap <= 1e-6
    assert all(isinstance(cut, AggregateCut) for cut in standard.cuts)


def test_standard_input_and_iteration_guards(tiny_instance) -> None:
    with pytest.raises(ValueError, match="gamma"):
        solve_standard_benders(tiny_instance, [[2.0, 1.0]], 18.0, 3, 0.05)
    with pytest.raises(ValueError, match="nonnegative"):
        solve_standard_benders(tiny_instance, [[2.0, 1.0]], 18.0, 1, -0.1)
    with pytest.raises(RuntimeError, match="iteration limit"):
        solve_standard_benders(
            tiny_instance, [[2.0, 1.0]], 18.0, 1, 0.05, max_iterations=0
        )
