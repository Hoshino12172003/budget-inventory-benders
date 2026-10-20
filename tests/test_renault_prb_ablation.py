from __future__ import annotations

import inspect
from pathlib import Path
import shutil

import pytest
import psutil

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
    assert config["known_failure_policy"]["classification"] == "NUMERICAL_CERTIFICATION_FAIL"
    assert config["known_failure_policy"]["coupling_residual_must_exceed"] == 1e-6
    assert config["known_failure_policy"]["maximum_numerical_closure_residual"] == 1e-4
    if method == "PRB-SG":
        assert config["execution_plan"]["210129"] == {
            "action": "preserve_canonical",
            "attempt": "attempt-002",
            "result_sha256": "41a9ea2c66a05153a10d2d80eb431d18a9fdd86bd8dd8fc5455e39cf56ef6441",
        }
        assert config["execution_plan"]["210202"]["action"] == "preserve_canonical"
        assert config["execution_plan"]["210628"]["action"] == "preserve_canonical"
        assert config["execution_plan"]["210310"]["action"] == "preserve_canonical"
        assert config["execution_plan"]["210330"]["action"] == "preserve_numerical_failure"
        assert tuple(
            case
            for case, plan in config["execution_plan"].items()
            if plan["action"] == "run"
        ) == ("210323", "210428", "210611")


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


def test_resource_monitor_tolerates_worker_exit_race() -> None:
    class ExitedProcess:
        def children(self, recursive: bool):
            raise psutil.NoSuchProcess(12345)

    assert runner.tree_rss(ExitedProcess()) == 0


def test_preserved_210330_is_independently_classified_and_unknown_failure_stops(
    tmp_path: Path,
) -> None:
    config = runner.load_config(runner.CONFIGS["PRB-SG"])
    plan = config["execution_plan"]["210330"]
    attempt = (
        ROOT
        / config["output_directory"]
        / "worker_logs"
        / "PRB_SG_RENAULT_210330"
        / plan["attempt"]
    )
    audit = runner.coupling_only_failure_audit(
        config,
        attempt,
        "PRB_SG_RENAULT_210330",
        expected_artifact_sha256=plan["artifact_sha256"],
        expected_config_sha256=plan["config_sha256"],
        expected_code_commit=plan["code_commit"],
    )
    assert audit["pass"]
    assert audit["classification"] == "NUMERICAL_CERTIFICATION_FAIL"
    assert runner.continuation_allowed(audit["classification"])

    incomplete = tmp_path / "attempt"
    shutil.copytree(attempt, incomplete)
    (incomplete / "solver.log").unlink()
    rejected = runner.coupling_only_failure_audit(
        config, incomplete, "PRB_SG_RENAULT_210330"
    )
    assert rejected["pass"] is False
    assert rejected["classification"] == "INTEGRITY_FAILURE"
    assert runner.continuation_allowed(rejected["classification"]) is False


@pytest.mark.parametrize("method", tuple(runner.CONFIGS))
def test_dry_run_has_zero_optimization_calls(method: str) -> None:
    audit = runner.dry_run(runner.CONFIGS[method])
    assert audit["optimization_calls"] == 0
    assert audit["formal_run_authorized"] is False
    assert audit["gates"]["identity"]
