from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments/run_e1c_development_probe.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("e1c_development_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dry_run_is_exactly_scoped_and_has_no_optimization(monkeypatch) -> None:
    runner = load_runner()
    monkeypatch.setattr(
        runner,
        "preflight",
        lambda authorization: (_ for _ in ()).throw(AssertionError("dry run used memory gate")),
    )
    result = runner.dry_run()
    assert result["status"] == "DRY_RUN_PASS"
    assert result["optimization_calls"] == 0
    assert [row["scale"] for row in result["authorized_scales"]] == ["L", "XL_low"]
    assert result["method_order"] == list(runner.METHODS)
    assert result["memory_gate"] == {
        "preflight_gib": 18,
        "process_stop_gib": 14,
        "system_emergency_gib": 3,
    }


def test_preflight_fails_closed_below_18_gib(monkeypatch) -> None:
    runner = load_runner()
    authorization = runner.validate_authorization()

    class Memory:
        available = 17 * 2**30

    monkeypatch.setattr(runner.psutil, "virtual_memory", lambda: Memory())
    with pytest.raises(RuntimeError, match="E1C_RESOURCE_PREFLIGHT_BLOCKED"):
        runner.preflight(authorization)
