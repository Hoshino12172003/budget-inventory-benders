from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments/run_prb_j_scaling_development.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("prb_j_scaling_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_static_audit_freezes_full_j_grid_before_results() -> None:
    runner = load_runner()
    audit = runner.static_audit()
    assert audit["status"] == "STATIC_AUDIT_PASS"
    assert audit["optimization_calls"] == 0
    assert audit["grid"] == [12, 24, 48, 96]
    assert [row["prb_product_risk_blocks"] for row in audit["rows"]] == [3612, 7224, 14448, 28896]
    assert [row["pure_binary_variables"] for row in audit["rows"]] == [288, 576, 1152, 2304]
    assert audit["j96_decision"] == "SAFE_TO_ATTEMPT_UNDER_FROZEN_MONITOR"


def test_dry_run_has_twelve_methods_and_three_preparations() -> None:
    runner = load_runner()
    dry = runner.dry_run()
    assert dry["status"] == "DRY_RUN_PASS"
    assert dry["optimization_calls"] == 0
    assert dry["reused_prepare"] == 12
    assert dry["preparation_runs"] == [24, 48, 96]
    assert len(dry["method_conditions"]) == 12


def test_resource_preflight_fails_closed(monkeypatch) -> None:
    runner = load_runner()
    config = runner.validate_config()

    class Memory:
        available = 17 * 2**30

    monkeypatch.setattr(runner.psutil, "virtual_memory", lambda: Memory())
    with pytest.raises(RuntimeError, match="PRB_J_SCALING_PREFLIGHT_BLOCKED"):
        runner.preflight(config)


def test_development_runner_uses_exact_bound_fixes_for_large_canonical_baselines() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "continuous_fix_tolerance=config[\"canonical_continuous_fix_tolerance\"]" in source
    assert "PARTIAL_PREDECLARED_GRID" in source
