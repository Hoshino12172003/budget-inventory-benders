from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

import experiments.run_e6_budget_risk_local as runner
from scripts.audit_e6_budget_risk_protocol import build_audit
from scripts.summarize_e6_budget_risk_results import interaction_contrast_for_case


ROOT = Path(__file__).resolve().parents[1]


def manifest() -> dict:
    return runner.load_manifest()


def test_only_frozen_tokens_are_accepted() -> None:
    assert runner.parse_beta_token("B080") == "B080"
    assert runner.parse_gamma_token("G4") == "G4"
    for value in ("B80", "B090", "0.8"):
        with pytest.raises(ValueError, match="beta token"):
            runner.parse_beta_token(value)
    for value in ("G1", "4", "G04"):
        with pytest.raises(ValueError, match="Gamma token"):
            runner.parse_gamma_token(value)


def test_exact_72_condition_grid_has_no_duplicates() -> None:
    conditions = runner.enumerate_conditions()
    assert len(conditions) == len({condition.run_id for condition in conditions}) == 72
    assert conditions[0].run_id == "E6-210202-B080-G0"
    assert conditions[-1].run_id == "E6-210611-B120-G4"


def test_manifest_freezes_identity_and_authorizes_only_e6() -> None:
    value = manifest()
    runner.validate_manifest(value)
    assert value["formal_run_authorized"] is True
    assert value["authorization_transition"] == [False, True]
    assert value["authorization_scope"] == ["E6_BUDGET_RISK_INTERACTION_V1"]
    assert value["authorization_exclusions"] == [
        "E7", "SCALING", "STANDARD_BENDERS", "FUTURE_EXPERIMENTS"
    ]
    assert value["lambda_R"] == runner.LAMBDA_R == 0.05
    assert value["materiality_tolerance"] == 1e-6
    assert value["solver_profile"] == "gurobi-balanced-1e-8-v1"


def test_reuse_plan_is_derived_and_overlap_counted_once() -> None:
    plan = runner.build_reuse_plan(manifest())
    reused = [row for row in plan if row["classification"] == "REUSE"]
    new = [row for row in plan if row["classification"] == "NEW_SOLVE"]
    overlaps = [row for row in plan if len(row["source_candidates"]) == 2]
    assert len(reused) == 40
    assert len(new) == 32
    assert len(overlaps) == 8
    assert all(row["beta_token"] == "B100" and row["Gamma_token"] == "G2" for row in overlaps)
    assert all(row["selected_source_experiment"] == "E3" for row in overlaps)


def test_reuse_sources_are_exactly_e3_and_e4() -> None:
    plan = runner.build_reuse_plan(manifest())
    cells = {
        (row["beta_token"], row["Gamma_token"], row["selected_source_experiment"])
        for row in plan if row["classification"] == "REUSE"
    }
    assert cells == {
        ("B080", "G2", "E3"),
        ("B100", "G0", "E4"),
        ("B100", "G2", "E3"),
        ("B100", "G4", "E4"),
        ("B120", "G2", "E3"),
    }


def test_reuse_provenance_mismatch_fails_closed() -> None:
    value = copy.deepcopy(manifest())
    value["instance_hashes"]["210202"] = "0" * 64
    with pytest.raises(RuntimeError, match="BLOCK_E6_CASE_IDENTITY"):
        runner.build_reuse_plan(value)


def test_source_provenance_tampering_is_rejected(tmp_path: Path) -> None:
    source_dir = runner.E3_ROOT / "E3-210202-B080"
    copied = tmp_path / source_dir.name
    copied.mkdir()
    for name in ("result.json", "first_stage_solution.json", "provenance.json"):
        shutil.copy2(source_dir / name, copied / name)
    provenance_path = copied / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["runner_sha256"] = "0" * 64
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    source = runner.source_descriptor(copied)
    condition = runner.Condition("210202", "B080", "G2")
    with pytest.raises(RuntimeError, match="BLOCK_E6_REUSE_IDENTITY_MISMATCH"):
        runner.validate_reuse_candidate(
            condition,
            source,
            manifest(),
            runner.load_identities()["210202"],
        )


def test_dry_run_never_invokes_optimizer(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "solve_prb_benders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("optimizer invoked")),
    )
    audit = runner.dry_run()
    assert audit["status"] == "E6_DRY_RUN_PASS"
    assert audit["optimization_solver_invocations"] == 0
    assert (audit["total_conditions"], audit["reusable_conditions"], audit["new_solve_conditions"]) == (72, 40, 32)


