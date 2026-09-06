from robust_inventory_reconfiguration.product_risk_budget_benders import (
    PRODUCTWISE_BENDERS_COMPATIBLE,
    solve_prb_benders,
)
from robust_inventory_reconfiguration.exact_benchmark import (
    solve_exact_benchmark,
    solve_global_scenario_benchmark,
)

import pytest


pytest.importorskip("gurobipy")


def test_productwise_benders_compatibility_marker() -> None:
    assert PRODUCTWISE_BENDERS_COMPATIBLE is True


@pytest.mark.parametrize("gamma", [1, 2])
def test_prb_matches_literal_and_factorized_exact_on_tiny(tiny_instance, gamma) -> None:
    x0 = [[2.0, 1.0]]
    literal = solve_global_scenario_benchmark(tiny_instance, x0, 18.0, gamma, 0.05)
    factorized = solve_exact_benchmark(tiny_instance, x0, 18.0, gamma, 0.05)
    prb = solve_prb_benders(tiny_instance, x0, 18.0, gamma, 0.05)
    solutions = [literal.solution, factorized.solution, prb.solution]
    assert all(solution is not None for solution in solutions)
    assert max(solution.objective for solution in solutions) - min(
        solution.objective for solution in solutions
    ) <= 1e-6
    assert max(solution.robust_recourse_cost for solution in solutions) - min(
        solution.robust_recourse_cost for solution in solutions
    ) <= 1e-6
    assert prb.exact_certification_pass
    assert prb.global_risk_budget_coupling_pass


def test_prb_correctness_artifact_contract() -> None:
    import json
    from pathlib import Path

    path = Path("artifacts/prb_benders_correctness_summary.json")
    if not path.exists():
        pytest.skip("generated correctness artifact is not present")
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["mathematical_derivation"] == "PASS"
    assert summary["product_cut_validity_pass"]
    assert summary["product_cut_tightness_pass"]
    assert summary["gamma_composition_exactness_pass"]
    assert summary["global_risk_budget_coupling_pass"]
