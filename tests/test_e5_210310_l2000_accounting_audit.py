from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = json.loads(
    (ROOT / "artifacts/e5_210310_l2000_accounting_audit.json").read_text(encoding="utf-8")
)


def test_failure_was_post_solve_accounting_only() -> None:
    boundary = AUDIT["failure_boundary"]
    assert boundary["primary_optimization_valid"] is True
    assert boundary["primary_status"] == "OPTIMAL"
    assert boundary["exact_certification_pass"] is True
    assert boundary["accounting_only_failure"] is True
    assert boundary["write_run_reached_before_failure"] is False
    assert boundary["partial_artifact_found"] is False


def test_solver_accounting_closes_and_canonical_accounting_explains_failure() -> None:
    run = AUDIT["verification_run"]
    gate = AUDIT["original_gate"]
    assert abs(run["solver_based_accounting_error"]) < gate["absolute_tolerance"]
    assert abs(run["canonical_based_accounting_error"]) > gate["absolute_tolerance"]
    assert run["solver_reconfiguration_cost_residual"] == 0.0
    assert run["solver_first_stage_cost"] + run["exact_robust_recourse"] == pytest.approx(
        run["reconstructed_total_objective"], abs=1e-12
    )


def test_high_friction_difference_is_near_zero_adjustment_noise() -> None:
    run = AUDIT["verification_run"]
    assert AUDIT["numerical_source"]["lambda_R"] == 0.2
    assert run["max_solver_canonical_adjustment_difference"] < 1e-6
    assert run["canonical_reconfiguration_cost"] - run["solver_reconfiguration_cost"] == pytest.approx(
        run["canonical_based_accounting_error"] - run["solver_based_accounting_error"]
    )


def test_fix_preserves_frozen_contract_and_prior_results() -> None:
    fix = AUDIT["fix"]
    preservation = AUDIT["preservation"]
    assert AUDIT["classification"] == "CANONICAL_REPORTING_VS_SOLVER_ACCOUNTING_MISMATCH"
    assert fix["accounting_tolerance_changed"] is False
    assert fix["model_changed"] is False
    assert preservation["completed_E5_files_changed"] == 0
    assert all(
        preservation[f"E{experiment}_overwritten"] is False
        for experiment in range(1, 5)
    )
