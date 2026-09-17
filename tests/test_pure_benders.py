from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("gurobipy")

from robust_inventory_reconfiguration.exact_benchmark import solve_exact_benchmark
from robust_inventory_reconfiguration.pure_benders import (
    GlobalRobustAdversarialSubproblem,
    _build_pure_master,
    estimate_global_adversarial_size,
    solve_pure_benders,
)


def test_global_adversary_matches_literal_exact_value_and_cut(tiny_instance) -> None:
    oracle = GlobalRobustAdversarialSubproblem(tiny_instance, 2)
    generating_x = [[2.0, 1.0]]
    result = oracle.solve(generating_x)
    assert result.cut.dual_feasible
    assert result.cut.strong_duality_error <= 1e-7
    assert result.cut.value_at(generating_x) == pytest.approx(result.value, abs=1e-7)
    assert len(result.cut.shock_pattern) <= 2
    for candidate_x in ([[0.5, 0.5]], [[3.0, 2.0]], [[8.0, 6.0]]):
        candidate = oracle.solve(candidate_x)
        assert result.cut.value_at(candidate_x) <= candidate.value + 1e-7


def test_pure_master_has_only_one_aggregate_surrogate(tiny_instance) -> None:
    model, variables = _build_pure_master(tiny_instance, [[2.0, 1.0]], 18.0, 0.05)
    model.update()
    names = {variable.VarName for variable in model.getVars()}
    assert "theta" in names
    assert not any(name.startswith("eta[") for name in names)
    assert "eta" not in variables


@pytest.mark.parametrize("gamma", [1, 2])
def test_direct_and_pure_benders_match_on_tiny(tiny_instance, gamma) -> None:
    x0 = [[2.0, 1.0]]
    direct = solve_exact_benchmark(tiny_instance, x0, 18.0, gamma, 0.05)
    pure = solve_pure_benders(tiny_instance, x0, 18.0, gamma, 0.05)
    assert direct.solution is not None
    assert pure.status == "OPTIMAL"
    assert pure.exact_certification_pass
    assert pure.cut_validity_pass
    assert pure.solution.objective == pytest.approx(direct.solution.objective, abs=1e-6)


def test_global_adversarial_size_formula(tiny_instance) -> None:
    size = estimate_global_adversarial_size(tiny_instance)
    assert size == {
        "binary_variables": 4,
        "continuous_variables": 16,
        "total_variables": 20,
        "constraints": 33,
    }


def test_pure_module_has_no_structured_or_product_risk_dependency() -> None:
    source_path = Path(__file__).parents[1] / "src/robust_inventory_reconfiguration/pure_benders.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = {
        "product_risk_subproblem",
        "risk_budget_composition",
        "standard_benders",
        "product_risk_budget_benders",
    }
    assert not any(any(part in name for part in forbidden) for name in imports)
    source = source_path.read_text(encoding="utf-8")
    assert "compose_risk_budget" not in source
    assert "ProductRiskSubproblem" not in source
    assigned_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
        if isinstance(target, ast.Name)
    }
    assert "eta" not in assigned_names
