from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from experiments import run_renault_sg_oracle_diagnostic as runner


ROOT = Path(__file__).resolve().parents[1]


def test_protocol_is_closed_and_exactly_scoped() -> None:
    config = runner.load_config()
    assert config["formal_run_authorized"] is False
    assert tuple(config["authorized_case_ids"]) == runner.CASES
    assert tuple(config["test_points"]) == ("final", "x0")
    assert config["unavailable_test_points"] == ["early_iteration", "middle_iteration"]
    assert config["start_modes"] == ["cold", "historical_warm"]
    assert config["fixed_scientific_parameters"] == {"Gamma": 2, "lambda_R": 0.05}
    assert config["solver"]["Threads"] == 1


def test_resource_contract_is_frozen() -> None:
    resource = runner.load_config()["resource_policy"]
    assert resource == {
        "execution": "sequential_single_process",
        "parallel_workers": 1,
        "minimum_available_memory_gib": 8,
        "maximum_process_tree_memory_gib": 4,
        "minimum_system_available_memory_gib": 3,
        "minimum_free_disk_gib": 20,
        "condition_time_limit_seconds": 300,
        "memory_monitor_interval_seconds": 0.25,
        "retry_policy": "no_automatic_retry",
    }


def test_only_real_persisted_test_points_are_selected() -> None:
    config = runner.load_config()
    _, frozen = runner.frozen_identities(config)
    for case in runner.CASES:
        loaded = runner.load_frozen_renault_case(case)
        runner.assert_frozen_identity(config, case, loaded)
        assert loaded["identity"] == frozen[case]
        final_x, final_source, final_warm = runner.load_point(case, "final")
        x0, x0_source, x0_warm = runner.load_point(case, "x0")
        trajectory = json.loads(
            (runner.final_root(case) / "iteration_trajectory.json").read_text(encoding="utf-8")
        )
        assert final_source.name == "first_stage_solution.json"
        assert x0_source.name == f"{case}.json"
        assert final_x != [] and x0 != []
        assert len(final_warm) <= 2 and len(x0_warm) <= 2
        assert all("x" not in row for row in trajectory)


def test_execute_fails_closed_before_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "dry_run", lambda *_: pytest.fail("closed gate must fail first"))
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        runner.execute(runner.CONFIG)


@pytest.mark.skipif(
    os.environ.get("RUN_SG_ORACLE_OPTIMIZATION_TESTS") != "1",
    reason="requires explicit authorization because it calls Gurobi optimize",
)
def test_tiny_sg_oracle_matches_full_eb_enumeration() -> None:
    from experiments.run_renault_vanilla_bd_pilot import _tiny_inputs
    from robust_inventory_reconfiguration.enhanced_basic_benders import (
        EnhancedGlobalEnumeratedLPOracle,
    )
    from robust_inventory_reconfiguration.scenario_generation_oracle import (
        ExactScenarioLPEvaluator,
    )
    from robust_inventory_reconfiguration.scenario_generation_single_cut import exact_separation

    instance, x0, _, gamma, _ = _tiny_inputs()
    eb_oracle = EnhancedGlobalEnumeratedLPOracle(instance, gamma)
    eb_oracle.model.Params.Threads = 1
    evaluator = ExactScenarioLPEvaluator(instance, gamma, x0, threads=1)
    try:
        eb = eb_oracle.solve(x0)
        sg = exact_separation(instance, x0, gamma, evaluator.evaluate)
    finally:
        evaluator.close()
        eb_oracle.close()
    assert abs(eb.value - sg.evaluation.value) <= 1e-4
    assert sg.evaluation.payload["dual_feasibility_max_violation"] <= 1e-7
    assert sg.evaluation.payload["strong_duality_residual"] <= 1e-4
    assert sg.evaluation.payload["cut_anchor_residual"] <= 1e-4
    assert sg.lp_solves + sg.safely_pruned_scenarios == sg.total_scenarios
