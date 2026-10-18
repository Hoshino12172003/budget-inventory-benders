from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments import run_direct_scaling as runner
from scripts import run_direct_scaling_xl10_remaining7 as batch


CONFIG = runner.ROOT / "experiments/configs/formal/direct_scaling_xl10_remaining7_8gib_v1.yaml"
OUTPUT_ROOT = runner.ROOT / "experiments/results/direct_scaling_extension_v1"


def test_protocol_is_closed_fixed_and_scoped_to_remaining_seven() -> None:
    config = runner.load_config(CONFIG)
    source = runner.load_config(batch.XL10_REMAINING9_CONFIG)
    assert config["formal_run_authorized"] is False
    assert config["resource_protocol_id"] == batch.PROTOCOL_ID
    assert [row["condition_id"] for row in runner.authorized_conditions(config)] == batch.CONDITION_IDS
    assert config["fixed_scientific_parameters"] == source["fixed_scientific_parameters"]
    assert config["solver_profile"] == source["solver_profile"]
    assert config["solver_parameters"] == source["solver_parameters"]
    assert config["solver_parameters"]["Method"] == 2
    assert config["solver_parameters"]["Threads"] == 2
    assert config["solver_parameters"]["MIPGap"] == 0.0
    policy = config["resource_policy"]
    assert policy["maximum_process_tree_memory_gib_by_size"]["XL10"] == 8
    assert policy["minimum_available_memory_gib_by_size"]["XL10"] == 12
    assert policy["minimum_system_available_memory_gib"] == 3
    assert policy["condition_time_limit_seconds"] == 900
    assert policy["memory_monitor_interval_seconds"] == 0.25
    assert policy["parallel_workers"] == 1


def test_plan_freezes_attempt_numbers_and_rejects_an_extra_retry(tmp_path: Path) -> None:
    config = runner.load_config(CONFIG)
    first = tmp_path / "worker_logs" / batch.CONDITION_IDS[0] / "attempt-001"
    first.mkdir(parents=True)
    assert {row["condition_id"]: row["next_attempt"] for row in batch.build_plan(config, tmp_path)} == batch.EXPECTED_ATTEMPTS
    (first.parent / "attempt-002").mkdir()
    with pytest.raises(RuntimeError, match="attempt identities changed"):
        batch.build_plan(config, tmp_path)


def test_current_plan_and_prior_three_certified_archives_pass() -> None:
    config = runner.load_config(CONFIG)
    assert {row["condition_id"]: row["next_attempt"] for row in batch.build_plan(config, OUTPUT_ROOT)} == batch.EXPECTED_ATTEMPTS
    audits = batch.audit_prior_certified_results(OUTPUT_ROOT)
    assert [row["condition_id"] for row in audits] == [f"DIRECT_XL10_S{seed}" for seed in range(20260921, 20260924)]
    assert all(row["solver_status"] == "OPTIMAL" and row["exact_certification"] for row in audits)
    assert all(len(row[key]) == 64 for row in audits for key in ("result_sha256", "provenance_sha256", "resource_monitor_sha256"))


def test_resource_failure_is_classified_without_becoming_success(tmp_path: Path) -> None:
    config = runner.load_config(CONFIG)
    condition = runner.authorized_conditions(config)[1]
    attempt = tmp_path / "worker_logs" / condition["condition_id"] / "attempt-001"
    attempt.mkdir(parents=True)
    (attempt / "resource_monitor.json").write_text(json.dumps({
        "attempt": "attempt-001",
        "resource_protocol_id": batch.PROTOCOL_ID,
        "stop_reason": "RESOURCE_PROCESS_CAP",
        "worker_return_code": 1,
        "peak_process_tree_memory_gib": 8.0,
        "wall_clock_seconds": 1.0,
    }), encoding="utf-8")
    row = batch.classify_condition(config, condition, tmp_path)
    assert row["status"] == "RESOURCE_OR_TIME_FAILURE"
    assert row["exact_certification"] is None


