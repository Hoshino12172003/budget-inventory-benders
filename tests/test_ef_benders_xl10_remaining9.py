import json
from pathlib import Path

import pytest

from experiments import run_ef_benders_scaling as ef_runner
from scripts import run_ef_benders_scaling_xl10_remaining9 as batch
from scripts.audit_ef_benders_scaling_xl10_remaining9 import build_audit


def _stable_dry_run(monkeypatch):
    original = ef_runner.dry_run

    def wrapped(config_path, condition_id):
        row = original(config_path, condition_id)
        row["resource_gate"]["available_memory_gib"] = 64.0
        row["resource_gate"]["free_disk_gib"] = 64.0
        return row

    monkeypatch.setattr(batch.runner, "dry_run", wrapped)
    monkeypatch.setattr(
        batch,
        "git_status_for_execution",
        lambda _output: {"head": "test", "clean_for_execution": True, "unexpected": []},
    )
    monkeypatch.setattr(batch, "active_solver_workers", lambda: [])


def test_protocol_scope_resources_and_authorization_are_frozen():
    config = ef_runner.load_config(batch.DEFAULT_CONFIG)
    batch.validate_protocol(config)
    assert config["formal_run_authorized"] is False
    assert config["authorized_condition_ids"] == batch.EXPECTED
    assert config["resource_policy"]["maximum_process_tree_memory_gib_by_size"] == {"XL10": 8}
    assert config["resource_policy"]["minimum_available_memory_gib_by_size"] == {"XL10": 12}
    assert config["resource_policy"]["minimum_system_available_memory_gib"] == 3
    assert config["resource_policy"]["condition_time_limit_seconds"] == 900
    assert config["solver_parameters"] == {"Threads": 2}


def test_completed_pilot_is_byte_identical_and_certified():
    pilot = batch.pilot_audit()
    assert all(pilot["checks"].values())
    assert pilot["result"]["final_objective"] == 3153985.8116781656
    assert pilot["result"]["algorithm_core_time"] == 162.4874189000111
    assert pilot["resource_monitor"]["peak_process_tree_memory_gib"] == 4.7296600341796875


def test_dry_run_validates_nine_absent_attempts_without_optimization(monkeypatch):
    _stable_dry_run(monkeypatch)
    dry = batch.build_dry_run()
    assert dry["decision"] == "READY_FOR_AUTHORIZATION"
    assert dry["optimization_calls"] == 0
    assert len(dry["conditions"]) == 9
    assert all(row["identity_status"] == "PASS" for row in dry["conditions"])
    assert all(not row["attempt_exists"] and not row["canonical_result_exists"] for row in dry["conditions"])
    assert all(row["expected_attempt"] == "attempt-001" for row in dry["conditions"])


def test_readiness_audit_is_closed_and_zero_optimization(monkeypatch):
    _stable_dry_run(monkeypatch)
    audit = build_audit()
    assert audit["status"] == "READY_FOR_AUTHORIZATION"
    assert audit["checks"]["authorization_closed"] is True
    assert audit["optimization_calls"] == 0
    assert audit["fixed_denominator"] == {"completed_pilot": 1, "remaining": 9, "total_xl10": 10}


def test_execute_refuses_before_worker_launch(monkeypatch):
    monkeypatch.setattr(
        batch.runner,
        "run_condition",
        lambda *_args, **_kwargs: pytest.fail("optimization launcher must not be called"),
    )
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        batch.execute_batch()


def test_failure_classification_continues_only_known_stops_after_worker_exit():
    config = ef_runner.load_config(batch.DEFAULT_CONFIG)
    resource = {"worker_return_code": 1, "stop_reason": "RESOURCE_PROCESS_CAP"}
    assert batch.classify_monitor(config, batch.EXPECTED[0], resource, workers=[]) == "RESOURCE_OR_TIME_FAILURE"
    assert batch.classify_monitor(config, batch.EXPECTED[0], resource, workers=[{"pid": 1}]) == "INTEGRITY_FAILURE"
    unknown = {"worker_return_code": 1, "stop_reason": None}
    assert batch.classify_monitor(config, batch.EXPECTED[0], unknown, workers=[]) == "INTEGRITY_FAILURE"


def test_atomic_report_write_replaces_complete_json(tmp_path):
    target = tmp_path / "report.json"
    batch.write_json(target, {"status": "RUNNING"})
    batch.write_json(target, {"status": "COMPLETE"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "COMPLETE"}
    assert not list(tmp_path.glob(".tmp-*"))


def test_batch_source_rechecks_every_condition_and_stops_integrity_failure():
    source = (Path(__file__).parents[1] / "scripts/run_ef_benders_scaling_xl10_remaining9.py").read_text(encoding="utf-8")
    assert "runner.validate_execution_gate(config_path, condition_id)" in source
    assert "INTEGRITY_FAILURE stops batch" in source
    assert "RESOURCE_OR_TIME_FAILURE" in source
    assert "attempt-001" in source
