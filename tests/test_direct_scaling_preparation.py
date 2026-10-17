from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments import run_direct_scaling as runner
from scripts.audit_direct_scaling_l10_authorization import audit as authorization_audit


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


def test_short_atomic_directory_name() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert '.tmp-{uuid4().hex[:12]}' in source
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
