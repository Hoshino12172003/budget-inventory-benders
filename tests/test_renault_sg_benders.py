from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from experiments import run_renault_sg_benders as runner


ROOT = Path(__file__).resolve().parents[1]


def test_protocol_is_closed_after_execution_and_exactly_scoped() -> None:
    config = runner.load_config()
    assert config["formal_run_authorized"] is False
    assert tuple(config["case_ids"]) == runner.CASES
    assert tuple(config["authorized_condition_ids"]) == runner.CONDITIONS
    assert config["fixed_scientific_parameters"] == {"Gamma": 2, "lambda_R": 0.05}
    assert config["algorithm"]["global_theta_count"] == 1
    assert config["algorithm"]["cuts_per_iteration_maximum"] == 1
    assert config["algorithm"]["product_risk_budget_decomposition"] is False
    assert config["algorithm"]["product_multicut"] is False
    assert config["algorithm"]["compact_global_robust_milp_oracle"] is False


def test_resource_contract_is_frozen() -> None:
    assert runner.load_config()["resource_policy"] == {
        "execution": "sequential_single_process",
        "parallel_workers": 1,
        "minimum_available_memory_gib": 8,
        "maximum_process_tree_memory_gib": 4,
        "minimum_system_available_memory_gib": 3,
        "minimum_free_disk_gib": 20,
        "condition_time_limit_seconds": 300,
        "memory_monitor_interval_seconds": 0.25,
        "fail_closed": True,
        "retry_policy": "no_automatic_retry",
    }


def test_all_frozen_identities_and_direct_references_pass() -> None:
    config = runner.load_config()
    rows = [runner.condition_identity(config, case) for case in runner.CASES]
    assert all(row["status"] == "PASS" for row in rows)
    assert all(row["total_scenarios"] == 4657 for row in rows)


def test_execute_is_fail_closed_when_authorization_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = runner.load_config()
    config["formal_run_authorized"] = False
    monkeypatch.setattr(runner, "load_config", lambda *_: config)
    monkeypatch.setattr(
        runner, "build_dry_run", lambda *_: pytest.fail("authorization must fail first")
    )
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        runner.execute_batch()


def test_sg_implementation_has_no_forbidden_algorithm_import() -> None:
    source = (
        ROOT / "src/robust_inventory_reconfiguration/scenario_generation_benders.py"
    ).read_text(encoding="utf-8")
    assert "standard_benders" not in source
    assert "product_risk_budget_benders" not in source
    assert "GlobalRobustAdversarialSubproblem(" not in source
    assert "ScenarioGenerationGlobalOracle(" in source
    assert "maximum_cuts_per_iteration\": 1" in source


def test_archived_results_cover_eight_cases_and_preserve_prb_failure() -> None:
    audit = json.loads(
        (ROOT / "artifacts/renault_sg_bd_acceptance_audit.json").read_text(encoding="utf-8")
    )
    assert audit["status"] == "PASS"
    assert audit["expected"] == 8
    assert audit["exact_certified"] == 8
    assert audit["objective_consistent_with_direct"] == 8
    assert audit["prb_210330_strict_pairing_eligible"] is False
    assert all(all(checks.values()) for checks in audit["checks"].values())


@pytest.mark.skipif(
    os.environ.get("RUN_SG_BD_OPTIMIZATION_TESTS") != "1",
    reason="requires explicit authorization because it calls Gurobi optimize",
)
def test_tiny_sg_bd_matches_direct_and_persists_real_iterates(tmp_path: Path) -> None:
    from experiments.run_renault_vanilla_bd_pilot import _tiny_inputs
    from robust_inventory_reconfiguration.exact_benchmark import solve_global_scenario_benchmark
    from robust_inventory_reconfiguration.scenario_generation_benders import (
        solve_scenario_generation_benders,
    )

    instance, x0, budget, gamma, lambda_r = _tiny_inputs()
    direct = solve_global_scenario_benchmark(instance, x0, budget, gamma, lambda_r)
    trace_path = tmp_path / "oracle_trace.jsonl"
    sg, diagnostics = solve_scenario_generation_benders(
        instance,
        x0,
        budget,
        gamma,
        lambda_r,
        trace_path=trace_path,
        time_limit=120.0,
    )
    traces = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert direct.status == "OPTIMAL"
    assert sg.status == "OPTIMAL"
    assert abs(direct.solution.objective - sg.solution.objective) <= 1e-4
    assert sg.cut_validity_pass is True
    assert len(traces) == len(sg.iterations) + 1
    assert all(trace["first_stage_x"] for trace in traces)
    assert all(
        trace["exact_lp_solves"] + trace["safely_pruned_scenarios"]
        == trace["total_scenarios"]
        for trace in traces
    )
    assert diagnostics["single_global_theta"] is True
    assert diagnostics["maximum_cuts_per_iteration"] == 1
    assert diagnostics["product_risk_budget_decomposition"] is False
    assert diagnostics["product_multicut"] is False
    assert diagnostics["compact_global_robust_milp_oracle"] is False
