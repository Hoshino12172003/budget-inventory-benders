from __future__ import annotations

import json
from pathlib import Path

import pytest

import experiments.run_e2_stockout_common_scenario as runner
from robust_inventory_reconfiguration.e2_stockout_common_scenario import (
    file_sha256,
    fixed_policy_block_keys,
    policy_from_manifest,
    validate_complete_evaluation,
)
from robust_inventory_reconfiguration.instance import load_instance


def _identities() -> tuple[dict, object, object, tuple, dict]:
    identity, scenario, authorization = runner.validate_preflight_authorization()
    policy_row = next(
        row for row in identity["policies"] if row["policy_id"] == authorization["policy_id"]
    )
    case_row = next(
        row for row in scenario["cases"] if row["case_id"] == authorization["case_id"]
    )
    instance = load_instance(runner.ROOT / case_row["instance_path"])
    policy = policy_from_manifest(runner.ROOT, policy_row)
    selected = [f"S{index:04d}" for index in range(4657)]
    blocks = fixed_policy_block_keys(instance, selected)
    expected = runner.preflight_checkpoint_identity(
        authorization=authorization,
        scenario=scenario,
        case_row=case_row,
        policy_row=policy_row,
        block_keys=blocks,
    )
    return scenario, instance, policy, blocks, expected


def test_completed_preflight_evidence_is_identity_valid() -> None:
    checkpoint = runner.validate_completed_resource_preflight_evidence()
    assert checkpoint["classification"] == "PREFLIGHT_NON_PUBLISHABLE"
    assert checkpoint["completion_status"] == "COMPLETE"
    assert checkpoint["formal_run_authorized"] is False
    assert checkpoint["completed_blocks"] == 632
    assert checkpoint["scenario_count"] == 4657
    assert checkpoint["economic_optimal_block_count"] == 632
    assert checkpoint["reporting_optimal_block_count"] == 632


def test_preflight_proves_incomplete_checkpoint_recovery() -> None:
    checkpoint = json.loads(
        (runner.PREFLIGHT_ROOT / "checkpoint.json").read_text(encoding="utf-8")
    )
    first, second = checkpoint["run_segments"]
    assert first["resumed"] is False
    assert first["completed_blocks_at_end"] == 16
    assert first["end_reason"] == "PREDECLARED_PROTOCOL_INTERRUPT"
    assert second["resumed"] is True
    assert second["started_from_completed_blocks"] == 16
    assert checkpoint["resume_validation"] == {
        "validated_completed_prefix_blocks": 16,
        "checkpoint_digest_verified": True,
        "identity_chain_verified": True,
    }


def test_preflight_rows_and_cost_components_are_complete() -> None:
    scenario, instance, policy, _, _ = _identities()
    checkpoint = json.loads(
        (runner.PREFLIGHT_ROOT / "checkpoint.json").read_text(encoding="utf-8")
    )
    rows = validate_complete_evaluation(
        checkpoint["evaluation"],
        instance=instance,
        policy=policy,
        scenario_manifest=scenario,
    )
    assert len(rows) == 4657
    assert checkpoint["metric_summary"]["coverage_status"] == "COMPLETE_FROZEN_SCENARIO_SET"
    assert set(checkpoint["metric_summary"]["worst_over_frozen_set"]) == {
        "total_shortage",
        "total_service_violation",
        "shortage_penalty_cost",
        "economic_optimum_recourse_cost",
    }


def test_preflight_checkpoint_corruption_and_identity_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    scenario, instance, policy, blocks, expected = _identities()
    source = runner.PREFLIGHT_ROOT / "checkpoint.json"
    checkpoint = json.loads(source.read_text(encoding="utf-8"))
    copied = tmp_path / "checkpoint.json"
    runner.write_checkpoint(copied, checkpoint)
    wrong = {**expected, "runner_sha256": "0" * 64}
    with pytest.raises(ValueError, match="identity mismatch: runner_sha256"):
        runner.validate_preflight_checkpoint(
            copied,
            expected_identity=wrong,
            instance=instance,
            policy=policy,
            scenario_manifest=scenario,
            block_keys=blocks,
        )
    copied.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="content hash mismatch"):
        runner.validate_preflight_checkpoint(
            copied,
            expected_identity=expected,
            instance=instance,
            policy=policy,
            scenario_manifest=scenario,
            block_keys=blocks,
        )


def test_preflight_output_hashes_and_sizes_are_exact() -> None:
    result_path = runner.PREFLIGHT_ROOT / "result_manifest.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    checkpoint = runner.PREFLIGHT_ROOT / "checkpoint.json"
    digest = checkpoint.with_suffix(".json.sha256")
    assert result["checkpoint_sha256"] == file_sha256(checkpoint)
    assert result["checkpoint_digest_file_sha256"] == file_sha256(digest)
    assert result["checkpoint_bytes"] == checkpoint.stat().st_size
    assert result["checkpoint_digest_bytes"] == digest.stat().st_size
    assert result["checkpoint_bundle_bytes"] == checkpoint.stat().st_size + digest.stat().st_size
