from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments import run_direct_scaling as runner
from scripts.audit_direct_scaling_l10_authorization import audit as authorization_audit


RETRY_CONFIG = runner.ROOT / "experiments/configs/formal/direct_scaling_l10_resource_retry_v2.yaml"


def test_direct_grid_is_frozen_30_conditions() -> None:
    config = runner.load_config(runner.CONFIG)
    grid = runner.conditions(config)
    assert len(grid) == 30
    assert {row["size"] for row in grid} == {"L10", "XL10", "XXL10"}
    assert {row["seed"] for row in grid} == set(range(20260921, 20260931))
    assert config["fixed_scientific_parameters"] == {
        "Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "SL": 0.9, "phi_multiplier": 1.85
    }


def test_formal_execution_is_fail_closed_before_environment_probe(monkeypatch) -> None:
    config = {**runner.load_config(runner.CONFIG), "formal_run_authorized": False}
    monkeypatch.setattr(runner, "current_environment", lambda: pytest.fail("environment probe should not run"))
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        runner.validate_execution_gate(config, runner.conditions(config)[0], runner.ROOT / config["output_directory"])


def test_all_frozen_inputs_pass_identity_checks() -> None:
    config = runner.load_config(runner.CONFIG)
    for condition in runner.conditions(config):
        instance, preparation, hashes = runner.verified_input(config, condition)
        assert preparation["instance_hash"] == runner.canonical_hash(instance.to_dict())
        assert preparation["x0_hash"] == runner.canonical_hash(instance.initial_inventory)
        assert set(hashes) == {"instance_sha256", "preparation_sha256"}


