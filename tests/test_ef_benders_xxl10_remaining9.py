import json
from pathlib import Path

import pytest

from experiments import run_ef_benders_scaling as ef_runner
from scripts import run_ef_benders_scaling_xxl10_remaining9 as batch
from scripts.audit_ef_benders_scaling_xxl10_remaining9 import build_audit


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
    monkeypatch.setattr(batch, "active_paired_solver_workers", lambda: [])


def test_protocol_scope_resources_and_authorization_are_frozen():
    config = ef_runner.load_config(batch.DEFAULT_CONFIG)
    batch.validate_protocol(config)
    assert config["formal_run_authorized"] is True
    assert config["authorized_condition_ids"] == batch.EXPECTED
    assert config["resource_policy"]["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
    assert config["resource_policy"]["minimum_available_memory_gib_by_size"] == {"XXL10": 17}
    assert config["resource_policy"]["minimum_system_available_memory_gib"] == 3
    assert config["resource_policy"]["condition_time_limit_seconds"] == 900
    assert config["solver_parameters"] == {"Threads": 2}


def test_completed_pilot_is_byte_identical_and_certified():
    pilot = batch.pilot_audit()
    assert all(pilot["checks"].values())
    assert pilot["result"]["final_objective"] == 4754158.5907900315
    assert pilot["result"]["algorithm_core_time"] == 287.82764680008404
    assert pilot["resource_monitor"]["elapsed_seconds"] == 373.4123421001714
    assert pilot["resource_monitor"]["peak_process_tree_memory_gib"] == 10.958301544189453


def test_dry_run_protects_nine_archived_attempts_without_optimization(monkeypatch):
    _stable_dry_run(monkeypatch)
    dry = batch.build_dry_run()
    assert dry["decision"] == "BLOCKED"
    assert dry["optimization_calls"] == 0
    assert len(dry["conditions"]) == 9
    assert all(row["identity_status"] == "PASS" for row in dry["conditions"])
    assert all(row["attempt_exists"] and row["canonical_result_exists"] for row in dry["conditions"])
    assert all(row["expected_attempt"] == "attempt-001" for row in dry["conditions"])
    seed_20260925 = next(row for row in dry["conditions"] if row["condition"]["seed"] == 20260925)
    assert seed_20260925["paired_instance_identity"]["PURE_BENDERS"] is None


def test_readiness_audit_blocks_rerun_and_records_zero_optimization(monkeypatch):
    _stable_dry_run(monkeypatch)
    audit = build_audit()
    assert audit["status"] == "BLOCKED"
    assert audit["checks"]["authorization_closed"] is False
    assert audit["checks"]["all_nine_attempts_absent"] is False
    assert audit["checks"]["all_nine_canonical_absent"] is False
    assert audit["optimization_calls"] == 0
    assert audit["fixed_denominator"] == {"completed_pilot": 1, "remaining": 9, "total_xxl10": 10}


def test_execute_refuses_before_worker_launch(monkeypatch, tmp_path):
    config = ef_runner.load_config(batch.DEFAULT_CONFIG)
    config["formal_run_authorized"] = False
    closed = tmp_path / "closed.json"
    closed.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(
        batch.runner,
        "run_condition",
        lambda *_args, **_kwargs: pytest.fail("optimization launcher must not be called"),
    )
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        batch.execute_batch(closed)


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


def test_batch_source_rechecks_each_condition_and_stops_integrity_failure():
    source = (Path(__file__).parents[1] / "scripts/run_ef_benders_scaling_xxl10_remaining9.py").read_text(encoding="utf-8")
    assert "runner.validate_execution_gate(config_path, condition_id)" in source
    assert "INTEGRITY_FAILURE stops batch" in source
    assert "RESOURCE_OR_TIME_FAILURE" in source
    assert "attempt-001" in source
