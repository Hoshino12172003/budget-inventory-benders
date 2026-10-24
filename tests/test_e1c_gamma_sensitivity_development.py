from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments/run_e1c_gamma_sensitivity_development.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("e1c_gamma_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dry_run_freezes_grid_identity_and_resources() -> None:
    runner = load_runner()
    result = runner.dry_run()
    assert result["status"] == "BLOCKED_SOURCE_MISSING"
    assert result["optimization_calls"] == 0
    assert result["input_audit"]["status"] == "SOURCE_MISSING"
    assert len(result["input_audit"]["missing_paths"]) == 5
    assert len(result["conditions"]) == 12
    assert {row["gamma"] for row in result["conditions"]} == {2, 4, 6, 8}
    assert result["memory_gate"] == {
        "preflight_gib": 18,
        "process_stop_gib": 14,
        "system_emergency_gib": 3,
        "poll_seconds": 0.25,
    }


def test_config_is_development_only_and_reuses_prepared_l() -> None:
    runner = load_runner()
    config = runner.validate_static_config()
    assert config["development_only"] is True
    assert config["paper_final_observation"] is False
    assert config["formal_run_authorized"] is False
    audit = runner.development_input_audit(config)
    assert audit["status"] == "SOURCE_MISSING"
    with pytest.raises(RuntimeError, match="E1C_GAMMA_DEVELOPMENT_INPUT_MISSING"):
        runner.validate_config()


def test_preflight_fails_closed_below_frozen_threshold(monkeypatch) -> None:
    runner = load_runner()
    config = runner.validate_static_config()

    class Memory:
        available = 17 * 2**30

    monkeypatch.setattr(runner.psutil, "virtual_memory", lambda: Memory())
    with pytest.raises(RuntimeError, match="E1C_GAMMA_RESOURCE_PREFLIGHT_BLOCKED"):
        runner.preflight(config)


def test_gamma2_sanity_checks_all_three_frozen_methods() -> None:
    runner = load_runner()
    config = runner.validate_static_config()
    audit = runner.development_input_audit(config)
    expected = {
        "experiments/results/e1c_development_probe_v1/L/PURE_BENDERS/result.json",
        "experiments/results/e1c_development_probe_v1/L/AGGREGATE_BENDERS_STRUCTURED_ORACLE/result.json",
        "experiments/results/e1c_development_probe_v1/L/PRB_BENDERS/result.json",
    }
    assert expected <= set(audit["missing_paths"])
