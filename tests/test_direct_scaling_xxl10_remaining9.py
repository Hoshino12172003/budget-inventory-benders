from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import run_direct_scaling_xxl10_remaining9 as batch


def _stable_live(monkeypatch):
    monkeypatch.setattr(batch.psutil, "virtual_memory", lambda: type("Memory", (), {"available": 32 * 2**30})())
    monkeypatch.setattr(batch.shutil, "disk_usage", lambda _path: type("Disk", (), {"free": 64 * 2**30})())
    monkeypatch.setattr(batch, "git_status_for_execution", lambda _output: {"head": "test", "clean_for_execution": True, "unexpected": []})
    monkeypatch.setattr(batch, "active_solver_workers", lambda **_kwargs: [])


def test_protocol_is_closed_scoped_and_byte_equivalent_to_pilot_settings():
    config = batch.runner.load_config(batch.DEFAULT_CONFIG)
    pilot = batch.runner.load_config(batch.PILOT_CONFIG)
    batch.validate_protocol(config)
    assert config["formal_run_authorized"] is True
    assert config["authorized_condition_ids"] == batch.EXPECTED
    assert config["fixed_scientific_parameters"] == pilot["fixed_scientific_parameters"]
    assert config["solver_parameters"] == pilot["solver_parameters"]
    assert config["frozen_model_files"] == pilot["frozen_model_files"]
    assert batch.sha256(batch.ROOT / "experiments/run_direct_scaling.py") == batch.CORE_SHA256
    policy = config["resource_policy"]
    assert policy["minimum_available_memory_gib_by_size"] == {"XXL10": 16}
    assert policy["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
    assert policy["minimum_system_available_memory_gib"] == 3
    assert policy["minimum_free_disk_gib"] == 20
    assert policy["condition_time_limit_seconds"] == 900
    assert policy["memory_monitor_interval_seconds"] == 0.25
    assert policy["parallel_workers"] == 1
    assert policy["retry_policy"] == "no_automatic_retry"


def test_pilot_is_preserved_as_time_limited_not_certified():
    pilot = batch.pilot_audit()
    assert all(pilot["checks"].values())
    assert pilot["result"]["solver_status"] == "TIME_LIMIT"
    assert pilot["result"]["exact_certification"] is False
    assert pilot["result"]["certification_status"] == "NOT_ATTEMPTED"
    assert pilot["result"]["objective"] == 4754158.590790098
    assert pilot["result"]["best_bound"] == 4751359.2883982835
    assert pilot["result"]["mip_gap"] == 0.0005888113192599344
    assert pilot["attempt_002_monitor"]["peak_process_tree_memory_gib"] == 10.683246612548828
    assert pilot["file_sha256"]["worker_logs/DIRECT_XXL10_S20260921/attempt-002/resource_monitor.json"] == "3fdd9d36f51aef716769c05be22abcf970ab35b9f6aeb3553bcf254a7f0f1c53"


def test_all_nine_frozen_and_paired_identities_pass(monkeypatch, tmp_path):
    _stable_live(monkeypatch)
    config = batch.runner.load_config(batch.DEFAULT_CONFIG)
    rows = [batch.condition_audit(config, row, tmp_path) for row in batch.runner.authorized_conditions(config)]
    assert len(rows) == 9
    assert all(all(row["identity_checks"].values()) for row in rows)
    assert all(all(row["paired_identity_checks"].values()) for row in rows)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"solver_status": "OPTIMAL", "exact_certification": True, "certification_status": "PASS"}, "CERTIFIED_SUCCESS"),
        ({"solver_status": "TIME_LIMIT", "exact_certification": False, "certification_status": "NOT_ATTEMPTED", "objective": 2.0, "best_bound": 1.9, "mip_gap": 0.05}, "TIME_LIMIT_WITH_INCUMBENT"),
        ({"solver_status": "TIME_LIMIT", "exact_certification": False, "certification_status": "NOT_ATTEMPTED", "objective": None, "best_bound": None, "mip_gap": None}, "TIME_LIMIT_NO_INCUMBENT"),
        ({"solver_status": "MEMORY_LIMIT", "exact_certification": False}, "RESOURCE_LIMIT"),
        ({"solver_status": "OPTIMAL", "exact_certification": False, "certification_status": "OBJECTIVE_RESIDUAL_FAILURE"}, "INTEGRITY_FAILURE"),
        ({"solver_status": "OTHER", "exact_certification": False}, "INTEGRITY_FAILURE"),
    ],
)
def test_completed_result_classification_is_fail_closed(result, expected):
    monitor = {"worker_return_code": 0, "stop_reason": None}
    assert batch.classify_completed_result(result, monitor) == expected


