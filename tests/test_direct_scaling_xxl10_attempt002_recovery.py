from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import run_direct_scaling_xxl10_paired_pilot as pilot


def _known_attempt(root: Path, *, stderr: str = pilot.FAILURE_FRAGMENT) -> Path:
    attempt = root / "worker_logs" / pilot.CONDITION_ID / "attempt-001"
    attempt.mkdir(parents=True)
    (attempt / "stdout.log").write_text("", encoding="utf-8")
    (attempt / "stderr.log").write_text(stderr, encoding="utf-8")
    (attempt / "resource_monitor.json").write_text(json.dumps({
        "condition_id": pilot.CONDITION_ID,
        "attempt": "attempt-001",
        "peak_process_tree_memory_gib": 0.034252166748046875,
        "wall_clock_seconds": 0.8216574001125991,
        "stop_reason": None,
        "worker_return_code": 1,
    }), encoding="utf-8")
    return attempt


def test_frozen_core_runner_sha_is_unchanged():
    assert pilot.sha256(pilot.ROOT / pilot.CORE_RUNNER_PATH) == pilot.CORE_RUNNER_SHA256


def test_protocol_preserves_solver_science_and_resource_contract():
    config = pilot.runner.load_config(pilot.DEFAULT_CONFIG)
    pilot.validate_protocol(config)
    assert config["recovery_control"] == {
        "attempt": "attempt-002",
        "authorized": False,
        "required_prior_attempt": "attempt-001",
        "required_failure": "WORKER_INNER_GIT_GATE_MISMATCH",
    }
    assert {name: config["solver_parameters"][name] for name in ("MIPGap", "Method", "Threads")} == {
        "MIPGap": 0.0,
        "Method": 2,
        "Threads": 2,
    }
    policy = config["resource_policy"]
    assert policy["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
    assert policy["minimum_available_memory_gib_by_size"] == {"XXL10": 16}
    assert policy["minimum_system_available_memory_gib"] == 3
    assert policy["minimum_free_disk_gib"] == 20
    assert policy["condition_time_limit_seconds"] == 900
    assert policy["memory_monitor_interval_seconds"] == 0.25
    assert policy["parallel_workers"] == 1
    assert policy["retry_policy"] == "no_automatic_retry"


def test_real_attempt_001_is_the_specific_recoverable_gate_failure():
    config = pilot.runner.load_config(pilot.DEFAULT_CONFIG)
    output = pilot.ROOT / config["output_directory"]
    audit = pilot.audit_attempt_001(output)
    assert audit["classification"] == "WORKER_INNER_GIT_GATE_MISMATCH"
    assert all(audit["checks"].values())
    assert set(audit["files"]) == pilot.ATTEMPT_001_FILES


def test_unknown_failure_is_not_recoverable(tmp_path):
    _known_attempt(tmp_path, stderr="unrelated worker failure")
    assert pilot.audit_attempt_001(tmp_path)["classification"] == "UNKNOWN_FAILURE"


def test_attempt_002_is_absent_then_protected_from_reuse(tmp_path):
    _known_attempt(tmp_path)
    assert pilot.validate_attempt_002_state(tmp_path, expect_started=False)
    attempt = tmp_path / "worker_logs" / pilot.CONDITION_ID / "attempt-002"
    attempt.mkdir()
    assert not pilot.validate_attempt_002_state(tmp_path, expect_started=False)
    (attempt / "stdout.log").write_text("", encoding="utf-8")
    (attempt / "stderr.log").write_text("", encoding="utf-8")
    assert pilot.validate_attempt_002_state(tmp_path, expect_started=True)
    (attempt / "resource_monitor.json").write_text("{}", encoding="utf-8")
    assert not pilot.validate_attempt_002_state(tmp_path, expect_started=True)


def test_git_allowlist_accepts_only_archives_and_exact_audits(tmp_path):
    output = pilot.ROOT / "experiments/results/direct_scaling_xxl10_paired_pilot_v1"
    allowed = [
        "?? experiments/results/direct_scaling_xxl10_paired_pilot_v1/worker_logs/x.txt",
        "?? experiments/results/ef_benders_scaling_xxl10_remaining9_v1/runs/x/result.json",
        "?? artifacts/direct_scaling_xxl10_attempt002_recovery_audit.json",
    ]
    assert pilot.unexpected_git_entries(allowed, output) == []
    rejected = [
        " M experiments/run_direct_scaling.py",
        " M experiments/configs/development/direct_scaling_xxl10_paired_pilot_v1.yaml",
        "?? artifacts/direct_scaling_xxl10_attempt002_recovery_audit.json.extra",
        "?? unknown.txt",
    ]
    assert pilot.unexpected_git_entries(rejected, output) == rejected


def test_execute_requires_separate_recovery_authorization(monkeypatch):
    monkeypatch.setattr(pilot.runner, "run_monitored", lambda *_args: pytest.fail("optimization must not launch"))
    with pytest.raises(RuntimeError, match="RECOVERY_ATTEMPT_002_NOT_AUTHORIZED"):
        pilot.execute()


def test_dry_run_is_attempt_002_and_zero_optimization():
    dry = pilot.build_dry_run()
    assert dry["next_attempt"] == "attempt-002"
    assert dry["attempt_001"]["classification"] == "WORKER_INNER_GIT_GATE_MISMATCH"
    assert dry["gates"]["attempt_002_state"] is True
    assert dry["gates"]["canonical_absent"] is True
    assert dry["recovery_attempt_authorized"] is False
    assert dry["optimization_calls"] == 0


def test_independent_worker_preflight_exercises_child_git_gate():
    completed = subprocess.run(
        [sys.executable, str(Path(pilot.__file__).resolve()), "--worker-preflight", "--config", str(pilot.DEFAULT_CONFIG)],
        cwd=pilot.ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["git"]["clean_for_execution"] is True
    assert payload["optimization_calls"] == 0
