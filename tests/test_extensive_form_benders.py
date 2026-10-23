from __future__ import annotations

import os
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.extensive_form_benders import (
    ExtensiveFormRecourseOracle,
    solve_extensive_form_benders,
)


ROOT = Path(__file__).resolve().parents[1]


def test_ef_bd_source_keeps_the_declared_algorithm_boundary() -> None:
    source = (
        ROOT / "src/robust_inventory_reconfiguration/extensive_form_benders.py"
    ).read_text(encoding="utf-8")
    assert "product_risk_budget_benders" not in source
    assert "standard_benders" not in source
    assert "scenario_generation_oracle" not in source
    assert "GlobalRobustAdversarialSubproblem(" not in source
    assert "model.optimize()" in source
    assert "optimizer_calls_per_oracle\": 1" in source


@pytest.mark.skipif(
    os.environ.get("RUN_EF_BD_OPTIMIZATION_TESTS") != "1",
    reason="requires explicit authorization because it calls Gurobi optimize",
)
def test_tiny_fixed_x_oracle_matches_full_enumeration(tiny_instance) -> None:
    from robust_inventory_reconfiguration.enhanced_basic_benders import (
        EnhancedGlobalEnumeratedLPOracle,
    )

    x = [[5.0, 3.0]]
    ef = ExtensiveFormRecourseOracle(tiny_instance, 2)
    enumerated = EnhancedGlobalEnumeratedLPOracle(tiny_instance, 2)
    try:
        ef_result = ef.solve(x)
        enumerated_result = enumerated.solve(x)
    finally:
        ef.close()
        enumerated.close()
    assert abs(ef_result.value - enumerated_result.value) <= 1e-6
    assert ef_result.cut.dual_feasible is True
    assert ef_result.cut.strong_duality_error <= 1e-6
    assert abs(ef_result.cut.value_at(x) - ef_result.value) <= 1e-7


@pytest.mark.skipif(
    os.environ.get("RUN_EF_BD_OPTIMIZATION_TESTS") != "1",
    reason="requires explicit authorization because it calls Gurobi optimize",
)
def test_tiny_ef_bd_matches_literal_direct_and_basic(tmp_path: Path) -> None:
    from experiments.run_renault_vanilla_bd_pilot import (
        GlobalEnumeratedLPOracle,
        _tiny_inputs,
    )
    from robust_inventory_reconfiguration.exact_benchmark import (
        solve_global_scenario_benchmark,
    )
    import robust_inventory_reconfiguration.pure_benders as pure

    instance, x0, budget, gamma, lambda_r = _tiny_inputs()
    direct = solve_global_scenario_benchmark(instance, x0, budget, gamma, lambda_r)
    original = pure.GlobalRobustAdversarialSubproblem
    GlobalEnumeratedLPOracle.trace_path = tmp_path / "basic.jsonl"
    pure.GlobalRobustAdversarialSubproblem = GlobalEnumeratedLPOracle
    try:
        basic = pure.solve_pure_benders(
            instance, x0, budget, gamma, lambda_r, time_limit=120.0
        )
    finally:
        pure.GlobalRobustAdversarialSubproblem = original
    ef, diagnostics = solve_extensive_form_benders(
        instance,
        x0,
        budget,
        gamma,
        lambda_r,
        trace_path=tmp_path / "ef.jsonl",
        time_limit=120.0,
    )
    assert direct.status == "OPTIMAL"
    assert basic.status == "OPTIMAL"
    assert ef.status == "OPTIMAL"
    assert abs(direct.solution.objective - basic.solution.objective) <= 1e-4
    assert abs(direct.solution.objective - ef.solution.objective) <= 1e-4
    assert ef.exact_certification_pass is True
    assert ef.cut_validity_pass is True
    assert diagnostics["optimizer_calls_per_oracle"] == 1
    assert diagnostics["product_subproblem_decomposition"] is False
    assert diagnostics["scenario_pruning"] is False
