from __future__ import annotations

import itertools
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments import run_renault_enhanced_basic_benders as runner
from robust_inventory_reconfiguration.enhanced_basic_benders import (
    build_scenario_rhs_plans,
    enumerate_global_patterns,
    solve_enhanced_basic_benders,
)
from scripts.summarize_renault_enhanced_basic_benders import build_rows


ROOT = Path(__file__).resolve().parents[1]


def test_global_pattern_plan_is_complete_without_pruning() -> None:
    patterns = enumerate_global_patterns(3, 2, 2)
    expected = tuple(
        pattern
        for size in range(3)
        for pattern in itertools.combinations(
            tuple((r, j) for r in range(3) for j in range(2)), size
        )
    )
    assert patterns == expected
    assert len(patterns) == 22
    assert len(set(patterns)) == len(patterns)


def test_precomputed_rhs_plan_matches_global_scenario_definition() -> None:
    instance = SimpleNamespace(
        num_regions=2,
        num_products=2,
        base_demand=[[4.0, 3.0], [2.0, 1.0]],
        demand_deviation=[[1.0, 2.0], [3.0, 4.0]],
        service_level=[0.5, 0.75],
    )
    plans = build_scenario_rhs_plans(instance, 1)
    shocked = next(plan for plan in plans if plan.pattern == ((1, 0),))
    assert shocked.demand_rhs == (4.0, 3.0, 5.0, 1.0)
    assert shocked.service_rhs == (4.5, 1.0)


def test_protocol_is_closed_and_exactly_scoped() -> None:
    config = runner.load_config()
    assert config["formal_run_authorized"] is False
    assert tuple(config["case_ids"]) == runner.EXPECTED_CASES
    assert tuple(config["authorized_condition_ids"]) == runner.EXPECTED_CONDITIONS
    assert config["fixed_scientific_parameters"] == {"Gamma": 2, "lambda_R": 0.05}
    assert config["algorithm"]["global_theta_count"] == 1
    assert config["algorithm"]["cuts_per_iteration_maximum"] == 1
    assert config["algorithm"]["candidate_pruning"] is False
    assert config["algorithm"]["product_risk_budget_decomposition"] is False
    assert config["algorithm"]["product_multicut"] is False
    assert config["algorithm"]["compact_global_robust_milp_oracle"] is False


def test_resource_contract_matches_basic_bd_development_protocol() -> None:
    resource = runner.load_config()["resource_policy"]
    assert resource["condition_time_limit_seconds"] == 300
    assert resource["maximum_process_tree_memory_gib"] == 4
    assert resource["minimum_available_memory_gib"] == 8
    assert resource["minimum_system_available_memory_gib"] == 3
    assert resource["minimum_free_disk_gib"] == 20
    assert resource["memory_monitor_interval_seconds"] == 0.25
    assert resource["parallel_workers"] == 1
    assert resource["retry_policy"] == "no_automatic_retry"


def test_all_eight_frozen_identities_and_scenario_counts_pass() -> None:
    config = runner.load_config()
    rows = [runner.condition_identity(config, case_id) for case_id in runner.EXPECTED_CASES]
    assert all(row["status"] == "PASS" for row in rows)
    assert all(row["scenario_count"] == 4657 for row in rows)
    assert all(row["Gamma"] == 2 for row in rows)
    assert all(row["lambda_R"] == 0.05 for row in rows)


def test_dry_run_makes_no_optimization_calls_and_reports_archived_attempts() -> None:
    dry = runner.build_dry_run()
    assert dry["optimization_calls"] == 0
    assert dry["formal_run_authorized"] is False
    assert len(dry["conditions"]) == 8
    assert all(row["attempt_exists"] for row in dry["conditions"])
    assert all(row["canonical_exists"] for row in dry["conditions"])


def test_execute_fails_closed_before_any_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner,
        "build_dry_run",
        lambda *_: pytest.fail("dry-run must not follow a closed authorization gate"),
    )
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        runner.execute_batch()


def test_implementation_has_no_forbidden_oracle_or_product_decomposition_dependency() -> None:
    source = (
        ROOT / "src/robust_inventory_reconfiguration/enhanced_basic_benders.py"
    ).read_text(encoding="utf-8")
    oracle_source = source.split("class EnhancedGlobalEnumeratedLPOracle", 1)[1].split(
        "def solve_enhanced_basic_benders", 1
    )[0]
    assert "from .standard_benders import" not in source
    assert "from .product_risk_budget_benders import" not in source
    assert "GlobalRobustAdversarialSubproblem(" not in oracle_source
    assert "candidate_pruning\": False" in source
    assert "setAttr(GRB.Attr.RHS" in source


def test_comparison_uses_archived_eb_sources_and_excludes_prb_210330() -> None:
    rows = build_rows()
    assert len(rows) == 48
    eb_rows = [row for row in rows if row["method"] == "EB-BD"]
    assert len(eb_rows) == 8
    assert all(row["objective"] is not None for row in eb_rows)
    assert all(row["exact_certification"] is True for row in eb_rows)
    prb_210330 = next(
        row for row in rows if row["case"] == "210330" and row["method"] == "PRB-BD"
    )
    assert prb_210330["pairing_eligible"] is False
    assert prb_210330["pairing_exclusion_reason"] == (
        "PRB_INTERNAL_GLOBAL_COUPLING_CERTIFICATION_FAILED"
    )


@pytest.mark.skipif(
    os.environ.get("RUN_EB_BD_OPTIMIZATION_TESTS") != "1",
    reason="requires explicit authorization because it calls Gurobi optimize",
)
def test_tiny_eb_bd_matches_direct_exactly_when_explicitly_enabled(tmp_path: Path) -> None:
    from experiments.run_renault_vanilla_bd_pilot import _tiny_inputs
    from robust_inventory_reconfiguration.exact_benchmark import solve_global_scenario_benchmark

    instance, x0, budget, gamma, lambda_r = _tiny_inputs()
    direct = solve_global_scenario_benchmark(instance, x0, budget, gamma, lambda_r)
    eb, diagnostics = solve_enhanced_basic_benders(
        instance,
        x0,
        budget,
        gamma,
        lambda_r,
        trace_path=tmp_path / "oracle_trace.jsonl",
        time_limit=120.0,
    )
    assert direct.status == "OPTIMAL"
    assert eb.status == "OPTIMAL"
    assert abs(direct.solution.objective - eb.solution.objective) <= 1e-4
    assert eb.cut_validity_pass is True
    assert diagnostics["candidate_pruning"] is False
    assert diagnostics["maximum_cuts_per_iteration"] == 1