def test_other_experiments_remain_unauthorized() -> None:
    e7 = json.loads(
        (ROOT / "experiments/configs/formal/e7_risk_friction_interaction.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert e7["formal_run_authorized"] is False


def test_overwrite_prevention(tmp_path: Path) -> None:
    run_id = runner.enumerate_conditions()[0].run_id
    (tmp_path / run_id).mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner.check_output_target(run_id, tmp_path)


def test_result_namespace_is_narrowly_ignored() -> None:
    assert runner.subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e6_budget_risk_interaction_v1/probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    assert runner.subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e6-not-in-scope/probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode != 0


def test_case_identity_B_ref_x0_and_mapping_are_unchanged() -> None:
    value = manifest()
    identities = runner.load_identities()
    for case in runner.CASES:
        runner.validate_case_identity(case, value, identities[case])


def synthetic_interaction_rows() -> list[dict]:
    rows = []
    for beta in (0.8, 1.0, 1.2):
        for gamma in (0, 2, 4):
            rows.append(
                {
                    "case": "test",
                    "beta": beta,
                    "Gamma": gamma,
                    "RI": (1.2 - beta) * gamma,
                    "objective": 100 + (2 - beta) * gamma,
                    "robust_recourse_cost": 50 + (1.5 - beta) * gamma,
                    "RS": 0.01 * gamma,
                    "budget_slack": 10.0 if beta == 1.2 and gamma == 0 else 0.0,
                    "material_reconfiguration": gamma > 0,
                }
            )
    return rows


def test_interaction_contrast_and_DID_math() -> None:
    row = interaction_contrast_for_case("test", synthetic_interaction_rows(), 1e-6, 1e-6)
    assert row["delta_Gamma_RI_B080"] == pytest.approx(1.6)
    assert row["delta_Gamma_RI_B120"] == pytest.approx(0.0)
    assert row["DID_RI_tight_vs_relaxed"] == pytest.approx(1.6)
    assert row["DID_objective_tight_vs_relaxed"] == pytest.approx(1.6)
    assert row["DID_recourse_tight_vs_relaxed"] == pytest.approx(1.6)
    assert row["B120_risk_consumes_financial_slack"] is True
    assert "SCARCITY_AMPLIFIES_RISK_RESPONSE" in row["mechanism_classification"]


def test_budget_binding_classification_uses_frozen_tolerance() -> None:
    value = manifest()
    assert value["budget_binding_tolerance"] == 1e-6
    rows = synthetic_interaction_rows()
    rows[-1]["budget_slack"] = 2e-6
    row = interaction_contrast_for_case("test", rows, 1e-6, value["budget_binding_tolerance"])
    assert row["B120_risk_consumes_financial_slack"] is False


def test_static_preflight_passes_without_optimization() -> None:
    value = manifest()
    checks = [runner.static_feasibility(case, value) for case in runner.CASES]
    assert len(checks) == 8
    assert all(row["corner"].endswith("B080-G4") and row["feasible"] for row in checks)
    assert all(row["optimization_executed"] is False for row in checks)


def test_static_audit_passes_and_reports_zero_solves() -> None:
    reuse, audit = build_audit()
    assert audit["status"] == "E6_PROTOCOL_STATIC_AUDIT_PASS"
    assert (audit["total_conditions"], audit["reusable_conditions"], audit["new_solve_conditions"]) == (72, 40, 32)
    assert reuse["reuse_parameter_cells"] == ["B080-G2", "B100-G0", "B100-G2", "B100-G4", "B120-G2"]
    assert audit["formal_first_stage_optimization_solves_executed"] == 0
    assert audit["fixed_first_stage_evaluations_executed"] == 0
    assert audit["formal_run_authorized"] is True
    assert audit["checks"]["authorization_scope_E6_only"] is True


def test_future_reporting_outputs_are_not_fabricated() -> None:
    for name in (
        "e6_table_budget_risk_interaction_case_level.csv",
        "e6_table_budget_risk_interaction_aggregate.csv",
        "e6_table_interaction_contrasts.csv",
        "fig_e6_ri_interaction.png",
    ):
        assert not (ROOT / "artifacts" / name).exists()


@pytest.mark.parametrize(
    ("condition", "source_run"),
    [
        (runner.Condition("210202", "B080", "G2"), "E3-210202-B080"),
        (runner.Condition("210202", "B100", "G0"), "E4-210202-G0"),
    ],
)
def test_reused_result_conforms_to_frozen_schema(condition, source_run) -> None:
    value = manifest()
    result, solution = runner.build_reused_result(
        condition, value, runner.load_identities()[condition.case]
    )
    schema = json.loads(
        (ROOT / value["result_schema"]).read_text(encoding="utf-8")
    )
    assert set(schema["required"]) <= set(result)
    assert result["reuse_source_run"] == source_run
    assert result["exact_certification_pass"] is True
    assert solution.name == "first_stage_solution.json"
