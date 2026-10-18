from __future__ import annotations

import pytest

from experiments import run_direct_scaling as runner
from scripts.audit_direct_scaling_xxl10_preparation import CONFIG, DIRECT, build_audit, theoretical_direct_size


def test_model_size_formula_reproduces_actual_l10_xl10_counts() -> None:
    assert theoretical_direct_size(25, 24, 12, 2)["variable_count"] == 2258462
    assert theoretical_direct_size(25, 24, 12, 2)["constraint_count"] == 184929
    assert theoretical_direct_size(25, 24, 12, 2)["nonzero_count"] == 6866733
    assert theoretical_direct_size(30, 30, 14, 2)["variable_count"] == 6075177
    assert theoretical_direct_size(30, 30, 14, 2)["constraint_count"] == 405479
    assert theoretical_direct_size(30, 30, 14, 2)["nonzero_count"] == 18422892


def test_xxl10_static_counts_are_formula_based_not_measured() -> None:
    size = theoretical_direct_size(36, 36, 16, 2)
    assert size["scenario_patterns_per_product"] == 667
    assert size["scenario_blocks"] == 10672
    assert size["variable_count"] == 14227589
    assert size["binary_variable_count"] == 36
    assert size["constraint_count"] == 791070
    assert size["nonzero_count"] == 43069377
    assert "NOT_A_GUROBI_BUILD" in size["evidence_class"]


def test_candidate_is_closed_single_condition_and_preserves_parameters() -> None:
    candidate = runner.load_config(CONFIG)
    source = runner.load_config(runner.ROOT / "experiments/configs/formal/direct_scaling_xl10_low_memory_candidate_v1.yaml")
    assert candidate["formal_run_authorized"] is False
    assert [row["condition_id"] for row in runner.authorized_conditions(candidate)] == ["DIRECT_XXL10_S20260921"]
    assert candidate["fixed_scientific_parameters"] == source["fixed_scientific_parameters"]
    assert candidate["solver_profile"] == source["solver_profile"]
    assert candidate["solver_parameters"] == source["solver_parameters"]
    policy = candidate["resource_policy"]
    assert policy["maximum_process_tree_memory_gib_by_size"]["XXL10"] == 13
    assert policy["minimum_available_memory_gib_by_size"]["XXL10"] == 16
    assert policy["minimum_system_available_memory_gib"] == 3
    assert policy["minimum_free_disk_gib"] == 20
    assert policy["condition_time_limit_seconds"] == 900
    assert policy["memory_monitor_interval_seconds"] == 0.25
    assert policy["parallel_workers"] == 1


def test_all_frozen_xxl10_inputs_and_pairing_exception_pass() -> None:
    audit = build_audit()
    assert len(audit["xxl10_inputs"]) == 10
    assert all(row["identity_status"] == "PASS" for row in audit["xxl10_inputs"])
    assert audit["pure_xxl10_seed20260925"]["status"] == "EXCLUDED_FROM_VALID_FOUR_METHOD_PAIRING"
    assert audit["frozen_l10_xl10_evidence"]["status"] == "PASS"
    assert audit["next_attempt"] == "attempt-001"


def test_execution_gate_fails_closed_before_environment_probe(monkeypatch) -> None:
    config = runner.load_config(CONFIG)
    condition = runner.authorized_conditions(config)[0]
    monkeypatch.setattr(runner, "current_environment", lambda: pytest.fail("environment probe should not run"))
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        runner.validate_execution_gate(config, condition, DIRECT)
