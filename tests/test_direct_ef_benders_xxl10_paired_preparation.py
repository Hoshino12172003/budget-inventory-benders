from __future__ import annotations

import json

import pytest

from experiments import run_direct_scaling as direct_core
from experiments import run_ef_benders_scaling as ef_core
from scripts.audit_direct_ef_benders_xxl10_paired_preparation import build_audit
from scripts.audit_direct_scaling_xxl10_preparation import theoretical_direct_size
from scripts.audit_ef_benders_scaling_l10_preparation import theoretical_size
from scripts import run_direct_scaling_xxl10_paired_pilot as direct
from scripts import run_ef_benders_scaling_xxl10_paired_pilot as ef


def test_xxl10_static_sizes_are_exact_formula_counts():
    direct_size = theoretical_direct_size(36, 36, 16, 2)
    ef_size = theoretical_size(36, 36, 16, 2)
    assert (direct_size["variable_count"], direct_size["constraint_count"], direct_size["nonzero_count"]) == (14227589, 791070, 43069377)
    assert ef_size["ef_oracle"] == {"variables": 14225825, "constraints": 789881, "nonzeros": 42679929}
    assert direct_size["scenario_blocks"] == ef_size["product_local_scenario_blocks"] == 10672


def test_direct_and_ef_protocols_preserve_independent_authorization_history():
    direct_config = direct_core.load_config(direct.DEFAULT_CONFIG)
    ef_config = ef_core.load_config(ef.DEFAULT_CONFIG)
    direct.validate_protocol(direct_config)
    ef.validate_protocol(ef_config)
    assert direct_config["formal_run_authorized"] is True
    assert direct_config["recovery_control"]["authorized"] is False
    assert ef_config["formal_run_authorized"] is True
    assert direct_config["authorized_condition_ids"] == [direct.CONDITION_ID]
    assert ef_config["authorized_condition_ids"] == [ef.CONDITION_ID]
    assert direct_config["output_directory"] != ef_config["output_directory"]
    assert direct_config["resource_policy"]["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
    assert ef_config["resource_policy"]["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
    assert direct_config["resource_policy"]["minimum_available_memory_gib_by_size"] == {"XXL10": 16}
    assert ef_config["resource_policy"]["minimum_available_memory_gib_by_size"] == {"XXL10": 17}


def test_direct_dry_run_is_identity_complete_and_zero_optimization():
    dry = direct.build_dry_run()
    assert all(dry["identity_checks"].values())
    assert all(dry["model_identity_checks"].values())
    assert dry["next_attempt"] == "attempt-002"
    assert dry["attempt_001"]["classification"] == "WORKER_INNER_GIT_GATE_MISMATCH"
    assert dry["gates"]["canonical_absent"] is True
    assert dry["optimization_calls"] == 0


def test_ef_dry_run_reports_archived_pilot_without_optimization():
    dry = ef.build_dry_run()
    assert all(dry["identity_checks"].values())
    assert all(dry["model_identity_checks"].values())
    assert dry["condition"]["attempt_exists"] is True
    assert dry["condition"]["canonical_result_exists"] is True
    assert dry["gates"]["canonical_absent"] is False
    assert dry["optimization_calls"] == 0


def test_both_execution_paths_fail_closed_before_worker_launch(monkeypatch):
    monkeypatch.setattr(direct.runner, "run_monitored", lambda *_args: pytest.fail("Direct optimization must not launch"))
    monkeypatch.setattr(ef.runner, "run_condition", lambda *_args: pytest.fail("EF-BD optimization must not launch"))
    with pytest.raises(RuntimeError, match="RECOVERY_ATTEMPT_002_NOT_AUTHORIZED"):
        direct.execute()
    with pytest.raises(RuntimeError, match="PILOT_BLOCKED"):
        ef.execute()


def test_paired_audit_uses_same_frozen_input_and_historical_memory():
    audit = build_audit()
    assert audit["identity_checks"]["authorization_separate_and_closed"] is False
    assert all(
        value for key, value in audit["identity_checks"].items()
        if key != "authorization_separate_and_closed"
    )
    assert audit["frozen_instance"]["instance_hash"] == "81739c07edea3babcb62bbaf91ac6ac37eb13c3201052071c5610c4e8a328f94"
    assert audit["historical_memory"]["Direct_XL10"]["maximum_all_attempt_peak_gib"] == 8.289241790771484
    assert audit["historical_memory"]["EF_BD_XL10"]["maximum_certified_peak_gib"] == 4.7296600341796875
    assert audit["optimization_calls"] == 0


def test_scientific_and_algorithm_boundaries_are_frozen():
    direct_config = json.loads(direct.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    ef_config = json.loads(ef.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    assert direct_config["fixed_scientific_parameters"] == ef_config["fixed_scientific_parameters"]
    assert direct_config["solver_parameters"]["MIPGap"] == 0.0
    assert direct_config["solver_parameters"]["Method"] == 2
    assert ef_config["algorithm"]["global_theta_count"] == 1
    assert ef_config["algorithm"]["cuts_per_iteration_maximum"] == 1
    assert ef_config["algorithm"]["scenario_pruning"] is False
    assert ef_config["algorithm"]["product_multicut"] is False
