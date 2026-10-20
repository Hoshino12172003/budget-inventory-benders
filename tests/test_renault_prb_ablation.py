from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from experiments import run_renault_prb_ablation as runner


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("method", tuple(runner.CONFIGS))
def test_protocols_are_closed_and_exactly_scoped(method: str) -> None:
    config = runner.load_config(runner.CONFIGS[method])
    assert config["formal_run_authorized"] is False
    assert tuple(config["case_ids"]) == runner.CASES
    assert config["fixed_scientific_parameters"] == {"Gamma": 2, "lambda_R": 0.05}
    assert config["algorithm"]["retain_product_budget_theta"] is True
    assert config["algorithm"]["retain_global_risk_budget_coupling"] is True
    assert config["algorithm"]["compact_global_oracle"] is False


def test_methods_form_the_declared_two_by_two_ablation() -> None:
    observed = {
        method: runner.load_config(path)["mechanisms"]
        for method, path in runner.CONFIGS.items()
    }
    assert observed == {
        "PRB-SG": {"adaptive_cut_selection": False, "exact_product_scenario_screening": True},
        "A-PRB": {"adaptive_cut_selection": True, "exact_product_scenario_screening": False},
        "A-PRB-SG": {"adaptive_cut_selection": True, "exact_product_scenario_screening": True},
    }


def test_runner_is_fail_closed_and_does_not_call_other_algorithms() -> None:
    source = inspect.getsource(runner)
    assert "formal_run_authorized" in source
    assert "refusing to overwrite" in source
    assert "solve_prb_ablation" in source
    assert "solve_prb_benders(" not in source
    assert "solve_pure" not in source
    assert "solve_standard" not in source


@pytest.mark.parametrize("method", tuple(runner.CONFIGS))
def test_dry_run_has_zero_optimization_calls(method: str) -> None:
    audit = runner.dry_run(runner.CONFIGS[method])
    assert audit["optimization_calls"] == 0
    assert audit["formal_run_authorized"] is False
    assert audit["gates"]["identity"]
    assert audit["gates"]["attempts_absent"]
    assert audit["gates"]["canonical_absent"]