def test_time_limit_requires_consistent_progress_fields_and_clean_worker():
    result = {"solver_status": "TIME_LIMIT", "exact_certification": False, "certification_status": "NOT_ATTEMPTED", "objective": 2.0, "best_bound": None, "mip_gap": None}
    assert batch.classify_completed_result(result, {"worker_return_code": 0, "stop_reason": None}) == "INTEGRITY_FAILURE"
    result.update({"best_bound": 1.0, "mip_gap": 0.5})
    assert batch.classify_completed_result(result, {"worker_return_code": 1, "stop_reason": None}) == "INTEGRITY_FAILURE"


def test_resource_stop_and_unknown_failure_are_distinct(tmp_path):
    config = batch.runner.load_config(batch.DEFAULT_CONFIG)
    condition = batch.runner.authorized_conditions(config)[0]
    attempt = tmp_path / "worker_logs" / condition["condition_id"] / "attempt-001"
    attempt.mkdir(parents=True)
    monitor = attempt / "resource_monitor.json"
    monitor.write_text(json.dumps({"worker_return_code": 1, "stop_reason": "RESOURCE_PROCESS_CAP"}), encoding="utf-8")
    assert batch.classify_condition(config, condition, tmp_path)["classification"] == "RESOURCE_LIMIT"
    monitor.write_text(json.dumps({"worker_return_code": 1, "stop_reason": None}), encoding="utf-8")
    assert batch.classify_condition(config, condition, tmp_path)["classification"] == "INTEGRITY_FAILURE"


def test_attempt_and_canonical_are_protected(tmp_path):
    config = batch.runner.load_config(batch.DEFAULT_CONFIG)
    condition = batch.runner.authorized_conditions(config)[0]
    clean = batch.condition_audit(config, condition, tmp_path)
    assert clean["attempt_state_valid"] and clean["canonical_absent"]
    (tmp_path / "worker_logs" / condition["condition_id"] / "attempt-001").mkdir(parents=True)
    assert batch.condition_audit(config, condition, tmp_path)["attempt_state_valid"] is False
    (tmp_path / "runs" / condition["condition_id"]).mkdir(parents=True)
    assert batch.condition_audit(config, condition, tmp_path)["canonical_absent"] is False


def test_git_allowlist_rejects_code_config_and_unknown_files():
    output = batch.ROOT / "experiments/results/direct_scaling_xxl10_remaining9_v1"
    allowed = [
        "?? experiments/results/direct_scaling_xxl10_remaining9_v1/batch_reports/status.json",
        "?? experiments/results/direct_scaling_xxl10_paired_pilot_v1/runs/x/result.json",
        "?? artifacts/direct_scaling_xxl10_remaining9_readiness_audit.json",
    ]
    assert batch.unexpected_git_entries(allowed, output) == []
    rejected = [
        " M experiments/run_direct_scaling.py",
        " M experiments/configs/development/direct_scaling_xxl10_remaining9_v1.yaml",
        "?? artifacts/direct_scaling_xxl10_remaining9_readiness_audit.json.extra",
        "?? unknown.txt",
    ]
    assert batch.unexpected_git_entries(rejected, output) == rejected


def test_parent_launches_wrapper_worker_not_core_worker(monkeypatch, tmp_path):
    config = batch.runner.load_config(batch.DEFAULT_CONFIG)
    condition = batch.runner.authorized_conditions(config)[0]
    state = {"pass": True, "resource_gate": {"optimization_calls": 0}}
    monkeypatch.setattr(batch, "live_gates", lambda *_args, **_kwargs: state)

    def fake_run(_config_path, _config, _condition, _output):
        assert Path(batch.runner.__file__).resolve() == Path(batch.__file__).resolve()
        assert batch.runner.validate_execution_gate(None, None, None) == state["resource_gate"]

    monkeypatch.setattr(batch.runner, "run_monitored", fake_run)
    batch.run_one(batch.DEFAULT_CONFIG, config, condition, tmp_path)


def test_completed_batch_cannot_launch_a_duplicate_worker(monkeypatch):
    monkeypatch.setattr(batch, "run_one", lambda *_args: pytest.fail("optimization must not launch"))
    with pytest.raises(RuntimeError, match="DIRECT_XXL10_REMAINING9_BLOCKED"):
        batch.execute_batch()


def test_independent_subprocess_worker_preflight_is_zero_optimization():
    completed = subprocess.run(
        [sys.executable, str(Path(batch.__file__).resolve()), "--worker-preflight", batch.EXPECTED[0], "--config", str(batch.DEFAULT_CONFIG)],
        cwd=batch.ROOT, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gates"]["git"] is True
    assert payload["optimization_calls"] == 0
