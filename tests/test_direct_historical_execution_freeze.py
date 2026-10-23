from __future__ import annotations

from pathlib import Path

import pytest

from experiments import run_direct_scaling as runner


ROOT = Path(__file__).resolve().parents[1]
RETRY = ROOT / "experiments/configs/formal/direct_scaling_l10_resource_retry_v2.yaml"


def test_retry_protocol_is_frozen_even_without_canonical() -> None:
    config = runner.load_config(RETRY)
    condition = runner.authorized_conditions(config)[0]
    with pytest.raises(PermissionError, match="FORMAL_EXPERIMENT_FROZEN"):
        runner.validate_execution_gate(config, condition, ROOT / config["output_directory"])


def test_direct_solver_entry_blocks_before_model_build(monkeypatch) -> None:
    config = runner.load_config(RETRY)
    condition = runner.authorized_conditions(config)[0]
    monkeypatch.setattr(
        runner,
        "build_exact_reconfiguration_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("optimizer model built")),
    )
    with pytest.raises(PermissionError, match="FORMAL_EXPERIMENT_FROZEN"):
        runner.solve_condition(config, condition, ROOT / config["output_directory"])


def test_config_path_replacement_cannot_reactivate_historical_experiment(tmp_path) -> None:
    replacement = tmp_path / "replacement.yaml"
    replacement.write_text(RETRY.read_text(encoding="utf-8"), encoding="utf-8")
    config = runner.load_config(replacement)
    with pytest.raises(PermissionError, match="FORMAL_EXPERIMENT_FROZEN"):
        runner.validate_execution_gate(
            config,
            runner.authorized_conditions(config)[0],
            ROOT / config["output_directory"],
        )
