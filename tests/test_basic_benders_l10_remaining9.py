from __future__ import annotations

from pathlib import Path

import pytest

from experiments import run_basic_benders_scaling as runner
from scripts.audit_basic_benders_scaling_l10_remaining9 import build_audit
from scripts.run_basic_benders_scaling_l10_remaining9 import (
    DEFAULT_CONFIG,
    EXPECTED,
    build_dry_run,
    execute_batch,
)


ROOT = Path(__file__).resolve().parents[1]


def test_remaining9_protocol_is_closed_and_exactly_scoped() -> None:
    config = runner.load_config(DEFAULT_CONFIG)
    assert config["formal_run_authorized"] is False
    assert config["authorized_condition_ids"] == EXPECTED
    assert len(config["frozen_input_identity"]) == 9
    assert config["resource_policy"]["condition_time_limit_seconds"] == 900
    assert config["resource_policy"]["maximum_process_tree_memory_gib_by_size"]["L10"] == 4
    assert config["resource_policy"]["minimum_available_memory_gib_by_size"]["L10"] == 7
    assert config["resource_policy"]["minimum_system_available_memory_gib"] == 3
    assert config["resource_policy"]["minimum_free_disk_gib"] == 20
    assert config["resource_policy"]["memory_monitor_interval_seconds"] == 0.25
    assert config["resource_policy"]["retry_policy"] == "no_automatic_retry"


def test_dry_run_checks_nine_frozen_inputs_without_attempts() -> None:
    dry = build_dry_run(DEFAULT_CONFIG)
    assert dry["optimization_calls"] == 0
    assert len(dry["conditions"]) == 9
    assert all(row["identity_status"] == "PASS" for row in dry["conditions"])
    assert all(row["expected_attempt"] == "attempt-001" for row in dry["conditions"])
    assert all(not row["attempt_exists"] for row in dry["conditions"])
    assert all(not row["canonical_result_exists"] for row in dry["conditions"])


def test_batch_execution_fails_closed_before_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.run_basic_benders_scaling_l10_remaining9.build_dry_run",
        lambda *_: pytest.fail("dry-run must not follow a closed authorization gate"),
    )
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        execute_batch(DEFAULT_CONFIG)


def test_general_runner_rejects_non_allowlisted_and_preserves_pilot_scope() -> None:
    config = runner.load_config(DEFAULT_CONFIG)
    assert runner.candidate(config, "BASIC_L10_S20260922")["seed"] == 20260922
    with pytest.raises(RuntimeError, match="not allowlisted"):
        runner.candidate(config, "BASIC_L10_S20260921")
    pilot = runner.load_config(ROOT / "experiments/configs/development/basic_benders_scaling_l10_pilot_v1.yaml")
    assert runner.candidate(pilot)["condition_id"] == "BASIC_L10_S20260921"


def test_static_audit_is_zero_optimization_and_preserves_pilot() -> None:
    audit = build_audit()
    assert audit["status"] == "STATIC_AUDIT_PASS"
    assert audit["formal_run_authorized"] is False
    assert audit["optimization_calls"] == 0
    assert len(audit["conditions"]) == 9
    assert audit["checks"]["pilot_preserved"] is True
