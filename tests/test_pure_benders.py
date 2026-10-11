from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("gurobipy")

from robust_inventory_reconfiguration.exact_benchmark import solve_exact_benchmark
import robust_inventory_reconfiguration.pure_benders as pure_benders_module
from robust_inventory_reconfiguration.pure_benders import (
    GlobalAdversarialResult,
    GlobalRobustAdversarialSubproblem,
    PureAggregateCut,
    _build_pure_master,
    _cut_signature,
    _cut_violation,
    _cut_validation_record,
    _enforce_duplicate_cut_guard,
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


def test_cut_validation_uses_exact_master_expression(tiny_instance) -> None:
    model, variables = _build_pure_master(tiny_instance, [[2.0, 1.0]], 18.0, 0.05)
    cut = PureAggregateCut(
        alpha=4.0,
        beta=((-0.5, -0.25),),
        generation_value=2.75,
        generation_x=((2.0, 1.0),),
        shock_pattern=(),
        dual_feasible=True,
        strong_duality_error=0.0,
    )
    constraint = model.addConstr(
        variables["theta"] >= cut.alpha + sum(
            cut.beta[i][j] * variables["x"][i, j]
            for i in range(tiny_instance.num_depots)
            for j in range(tiny_instance.num_products)
        ),
        name="diagnostic_cut",
    )
    model.optimize()
    record = _cut_validation_record(
        model,
        variables,
        cut,
        constraint,
        cut_id=0,
        iteration_added=1,
        current_iteration=2,
        feasibility_tolerance=model.Params.FeasibilityTol,
    )
    assert record["master_expression_audit"]["identical_to_stored_cut"]
    assert record["master_expression_audit"]["maximum_coefficient_difference"] == 0.0
    assert record["master_expression_audit"]["rhs_intercept_difference"] == 0.0
    assert record["signed_violation"] == pytest.approx(
        record["master_expression_audit"]["actual_solver_signed_violation"]
    )


def test_zero_cut_violation_is_not_primal_dual_certification_residual(
    tiny_instance, monkeypatch
) -> None:
    certified_value = 4.0000002

    class FixedResidualOracle:
        def __init__(self, instance, gamma) -> None:
            self.instance = instance

        def solve(self, x, *, time_limit=None, certify=True) -> GlobalAdversarialResult:
            cut = PureAggregateCut(
                alpha=4.0,
                beta=tuple(
                    tuple(0.0 for _ in range(self.instance.num_products))
                    for _ in range(self.instance.num_depots)
                ),
                generation_value=4.0,
                generation_x=tuple(tuple(row) for row in x),
                shock_pattern=(),
                dual_feasible=True,
                strong_duality_error=certified_value - 4.0,
            )
            return GlobalAdversarialResult(
                value=certified_value,
                cut=cut,
                fixed_scenario_value=certified_value,
                mip_runtime=0.0,
                certification_runtime=0.0,
                binary_variables=0,
                continuous_variables=0,
                constraints=0,
            )

    monkeypatch.setattr(
        pure_benders_module, "GlobalRobustAdversarialSubproblem", FixedResidualOracle
    )
    result = solve_pure_benders(
        tiny_instance, [[2.0, 1.0]], 18.0, 2, 0.05
    )
    assert result.status == "OPTIMAL"
    assert result.aggregate_cut_count == 1
    assert result.iterations[-1].cut_violation == 0.0
    assert result.solution.robust_recourse_cost == pytest.approx(certified_value)
    assert result.final_upper_bound == pytest.approx(
        result.solution.first_stage_expenditure + certified_value
    )


def test_genuinely_violated_duplicate_cut_is_still_rejected() -> None:
    cut = PureAggregateCut(
        alpha=4.0,
        beta=((0.0, 0.0),),
        generation_value=4.0,
        generation_x=((0.0, 0.0),),
        shock_pattern=(),
        dual_feasible=True,
        strong_duality_error=0.0,
    )
    signatures = {_cut_signature(cut)}
    violation = _cut_violation(cut, [[0.0, 0.0]], theta=3.0)
    assert violation == 1.0
    assert _cut_signature(cut) in signatures
    with pytest.raises(RuntimeError, match="previously added Pure Benders cut"):
        _enforce_duplicate_cut_guard(
            cut, [[0.0, 0.0]], 3.0, 1e-7, signatures
        )


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
