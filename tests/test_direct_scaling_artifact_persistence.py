from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments import run_direct_scaling as runner


class SharingViolation(PermissionError):
    winerror = 32


def persistence_inputs(tmp_path: Path) -> tuple[dict, dict, dict, dict, Path, Path]:
    condition = {"condition_id": "DIRECT_L10_S20260921", "size": "L10", "seed": 20260921}
    result = {
        "condition_id": condition["condition_id"],
        "solver_status": "OPTIMAL",
        "exact_certification": True,
        "environment": {"python_version": "3.12.7"},
    }
    first_stage = {"case_id": condition["condition_id"], "objective": 1.0}
    input_hashes = {"instance_sha256": "instance", "preparation_sha256": "preparation"}
    model_identity = {"sha256": "model", "files": {}}
    solver_log = tmp_path / ".solver.log"
    progress = tmp_path / ".progress.json"
    solver_log.write_text("optimal\n", encoding="utf-8")
    progress.write_text("{}\n", encoding="utf-8")
    return condition, result, first_stage, input_hashes, model_identity, solver_log, progress


def test_transient_windows_sharing_violation_is_retried(monkeypatch, tmp_path: Path) -> None:
    condition, result, first_stage, input_hashes, model_identity, solver_log, progress = persistence_inputs(tmp_path)
    real_copy = runner.shutil.copy2
    calls = {"solver_log": 0}

    def flaky_copy(source, target):
        if Path(source) == solver_log and calls["solver_log"] == 0:
            calls["solver_log"] += 1
            raise SharingViolation("locked")
        return real_copy(source, target)

    monkeypatch.setattr(runner.shutil, "copy2", flaky_copy)
    target = runner.persist_result_artifacts(
        tmp_path, condition, result, first_stage, input_hashes, model_identity,
        solver_log, progress, log_copy_attempts=2, log_copy_delay=0,
    )
    assert calls["solver_log"] == 1
    assert (target / "result.json").is_file()
    assert (target / "solver.log").read_text(encoding="utf-8") == "optimal\n"
    assert not (target / "CANDIDATE_NOT_FORMAL.json").exists()
    assert json.loads((target / "provenance.json").read_text(encoding="utf-8"))["archive_complete"] is True


def test_persistent_file_lock_preserves_nonformal_candidate(monkeypatch, tmp_path: Path) -> None:
    condition, result, first_stage, input_hashes, model_identity, solver_log, progress = persistence_inputs(tmp_path)
    real_copy = runner.shutil.copy2

    def locked_copy(source, target):
        if Path(source) == solver_log:
            raise SharingViolation("locked")
        return real_copy(source, target)

    monkeypatch.setattr(runner.shutil, "copy2", locked_copy)
    with pytest.raises(SharingViolation):
        runner.persist_result_artifacts(
            tmp_path, condition, result, first_stage, input_hashes, model_identity,
            solver_log, progress, log_copy_attempts=2, log_copy_delay=0,
        )
    candidates = list((tmp_path / "recovery_candidates").iterdir())
    assert len(candidates) == 1
    candidate = candidates[0]
    assert (candidate / "result.json").is_file()
    assert (candidate / "first_stage_solution.json").is_file()
    assert (candidate / "provenance.json").is_file()
    assert (candidate / "CANDIDATE_NOT_FORMAL.json").is_file()
    assert not (tmp_path / "runs" / condition["condition_id"]).exists()


def test_atomic_publication_failure_preserves_nonformal_candidate(monkeypatch, tmp_path: Path) -> None:
    condition, result, first_stage, input_hashes, model_identity, solver_log, progress = persistence_inputs(tmp_path)

    def failed_replace(source, target):
        raise OSError("simulated atomic rename failure")

    monkeypatch.setattr(runner.os, "replace", failed_replace)
    with pytest.raises(OSError, match="atomic rename failure"):
        runner.persist_result_artifacts(
            tmp_path, condition, result, first_stage, input_hashes, model_identity,
            solver_log, progress,
        )
    candidate = next((tmp_path / "recovery_candidates").iterdir())
    marker = json.loads((candidate / "CANDIDATE_NOT_FORMAL.json").read_text(encoding="utf-8"))
    assert marker["formal_artifact"] is False
    assert marker["reason"] == "ATOMIC_PUBLICATION_FAILED"
    assert (candidate / "solver.log").is_file()
    assert not (tmp_path / "runs" / condition["condition_id"]).exists()


def test_abnormal_worker_exit_preserves_attempt_record(monkeypatch, tmp_path: Path) -> None:
    class FailedProcess:
        pid = 12345

        def poll(self):
            return 1

        def wait(self):
            return 1

        def kill(self):
            raise AssertionError("completed process must not be killed")

    config = {
        "resource_protocol_id": "TEST_PROTOCOL",
        "resource_policy": {
            "condition_time_limit_seconds": 900,
            "maximum_process_tree_memory_gib_by_size": {"L10": 6},
            "minimum_system_available_memory_gib": 3,
            "memory_monitor_interval_seconds": 0.25,
        },
    }
    condition = {"condition_id": "DIRECT_L10_S20260921", "size": "L10", "seed": 20260921}
    monkeypatch.setattr(runner, "validate_execution_gate", lambda *args: {"pass": True})
    monkeypatch.setattr(runner, "verified_input", lambda *args: None)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: FailedProcess())
    with pytest.raises(RuntimeError, match="RESOURCE_MONITOR_NO_SAMPLES"):
        runner.run_monitored(Path("config.json"), config, condition, tmp_path)
    monitor_path = tmp_path / "worker_logs" / condition["condition_id"] / "attempt-001" / "resource_monitor.json"
    monitor = json.loads(monitor_path.read_text(encoding="utf-8"))
    assert monitor["worker_return_code"] == 1
    assert monitor["stop_reason"] == "RESOURCE_MONITOR_NO_SAMPLES"
    assert monitor["attempt"] == "attempt-001"


def test_solver_log_is_detached_before_model_and_environment_disposal(monkeypatch) -> None:
    import gurobipy as gp

    events = []

    class Parameters:
        LogFile = "solver.log"

        def __setattr__(self, name, value):
            events.append((name, value))
            object.__setattr__(self, name, value)

    class Model:
        Params = Parameters()

        def dispose(self):
            events.append(("model", "disposed"))

    monkeypatch.setattr(gp, "disposeDefaultEnv", lambda: events.append(("environment", "disposed")))
    runner._release_solver_resources(Model())
    assert events == [
        ("LogFile", ""),
        ("model", "disposed"),
        ("environment", "disposed"),
    ]
