from __future__ import annotations

import json
from pathlib import Path

import pytest

import experiments.run_e2_stockout_common_scenario as runner
from robust_inventory_reconfiguration.e2_stockout_common_scenario import (
    build_structural_resource_preflight,
    validate_formal_checkpoint,
    write_checkpoint,
)


ROOT = Path(__file__).resolve().parents[1]


def test_formal_authorization_is_locked_and_plan_has_16_unique_tasks() -> None:
    identity, scenario, authorization = runner.validate_formal_authorization(
        require_authorized=False
    )
    tasks = authorization["planned_tasks"]
    assert authorization["formal_run_authorized"] is False
    assert authorization["human_policy_approval"] is True
    assert authorization["authorization_transition"] == [False]
    assert scenario["formal_run_authorized"] is False
    assert identity["formal_run_authorized"] is False
    assert len(tasks) == len({task["task_id"] for task in tasks}) == 16
    assert all("NOMINAL" not in task["policy_id"] for task in tasks)
    assert not any(row["formal_authorized"] for row in identity["policies"])
    assert (
        identity["identity_freeze_status"]
        == "FROZEN_TWO_POLICY_SCIENTIFIC_DEFINITION_CONFIRMED"
    )


def test_formal_checkpoint_schema_defines_every_required_property() -> None:
    schema = json.loads(runner.FORMAL_CHECKPOINT_SCHEMA.read_text(encoding="utf-8"))
    assert set(schema["required"]) <= set(schema["properties"])
    assert schema["properties"]["solver_version"]["type"] == "string"


def test_preflight_authorization_is_exactly_scoped_and_non_formal() -> None:
    identity, scenario, authorization = runner.validate_preflight_authorization()
    assert authorization["preflight_run_authorized"] is True
    assert authorization["formal_run_authorized"] is False
    assert authorization["case_id"] == "210202"
    assert authorization["policy_id"] == "EXISTING_CANONICAL_210202"
    assert authorization["scenario_count"] == 4657
    assert authorization["expected_block_count"] == 632
    assert authorization["protocol_interrupt_after_blocks"] == 16
    assert authorization["threads"] == 1
    assert identity["formal_run_authorized"] is False
    assert scenario["formal_run_authorized"] is False


def test_preflight_checkpoint_schema_defines_every_required_property() -> None:
    schema = json.loads(runner.PREFLIGHT_CHECKPOINT_SCHEMA.read_text(encoding="utf-8"))
    assert set(schema["required"]) <= set(schema["properties"])
    assert schema["properties"]["classification"]["const"] == "PREFLIGHT_NON_PUBLISHABLE"
    assert schema["properties"]["formal_run_authorized"]["const"] is False


def test_unauthorized_formal_runner_refuses_before_optimizer(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "evaluate_fixed_policy_scenarios",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("optimizer invoked")),
    )
    with pytest.raises(PermissionError, match="not authorized"):
        runner.run_formal(resume=False)


def test_formal_authorization_rejects_code_identity_mismatch(
    monkeypatch, tmp_path: Path
) -> None:
    authorization = json.loads(runner.FORMAL_AUTHORIZATION.read_text(encoding="utf-8"))
    first_path = next(iter(authorization["identity_file_sha256"]))
    authorization["identity_file_sha256"][first_path] = "0" * 64
    payload = {
        key: value
        for key, value in authorization.items()
        if key != "authorization_payload_sha256"
    }
    from robust_inventory_reconfiguration.e2_stockout_common_scenario import (
        canonical_sha256,
    )

    authorization["authorization_payload_sha256"] = canonical_sha256(payload)
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(authorization), encoding="utf-8")
    monkeypatch.setattr(runner, "FORMAL_AUTHORIZATION", path)
    with pytest.raises(ValueError, match="code/protocol identity mismatch"):
        runner.validate_formal_authorization(require_authorized=False)


def test_formal_checkpoint_corruption_and_identity_mismatch_fail_closed(
    tiny_instance, tmp_path: Path
) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = {
        "schema_version": "1.0",
        "classification": "FORMAL_COMMON_SCENARIO_RESULT",
        "experiment_id": "E2_STOCKOUT_COMMON_SCENARIO_V1",
        "task_id": "E2S-tiny-ROBUST",
        "case_id": "tiny",
        "policy_id": "TEST",
        "scenario_count": 4657,
        "runtime_seconds": 0.0,
        "runner_sha256": "a" * 64,
    }
    write_checkpoint(path, checkpoint)

    class Policy:
        case_id = "tiny"
        policy_id = "TEST"

    with pytest.raises(ValueError, match="identity mismatch: runner_sha256"):
        validate_formal_checkpoint(
            path,
            expected_identity={"runner_sha256": "b" * 64},
            instance=tiny_instance,
            policy=Policy(),
            scenario_manifest={},
        )
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="content hash mismatch"):
        validate_formal_checkpoint(
            path,
            expected_identity={"runner_sha256": "a" * 64},
            instance=tiny_instance,
            policy=Policy(),
            scenario_manifest={},
        )


def test_structural_resource_preflight_is_two_policy_and_non_authorizing() -> None:
    scenario = json.loads(runner.SCENARIO_MANIFEST.read_text(encoding="utf-8"))
    pilot = json.loads(
        (
            runner.PILOT_ROOT
            / "PILOT-210202-EXISTING_CANONICAL"
            / "checkpoint.json"
        ).read_text(encoding="utf-8")
    )
    result = build_structural_resource_preflight(scenario, pilot)
    assert result["classification"] == "STRUCTURAL_PREFLIGHT_ONLY_NO_FULL_SCENARIO_SOLVE"
    assert result["formal_run_authorized"] is False
    assert result["case_policy_task_count"] == 16
    assert result["logical_scenario_rows_total"] == 16 * 4657
    assert result["blocks_per_task"] == 632
    assert result["threads"] == 1
    assert result["admission_status"] == "FULL_CASE_RESOURCE_PREFLIGHT_STILL_REQUIRED"
