from __future__ import annotations

import json

import pytest

from experiments import run_direct_scaling as runner
from scripts.freeze_direct_scaling_l10_xl10 import DIRECT, build_freeze


FREEZE_CONTROL = runner.ROOT / "experiments/configs/formal/direct_scaling_xl10_frozen_v1.yaml"


def test_freeze_manifest_has_exact_terminal_counts_and_pairs() -> None:
    manifest, sha_rows, pairs, summaries = build_freeze()
    assert manifest["optimization_calls"] == 0
    assert manifest["counts"] == {
        "CERTIFIED": 19,
        "RESOURCE_FAILURE": 1,
        "TIME_FAILURE": 0,
        "NUMERICAL_CERTIFICATION_FAILURE": 0,
        "UNEXECUTED": 0,
    }
    assert len(pairs) == 19
    assert not any(row["size"] == "XL10" and row["seed"] == 20260924 for row in pairs)
    assert {row["size"]: row["direct_completion_rate"] for row in summaries} == {"L10": 1.0, "XL10": 0.9}
    assert sha_rows
    assert {row["path"].split("/")[-1] for row in manifest["batch_reports"]} == {"condition_status.csv", "summary.json"}


def test_xl10_failure_preserves_two_resource_attempts_and_unverified_gap() -> None:
    manifest, _, _, _ = build_freeze()
    failure = manifest["xl10_terminal_failure"]
    assert failure["attempts"] == ["attempt-001", "attempt-002"]
    assert failure["stop_reasons"] == ["RESOURCE_PROCESS_CAP", "RESOURCE_PROCESS_CAP"]
    assert failure["attempt_002_progress_gap_percent"] == pytest.approx(0.38255149349544637)
    assert failure["interpretation"] == "UNVERIFIED_INTERRUPTED_SOLVER_PROGRESS_NOT_A_FINAL_EXACT_GAP"


def test_every_canonical_archive_and_provenance_hash_passes() -> None:
    manifest, _, _, _ = build_freeze()
    canonical = [row["canonical_result"] for row in manifest["conditions"] if row["canonical_result"]]
    assert len(canonical) == 19
    assert all(all(result["checks"].values()) for result in canonical)
    assert all(len(result["result_sha256"]) == 64 and len(result["provenance_sha256"]) == 64 for result in canonical)


def test_new_freeze_control_closes_all_historical_xl10_authorizations(monkeypatch) -> None:
    freeze = json.loads(FREEZE_CONTROL.read_text(encoding="utf-8"))
    assert freeze["execution_closed"] is True
    historical = runner.load_config(runner.ROOT / "experiments/configs/formal/direct_scaling_xl10_remaining7_8gib_v1.yaml")
    condition = runner.authorized_conditions(historical)[0]
    monkeypatch.setattr(runner, "validate_environment", lambda config: pytest.fail("freeze must precede environment probe"))
    with pytest.raises(RuntimeError, match="DIRECT_SCALE_FROZEN"):
        runner.validate_execution_gate(historical, condition, DIRECT)


def test_xxl10_is_explicitly_outside_completed_scale_scope() -> None:
    manifest, _, _, _ = build_freeze()
    assert manifest["scope"]["included_scales"] == ["L10", "XL10"]
    assert manifest["scope"]["xxl10"] == "NOT_EXECUTED_OUTSIDE_COMPLETED_SCALE_SCOPE"