def test_existing_result_mismatch_fails_closed(tmp_path: Path) -> None:
    config = runner.load_config(runner.CONFIG)
    condition = runner.conditions(config)[0]
    target = tmp_path / "runs" / condition["condition_id"]
    target.mkdir(parents=True)
    result_path = target / "result.json"
    result_path.write_text(json.dumps({"condition_id": "WRONG"}), encoding="utf-8")
    (target / "provenance.json").write_text(
        json.dumps({"result_sha256": runner.file_sha256(result_path)}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="identity failure"):
        runner.verified_existing_result(config, condition, tmp_path)


def test_incomplete_archive_cannot_be_resumed_as_certified(tmp_path: Path) -> None:
    config = runner.load_config(runner.CONFIG)
    condition = runner.conditions(config)[0]
    target = tmp_path / "runs" / condition["condition_id"]
    target.mkdir(parents=True)
    result_path = target / "result.json"
    result_path.write_text(json.dumps({
        "condition_id": condition["condition_id"],
        "size": condition["size"],
        "seed": condition["seed"],
        "config_hash": runner.canonical_hash(config),
        "solver_status": "OPTIMAL",
        "exact_certification": True,
    }), encoding="utf-8")
    (target / "provenance.json").write_text(json.dumps({
        "result_sha256": runner.file_sha256(result_path),
        "archive_complete": False,
    }), encoding="utf-8")
    with pytest.raises(RuntimeError, match="identity failure"):
        runner.verified_existing_result(config, condition, tmp_path)


def test_short_atomic_directory_name() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert '.candidate-{uuid4().hex[:12]}' in source
    assert "refusing to overwrite Direct result" in source


def test_direct_environment_requirement_is_not_inherited_from_renault() -> None:
    config = runner.load_config(runner.CONFIG)
    required = config["required_environment"]
    assert required["gurobipy_version"] == "13.0.1"
    assert required["gurobi_native_version"] == [13, 0, 1]
    assert required["scaling_v2_historical_solver_version"] == "NOT_VERIFIABLE"


def test_direct_model_identity_covers_runner_and_model_sources() -> None:
    identity = runner.model_identity()
    assert len(identity["sha256"]) == 64
    assert set(identity["files"]) == set(runner.MODEL_FILES)
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert '"model_identity": model_identity_record["sha256"]' in source
    assert '"model_identity": model_identity_record,' in source


def test_authorization_is_exactly_the_ten_l10_conditions() -> None:
    config = runner.load_config(runner.CONFIG)
    authorized = runner.authorized_conditions(config)
    assert [row["condition_id"] for row in authorized] == [
        f"DIRECT_L10_S{seed}" for seed in range(20260921, 20260931)
    ]
    assert all(row["size"] == "L10" for row in authorized)
    assert len(runner.conditions(config)) == 30


def test_xl10_and_xxl10_are_rejected_before_environment_probe(monkeypatch, tmp_path: Path) -> None:
    config = {**runner.load_config(runner.CONFIG), "formal_run_authorized": True}
    monkeypatch.setattr(runner, "current_environment", lambda: pytest.fail("environment probe should not run"))
    for condition in runner.conditions(config):
        if condition["size"] != "L10":
            with pytest.raises(RuntimeError, match="CONDITION_NOT_AUTHORIZED"):
                runner.validate_execution_gate(config, condition, runner.ROOT / config["output_directory"])


def test_l10_authorization_audit_passes_without_optimization() -> None:
    payload = authorization_audit()
    assert payload["status"] == "PASS"
    assert payload["optimization_calls"] == 0
    assert payload["source_scaling_post_run"]["formal_counts"] == {
        "expected": 90,
        "certified": 89,
        "documented_non_certified": 1,
        "unattempted": 0,
    }


def test_runner_preserves_solver_log_and_progress_evidence() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "model.Params.OutputFlag = 1" in source
    assert "solver_progress.json" in source
    assert "RESOURCE_MONITOR_FAILURE" in source


def test_retry_protocol_authorizes_attempt_003_for_one_condition() -> None:
    config = runner.load_config(RETRY_CONFIG)
    original = runner.load_config(runner.CONFIG)
    assert config["formal_run_authorized"] is True
    assert [row["condition_id"] for row in runner.authorized_conditions(config)] == [
        "DIRECT_L10_S20260921"
    ]
    assert config["resource_protocol_id"] == "DIRECT_L10_RESOURCE_PROTOCOL_V2_6GIB_RETRY"
    policy = config["resource_policy"]
    assert policy["maximum_process_tree_memory_gib_by_size"]["L10"] == 6
    assert policy["minimum_available_memory_gib_by_size"]["L10"] == 10
    assert policy["minimum_system_available_memory_gib"] == 3
    assert policy["condition_time_limit_seconds"] == 900
    assert policy["memory_monitor_interval_seconds"] == 0.25
    assert policy["parallel_workers"] == 1
    assert config["fixed_scientific_parameters"] == original["fixed_scientific_parameters"]
    assert config["solver_profile"] == original["solver_profile"]
    assert config["solver_parameters"] == original["solver_parameters"]
    assert config["source_output_root"] == original["source_output_root"]


def test_retry_protocol_rejects_every_other_condition_before_environment_probe(monkeypatch) -> None:
    config = {**runner.load_config(RETRY_CONFIG), "formal_run_authorized": True}
    monkeypatch.setattr(runner, "current_environment", lambda: pytest.fail("environment probe should not run"))
    for condition in runner.conditions(config):
        if condition["condition_id"] != "DIRECT_L10_S20260921":
            with pytest.raises(RuntimeError, match="CONDITION_NOT_AUTHORIZED"):
                runner.validate_execution_gate(config, condition, runner.ROOT / config["output_directory"])


def test_retry_uses_next_attempt_without_overwriting_existing_evidence(tmp_path: Path) -> None:
    condition_id = "DIRECT_L10_S20260921"
    original = tmp_path / "worker_logs" / condition_id / "attempt-001"
    original.mkdir(parents=True)
    marker = original / "resource_monitor.json"
    marker.write_text("original", encoding="utf-8")
    assert runner.next_attempt_number(tmp_path, condition_id) == 2
    assert marker.read_text(encoding="utf-8") == "original"


def test_original_resource_stop_evidence_is_immutable() -> None:
    attempt = (
        runner.ROOT
        / "experiments/results/direct_scaling_extension_v1/worker_logs"
        / "DIRECT_L10_S20260921/attempt-001"
    )
    assert runner.next_attempt_number(runner.ROOT / "experiments/results/direct_scaling_extension_v1", "DIRECT_L10_S20260921") == 3
    assert runner.file_sha256(attempt / "resource_monitor.json") == (
        "86f0cebbfe5abf763c6053e8e5d46e2f7ffc330d57d4d27b67e0ccf3752f041b"
    )
    assert runner.file_sha256(attempt / "solver.log") == (
        "1f0fda1313c70959b5c185c120b53ecb501a852d34bfda9b59165a35e88f864b"
    )


def test_attempt002_archive_failure_evidence_is_immutable() -> None:
    attempt = (
        runner.ROOT
        / "experiments/results/direct_scaling_extension_v1/worker_logs"
        / "DIRECT_L10_S20260921/attempt-002"
    )
    expected = {
        "resource_monitor.json": "318079cbd7f284786c787d30063e837def76d4a6335bdced5d6b5d5e609ac52e",
        "solver_progress.json": "e5ee13a70c22a800653087aebf5d404969bf9733c16d4d3f99c68c81f6bcdbb6",
        "solver.log": "07fd3367497928425314a4cfb1586ad0761b0e57dc6b62eb8c668e61d0865657",
        "stderr.log": "78e77fb8f67d4552a582596010a5feed22684ecc79f7f63c96d7c9fc4215b8c8",
        "stdout.log": "5032112f6af6b3db5dc3dec22c288eac895f86eefc344509eea5cf07d4ec5c4e",
    }
    assert {path.name: runner.file_sha256(path) for path in attempt.iterdir() if path.is_file()} == expected
