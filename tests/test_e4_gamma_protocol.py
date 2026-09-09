from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import experiments.run_e4_gamma_local as runner
from robust_inventory_reconfiguration.robust_service import ScenarioServiceResult, UnifiedServiceResult
from scripts.audit_e4_gamma_protocol import build_audit


ROOT = Path(__file__).resolve().parents[1]


def manifest() -> dict:
    return json.loads(runner.MANIFEST.read_text(encoding="utf-8"))


def test_exact_design_and_run_ids() -> None:
    value = manifest()
    runner.validate_manifest(value)
    assert runner.GAMMA_GRID == (0, 1, 2, 3, 4)
    assert len(runner.expected_run_ids()) == len(set(runner.expected_run_ids())) == 40
    assert runner.expected_run_ids() == value["authorized_run_ids"]
    assert runner.make_run_id("210202", 3) == "E4-210202-G3"


@pytest.mark.parametrize("value", ("-1", "5", "2.0", "x"))
def test_invalid_gamma_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="gamma must be one of"):
        runner.parse_gamma(value)


def test_case_validation_and_authorization_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown E4 case"):
        runner.validate_gate("not-a-case", 2)
    value = manifest()
    if value["formal_run_authorized"]:
        value["formal_run_authorized"] = False
        value["authorization_transition"] = [False]
    original = runner.load_manifest
    try:
        runner.load_manifest = lambda: value
        with pytest.raises(PermissionError, match="E4_FORMAL_RUN_NOT_AUTHORIZED"):
            runner.validate_gate("210202", 2)
    finally:
        runner.load_manifest = original


def test_beta_lambda_and_B_ref_are_frozen() -> None:
    value = manifest()
    assert value["beta"] == runner.BETA == 1.0
    assert value["lambda_R"] == runner.LAMBDA_R == 0.05
    identities = runner.load_identities()
    for case in runner.CASES:
        runner.validate_case_identity(case, value, identities[case])
    for key, changed in (("beta", 0.9), ("lambda_R", 0.1)):
        modified = copy.deepcopy(value)
        modified[key] = changed
        with pytest.raises(RuntimeError, match="BLOCK_E4_MANIFEST_IDENTITY"):
            runner.validate_manifest(modified)


def test_G2_reuse_identity_is_complete_for_all_cases() -> None:
    value = manifest()
    identities = runner.load_identities()
    checks = [runner.validate_g2_reuse(case, value, identities[case])["checks"] for case in runner.CASES]
    assert len(checks) == 8
    assert all(all(case_checks.values()) for case_checks in checks)


def test_G0_reuse_is_not_identity_safe() -> None:
    value = manifest()
    identities = runner.load_identities()
    audits = [runner.classify_g0_reuse(case, value, identities[case]) for case in runner.CASES]
    assert all(audit["classification"] == "E4_G0_REUSE_NOT_IDENTITY_SAFE" for audit in audits)
    assert sum(audit["eligible"] for audit in audits) == 0
    assert all("full_first_stage_artifact" in audit["failed_identity_evidence"] for audit in audits)


def test_result_root_is_isolated_and_narrowly_ignored() -> None:
    assert runner.subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e4_gamma_sensitivity_v1/probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    assert runner.subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e4-not-in-scope/probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode != 0


def test_no_overwrite_behavior(monkeypatch, tmp_path: Path) -> None:
    value = manifest()
    value["formal_run_authorized"] = True
    value["authorization_transition"] = [False, True]
    monkeypatch.setattr(runner, "load_manifest", lambda: value)
    monkeypatch.setattr(runner, "source_model_identity", lambda revision=None: value["model_identity_sha256"])
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *args, **kwargs: b"")
    (tmp_path / "E4-210202-G2").mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner.validate_gate("210202", 2, tmp_path)


def test_static_audit_passes_without_outputs_or_solves() -> None:
    audit = build_audit()
    assert audit["status"] == "E4_PROTOCOL_STATIC_AUDIT_PASS"
    assert audit["verified_Gamma2_reuse_count"] == 8
    assert audit["verified_Gamma0_reuse_count"] == 0
    assert audit["required_new_solve_count"] == 32
    assert audit["existing_E4_outputs"] == []
    assert audit["optimization_solves_executed_during_preparation"] == 0
    assert audit["fixed_first_stage_evaluations_executed_during_preparation"] == 0


def test_Gamma0_reporting_uses_canonical_transportation_cost(monkeypatch) -> None:
    case = "210202"
    value = manifest()
    identity = runner.load_identities()[case]
    x0_artifact = json.loads(
        (ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8")
    )
    x0, y0 = x0_artifact["x0"], x0_artifact["y0"]
    zeros = [[0.0 for _ in x0[0]] for _ in x0]
    solution = SimpleNamespace(
        x=x0, y=y0, a_plus=zeros, a_minus=zeros,
        objective=0.0, first_stage_expenditure=0.0,
        robust_recourse_cost=7.0, reconfiguration_cost=0.0,
    )
    solved = SimpleNamespace(
        status="OPTIMAL", exact_certification_pass=True, solution=solution,
        total_runtime=0.0, iterations=[], master_solve_count=1,
        product_subproblem_evaluations=0, unique_product_cuts=0,
        final_lower_bound=0.0, final_upper_bound=0.0, final_relative_gap=0.0,
        global_risk_budget_coupling_pass=True,
    )
    scenario = ScenarioServiceResult(
        shock_set=(), recourse_cost=7.0, transportation_cost=1.25,
        shortage_cost=2.0, service_penalty_cost=3.75, total_shortage=4.0,
        minimum_fill_rate=0.8, average_fill_rate=0.9, worst_region_id="1",
    )
    service = UnifiedServiceResult(
        robust_recourse_cost=7.0, worst_recourse_scenario=scenario,
        worst_shortage_scenario=scenario, worst_service_scenario=scenario,
        scenario_count=1, scenarios=(scenario,),
    )
    monkeypatch.setattr(runner, "solve_prb_benders", lambda *args: solved)
    monkeypatch.setattr(runner, "evaluate_robust_service_detailed", lambda *args: service)
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *args, **kwargs: "test-commit\n")

    result, _ = runner.solved_result(case, 0, value, identity)

    assert scenario.transportation_cost == 1.25
    assert result["Gamma"] == 0
    assert result["transport_cost"] == 1.25
    assert "transportation_cost" not in result
    assert result["certification_status"] == "CERTIFIED_PRB_EXACT"


def test_Gamma2_reuse_reporting_schema_is_unchanged() -> None:
    case = "210202"
    value = manifest()
    result, solution_path = runner.reused_g2_result(case, value, runner.load_identities()[case])
    assert result["Gamma"] == 2
    assert "transport_cost" in result
    assert result["exact_certification_pass"] is True
    assert solution_path.name == "first_stage_solution.json"
