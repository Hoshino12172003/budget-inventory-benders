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
    assert result["status"] == "DRY_RUN_PASS"
    assert result["optimization_calls"] == 0
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
    config, instance, baseline = runner.validate_config()
    assert config["development_only"] is True
    assert config["paper_final_observation"] is False
    assert config["formal_run_authorized"] is False
    assert (instance.num_depots, instance.num_regions, instance.num_products) == (25, 24, 12)
    assert baseline["seed"] == 20260911
    assert baseline["Gamma"] == 2


def test_preflight_fails_closed_below_frozen_threshold(monkeypatch) -> None:
    runner = load_runner()
    config, _, _ = runner.validate_config()

    class Memory:
        available = 17 * 2**30

    monkeypatch.setattr(runner.psutil, "virtual_memory", lambda: Memory())
    with pytest.raises(RuntimeError, match="E1C_GAMMA_RESOURCE_PREFLIGHT_BLOCKED"):
        runner.preflight(config)


def test_gamma2_sanity_checks_all_three_frozen_methods() -> None:
    runner = load_runner()
    config, _, _ = runner.validate_config()
    rows = []
    for method, directory in {
        "pure_benders": "PURE_BENDERS",
        "aggregate_benders_structured_oracle": "AGGREGATE_BENDERS_STRUCTURED_ORACLE",
        "prb_benders": "PRB_BENDERS",
    }.items():
        reference = runner.read_json(runner.EXISTING_L_ROOT / directory / "result.json")
        rows.append(
            {
                "method": method,
                "objective": reference["solution"]["objective"],
                "certified": True,
            }
        )
    sanity = runner.gamma2_sanity(rows, config)
    assert sanity["pass"] is True
    assert len(sanity["checks"]) == 3