def test_unknown_failure_is_fail_closed(tmp_path: Path) -> None:
    config = runner.load_config(CONFIG)
    condition = runner.authorized_conditions(config)[1]
    attempt = tmp_path / "worker_logs" / condition["condition_id"] / "attempt-001"
    attempt.mkdir(parents=True)
    (attempt / "resource_monitor.json").write_text(json.dumps({
        "attempt": "attempt-001",
        "resource_protocol_id": batch.PROTOCOL_ID,
        "stop_reason": "RESOURCE_MONITOR_FAILURE",
        "worker_return_code": 1,
    }), encoding="utf-8")
    assert batch.classify_condition(config, condition, tmp_path)["status"] == "INTEGRITY_FAILURE"


def test_status_summary_keeps_resource_and_time_failures_separate(tmp_path: Path) -> None:
    rows = [
        {"condition_id": "success", "attempt": "attempt-001", "status": "SUCCESS", "solver_status": "OPTIMAL", "exact_certification": True, "stop_reason": None, "peak_process_tree_memory_gib": 1, "wall_clock_seconds": 1, "objective": 1, "best_bound": 1, "mip_gap": 0, "detail": ""},
        {"condition_id": "resource", "attempt": "attempt-001", "status": "RESOURCE_OR_TIME_FAILURE", "solver_status": None, "exact_certification": None, "stop_reason": "RESOURCE_PROCESS_CAP", "peak_process_tree_memory_gib": 8, "wall_clock_seconds": 2, "objective": None, "best_bound": None, "mip_gap": None, "detail": ""},
        {"condition_id": "time", "attempt": "attempt-001", "status": "RESOURCE_OR_TIME_FAILURE", "solver_status": "TIME_LIMIT", "exact_certification": False, "stop_reason": None, "peak_process_tree_memory_gib": 7, "wall_clock_seconds": 900, "objective": 2, "best_bound": 1, "mip_gap": 0.5, "detail": ""},
        *[
            {"condition_id": f"unexecuted-{index}", "attempt": "attempt-001", "status": "UNEXECUTED", "solver_status": None, "exact_certification": None, "stop_reason": None, "peak_process_tree_memory_gib": None, "wall_clock_seconds": None, "objective": None, "best_bound": None, "mip_gap": None, "detail": ""}
            for index in range(4)
        ],
    ]
    batch.write_status(tmp_path, rows)
    summary = json.loads((tmp_path / "batch_reports" / batch.PROTOCOL_ID / "summary.json").read_text(encoding="utf-8"))
    assert summary["denominator"] == 7
    assert summary["counts"]["certified"] == 1
    assert summary["counts"]["resource_failure"] == 1
    assert summary["counts"]["time_failure"] == 1
    assert summary["counts"]["UNEXECUTED"] == 4


def test_seed24_attempt001_resource_evidence_is_immutable() -> None:
    attempt = OUTPUT_ROOT / "worker_logs" / "DIRECT_XL10_S20260924" / "attempt-001"
    assert runner.file_sha256(attempt / "resource_monitor.json") == "f091f9aeb222bc3ba8918303d27f565c5cd7e31f014d72e3a53a8d294965e1c9"
    assert runner.file_sha256(attempt / "solver.log") == "b701d8cca12002dc25a34f0e201fd059fb022e131922d7fcc6f59941ea5bf636"


def test_execute_is_blocked_while_protocol_is_unauthorized(monkeypatch, tmp_path: Path) -> None:
    config = runner.load_config(CONFIG)
    monkeypatch.setattr(batch, "build_plan", lambda *args: pytest.fail("plan must not execute"))
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        batch.execute_batch(CONFIG, config, tmp_path)


def test_process_tree_termination_waits_then_kills_survivors(monkeypatch) -> None:
    events = []

    class Process:
        def __init__(self, name):
            self.name = name

        def children(self, recursive):
            assert recursive is True
            return [child]

        def terminate(self):
            events.append((self.name, "terminate"))

        def kill(self):
            events.append((self.name, "kill"))

    parent = Process("parent")
    child = Process("child")
    waits = []
    monkeypatch.setattr(runner.psutil, "Process", lambda pid: parent)

    def wait_procs(processes, timeout):
        waits.append(([process.name for process in processes], timeout))
        return ([], [child]) if len(waits) == 1 else (list(processes), [])

    monkeypatch.setattr(runner.psutil, "wait_procs", wait_procs)
    runner._terminate_process_tree(123)
    assert events == [("child", "terminate"), ("parent", "terminate"), ("child", "kill")]
    assert waits == [(["child", "parent"], 3), (["child"], 3)]
