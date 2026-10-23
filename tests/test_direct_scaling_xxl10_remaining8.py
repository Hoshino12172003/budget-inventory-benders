from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import run_direct_scaling_xxl10_remaining8 as recovery


def _stable_live(monkeypatch):
    monkeypatch.setattr(recovery.base.psutil, "virtual_memory", lambda: type("Memory", (), {"available": 32 * 2**30})())
    monkeypatch.setattr(recovery.base.shutil, "disk_usage", lambda _path: type("Disk", (), {"free": 64 * 2**30})())
    monkeypatch.setattr(recovery.base, "git_status_for_execution", lambda _output: {"head": "test", "clean_for_execution": True, "unexpected": []})
    monkeypatch.setattr(recovery.base, "active_solver_workers", lambda **_kwargs: [])


def test_protocol_is_closed_scoped_and_authorized_history():
    config = recovery.runner.load_config(recovery.DEFAULT_CONFIG)
    recovery.validate_protocol(config)
    assert config["formal_run_authorized"] is True
    assert config["authorized_condition_ids"] == recovery.EXPECTED
    assert len(config["frozen_input_identity"]) == 8
    assert recovery.base.sha256(recovery.ROOT / "experiments/run_direct_scaling.py") == recovery.CORE_SHA256
    policy = config["resource_policy"]
    assert policy["minimum_available_memory_gib_by_size"] == {"XXL10": 16}
    assert policy["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
    assert policy["minimum_system_available_memory_gib"] == 3
    assert policy["minimum_free_disk_gib"] == 20
    assert policy["condition_time_limit_seconds"] == 900
    assert policy["memory_monitor_interval_seconds"] == 0.25
    assert policy["parallel_workers"] == 1
    assert policy["retry_policy"] == "no_automatic_retry"


def test_historical_seed22_is_byte_preserved_and_normally_time_limited():
    audit = recovery.historical_seed22_audit()
    assert all(audit["checks"].values())
    assert audit["historical_batch_status"] == "STOPPED_INTEGRITY_FAILURE"
    assert audit["posthoc_classification"] == "TIME_LIMIT_NO_INCUMBENT"
    assert audit["result"]["exact_certification"] is False
    assert all(audit["result"][key] is None for key in ("objective", "best_bound", "mip_gap"))
    assert audit["monitor"]["worker_return_code"] == 0
    assert audit["monitor"]["stop_reason"] is None
    assert audit["file_sha256"] == recovery.HISTORICAL_SHA256


def test_all_eight_frozen_and_paired_identities_pass(monkeypatch, tmp_path):
    _stable_live(monkeypatch)
    config = recovery.runner.load_config(recovery.DEFAULT_CONFIG)
    rows = [recovery.base.condition_audit(config, row, tmp_path) for row in recovery.runner.authorized_conditions(config)]
    assert len(rows) == 8
    assert all(all(row["identity_checks"].values()) for row in rows)
    assert all(all(row["paired_identity_checks"].values()) for row in rows)


def test_time_limit_variants_are_not_certified_success():
    monitor = {"worker_return_code": 0, "stop_reason": None}
    incumbent = {"solver_status": "TIME_LIMIT", "exact_certification": False, "certification_status": "NOT_ATTEMPTED", "objective": 2.0, "best_bound": 1.9, "mip_gap": 0.05}
    no_incumbent = {"solver_status": "TIME_LIMIT", "exact_certification": False, "certification_status": "NOT_ATTEMPTED", "objective": None, "best_bound": None, "mip_gap": None}
    partial = {**no_incumbent, "best_bound": 1.9}
    assert recovery.base.classify_completed_result(incumbent, monitor) == "TIME_LIMIT_WITH_INCUMBENT"
    assert recovery.base.classify_completed_result(no_incumbent, monitor) == "TIME_LIMIT_NO_INCUMBENT"
    assert recovery.base.classify_completed_result(partial, monitor) == "INTEGRITY_FAILURE"
    assert recovery.base.classify_completed_result(no_incumbent, {"worker_return_code": 1, "stop_reason": None}) == "INTEGRITY_FAILURE"


def test_attempt_and_canonical_are_protected(tmp_path):
    config = recovery.runner.load_config(recovery.DEFAULT_CONFIG)
    condition = recovery.runner.authorized_conditions(config)[0]
    clean = recovery.base.condition_audit(config, condition, tmp_path)
    assert clean["attempt_state_valid"] and clean["canonical_absent"]
    (tmp_path / "worker_logs" / condition["condition_id"] / "attempt-001").mkdir(parents=True)
    assert recovery.base.condition_audit(config, condition, tmp_path)["attempt_state_valid"] is False
    (tmp_path / "runs" / condition["condition_id"]).mkdir(parents=True)
    assert recovery.base.condition_audit(config, condition, tmp_path)["canonical_absent"] is False


def test_parent_launches_recovery_worker(monkeypatch, tmp_path):
    config = recovery.runner.load_config(recovery.DEFAULT_CONFIG)
    condition = recovery.runner.authorized_conditions(config)[0]
    state = {"pass": True, "resource_gate": {"optimization_calls": 0}}
    monkeypatch.setattr(recovery, "live_gates", lambda *_args, **_kwargs: state)

    def fake_run(_config_path, _config, _condition, _output):
        assert Path(recovery.runner.__file__).resolve() == Path(recovery.__file__).resolve()
        assert recovery.runner.validate_execution_gate(None, None, None) == state["resource_gate"]

    monkeypatch.setattr(recovery.runner, "run_monitored", fake_run)
    recovery.run_one(recovery.DEFAULT_CONFIG, config, condition, tmp_path)


def test_completed_batch_cannot_launch_duplicate_worker(monkeypatch):
    monkeypatch.setattr(recovery, "run_one", lambda *_args: pytest.fail("optimization must not launch"))
    with pytest.raises(RuntimeError, match="DIRECT_XXL10_REMAINING8_BLOCKED"):
        recovery.execute_batch()


def test_independent_subprocess_preflight_is_zero_optimization():
    completed = subprocess.run(
        [sys.executable, str(Path(recovery.__file__).resolve()), "--worker-preflight", recovery.EXPECTED[0], "--config", str(recovery.DEFAULT_CONFIG)],
        cwd=recovery.ROOT, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gates"]["git"] is True
    assert payload["gates"]["historical_seed22"] is True
    assert payload["optimization_calls"] == 0
