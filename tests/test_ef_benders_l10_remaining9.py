from pathlib import Path

from experiments import run_ef_benders_scaling as runner
from scripts import run_ef_benders_scaling_l10_remaining9 as batch_runner
from scripts.audit_ef_benders_scaling_l10_remaining9 import build_audit
from scripts.run_ef_benders_scaling_l10_remaining9 import DEFAULT_CONFIG, EXPECTED, build_dry_run, pilot_audit


def test_scope_and_resource_contract_are_exact():
    config = runner.load_config(DEFAULT_CONFIG)
    assert isinstance(config["formal_run_authorized"], bool)
    assert config["authorized_condition_ids"] == EXPECTED
    assert config["resource_policy"]["maximum_process_tree_memory_gib_by_size"] == {"L10": 7}
    assert config["resource_policy"]["minimum_available_memory_gib_by_size"] == {"L10": 11}
    assert config["resource_policy"]["minimum_system_available_memory_gib"] == 3
    assert config["solver_parameters"] == {"Threads": 2}


def test_pilot_archive_is_hash_identical_and_accepted():
    pilot = pilot_audit()
    assert all(pilot["checks"].values())
    assert pilot["result"]["algorithm_core_time"] == 66.63692490011454
    assert pilot["resource_monitor"]["peak_process_tree_memory_gib"] == 1.697723388671875


def test_dry_run_recognizes_completed_remaining_nine_without_optimization(monkeypatch):
    monkeypatch.setattr(
        batch_runner,
        "git_status_for_execution",
        lambda _output: {"head": "test", "clean_for_execution": True, "unexpected": []},
    )
    monkeypatch.setattr(batch_runner, "active_solver_workers", lambda: [])
    dry = build_dry_run(DEFAULT_CONFIG)
    assert dry["decision"] == "BLOCKED"
    assert dry["optimization_calls"] == 0
    assert len(dry["conditions"]) == 9
    assert all(row["identity_status"] == "PASS" for row in dry["conditions"])
    assert all(row["attempt_exists"] and row["canonical_result_exists"] for row in dry["conditions"])


def test_audit_reports_expected_paired_time_order_and_denominator(monkeypatch):
    monkeypatch.setattr(
        batch_runner,
        "git_status_for_execution",
        lambda _output: {"head": "test", "clean_for_execution": True, "unexpected": []},
    )
    monkeypatch.setattr(batch_runner, "active_solver_workers", lambda: [])
    audit = build_audit(DEFAULT_CONFIG)
    assert audit["status"] == "BLOCKED"
    assert audit["fixed_denominator"] == {"completed_pilot": 1, "authorized_remaining": 9, "total": 10}
    assert audit["paired_time_order_slowest_to_fastest"] == ["Direct", "EF-BD", "Aggregate-BD", "PRB-BD"]
    assert audit["optimization_calls"] == 0


def test_batch_runner_contains_fail_closed_policy():
    source = (Path(__file__).parents[1] / "scripts/run_ef_benders_scaling_l10_remaining9.py").read_text(encoding="utf-8")
    assert "INTEGRITY_FAILURE stops batch" in source
    assert "RESOURCE_OR_TIME_FAILURE" in source
    assert "runner.validate_execution_gate(config_path, condition_id)" in source
