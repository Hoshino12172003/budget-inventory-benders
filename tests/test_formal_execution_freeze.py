from __future__ import annotations

import json
from pathlib import Path

import pytest

import experiments.run_e1b_pure_benders_local as pure_runner
import experiments.run_e1b_standard_benders_local as standard_runner
from robust_inventory_reconfiguration.formal_execution_freeze import require_protocol_not_frozen


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "experiments/configs/formal/formal_execution_freeze_v1.json"


def test_all_historical_true_authorizations_are_revoked() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    true_configs = []
    for path in (ROOT / "experiments/configs").rglob("*"):
        if path.suffix not in {".json", ".yaml", ".yml"}:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(value, dict) and value.get("formal_run_authorized") is True:
            true_configs.append(path.relative_to(ROOT).as_posix())
    assert set(registry["revoked_config_paths"]).issubset(true_configs)


@pytest.mark.parametrize(
    "runner,case",
    [(standard_runner, "210129"), (pure_runner, "210129")],
)
def test_runner_entry_points_fail_closed_before_solver(runner, case, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        runner,
        "solve_standard_benders" if runner is standard_runner else "solve_pure_benders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("optimizer invoked")),
    )
    with pytest.raises(PermissionError, match="FORMAL_PROTOCOL_FROZEN"):
        runner.validate_execution_gate(case, tmp_path)


def test_unknown_new_protocol_is_not_silently_revoked(tmp_path) -> None:
    config = ROOT / "experiments/configs/formal/formal_parameter_freeze.json"
    require_protocol_not_frozen(ROOT, config)
