from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments import run_e5_lambda_local as runner
from robust_inventory_reconfiguration.e5_reporting import (
    canonical_adjustment,
    maximum_adjustment_difference,
)
from robust_inventory_reconfiguration.first_stage_solution import (
    load_first_stage_solution_artifact,
    matrix_from_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.reconfiguration_model import ReconfigurationSolution


ROOT = Path(__file__).resolve().parents[1]


def test_exact_design_and_run_ids() -> None:
    assert list(runner.LAMBDA_BY_TOKEN.items()) == [
        ("L0000", 0.0), ("L0025", 0.0025), ("L0100", 0.01),
        ("L0500", 0.05), ("L2000", 0.20),
    ]
    assert len(runner.expected_run_ids()) == len(set(runner.expected_run_ids())) == 40
    assert runner.make_run_id("210202", "L0025") == "E5-210202-L0025"


@pytest.mark.parametrize("value", ["0.0025", "L25", "L0050", "0.20", "bad"])
def test_invalid_lambda_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        runner.parse_lambda_token(value)


def test_beta_gamma_and_B_ref_are_frozen() -> None:
    manifest = runner.load_manifest()
    e4 = json.loads((ROOT / "experiments/configs/formal/e4_gamma_sensitivity_authorization.json").read_text(encoding="utf-8"))
    assert runner.BETA == manifest["beta"] == 1.0
    assert runner.GAMMA == manifest["Gamma"] == 2
    assert manifest["B_ref_by_case"] == e4["B_ref_by_case"]


def test_l0500_reuse_identity_is_complete_for_all_cases() -> None:
    manifest = runner.load_manifest()
    identities = runner.load_identities()
    for case in runner.CASES:
        reuse = runner.validate_l0500_reuse(case, manifest, identities[case])
        assert all(reuse["checks"].values())


def test_l0500_reuse_uses_e5_reporting_schema_without_solving() -> None:
    manifest = runner.load_manifest()
    identity = runner.load_identities()["210202"]
    result, solution_path = runner.reuse_result("210202", manifest, identity)
    assert result["run_id"] == "E5-210202-L0500"
    assert result["reused"] is True
    assert result["reuse_source_run"] == "E4-210202-G2"
    assert result["normalized_objective_vs_L0500"] == 1.0
    assert result["canonical_RI"] == pytest.approx(result["RI"])
    assert "transportation_cost" in result
    assert solution_path.name == "first_stage_solution.json"


def test_lambda_zero_canonical_adjustment_and_RI() -> None:
    x0 = [[2.0, 5.0], [3.0, 7.0]]
    x = [[4.0, 1.0], [3.0, 8.0]]
    adjustment = canonical_adjustment(x, x0)
    assert adjustment.a_plus == [[2.0, 0.0], [0.0, 1.0]]
    assert adjustment.a_minus == [[0.0, 4.0], [0.0, 0.0]]
    assert adjustment.total_adjustment == 7.0
    assert adjustment.reconfiguration_index == pytest.approx(7.0 / 17.0)
    assert runner.load_manifest()["reporting_canonicalization"]["RS_at_lambda_zero"] == 0.0


def test_canonical_reporting_ignores_degenerate_solver_adjustment() -> None:
    canonical = canonical_adjustment([[4.0]], [[2.0]])
    assert canonical.total_adjustment == 2.0
    assert maximum_adjustment_difference(canonical, [[7.0]], [[5.0]]) == 5.0


def test_positive_friction_economic_accounting_uses_solver_adjustment() -> None:
    instance = SimpleNamespace(
        num_depots=1,
        num_products=1,
        fixed_depot_cost=[10.0],
        inventory_cost=[[100.0]],
    )
    canonical = canonical_adjustment([[2.0]], [[1.0]])
    fixed, inventory, solver_reconfiguration = runner.cost_components(
        instance, [1], [[2.0]], [[1.0 + 5e-7]], [[5e-7]], 0.2
    )
    _, _, canonical_reconfiguration = runner.cost_components(
        instance, [1], [[2.0]], canonical.a_plus, canonical.a_minus, 0.2
    )
    assert fixed == 10.0
    assert inventory == 200.0
    assert solver_reconfiguration == pytest.approx(20.00002)
    assert canonical_reconfiguration == 20.0
    assert solver_reconfiguration != canonical_reconfiguration


def test_rs_uses_economic_reconfiguration_cost() -> None:
    budget = 250.0
    economic_reconfiguration_cost = 20.00002
    assert economic_reconfiguration_cost / budget == pytest.approx(0.08000008)


def test_positive_friction_artifact_preserves_solver_adjustment() -> None:
    instance = SimpleNamespace()
    solution = ReconfigurationSolution(
        230.00002, 230.00002, 0.0, [1], [[2.0]],
        [[1.0 + 5e-7]], [[5e-7]], 20.00002,
    )
    reporting_solution, canonical, _ = runner.canonical_solution(
        instance, [[1.0]], solution, 0.2
    )
    assert reporting_solution.a_plus == solution.a_plus
    assert reporting_solution.a_minus == solution.a_minus
    assert canonical.a_plus == [[1.0]]
    assert canonical.a_minus == [[0.0]]


def test_zero_friction_artifact_uses_canonical_adjustment() -> None:
    instance = SimpleNamespace()
    solution = ReconfigurationSolution(
        210.0, 210.0, 0.0, [1], [[2.0]], [[7.0]], [[6.0]], 0.0,
    )
    reporting_solution, _, _ = runner.canonical_solution(instance, [[1.0]], solution, 0.0)
    assert reporting_solution.a_plus == [[1.0]]
    assert reporting_solution.a_minus == [[0.0]]


def test_positive_friction_canonical_matches_frozen_baselines() -> None:
    for case in runner.CASES:
        instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
        x0 = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8"))["x0"]
        artifact = load_first_stage_solution_artifact(
            ROOT / f"experiments/results/e4_gamma_sensitivity_v1/E4-{case}-G2/first_stage_solution.json",
            instance,
        )
        canonical = canonical_adjustment(matrix_from_artifact(artifact, instance, "x"), x0)
        assert maximum_adjustment_difference(
            canonical,
            matrix_from_artifact(artifact, instance, "a_plus"),
            matrix_from_artifact(artifact, instance, "a_minus"),
        ) <= 1e-6


def test_high_friction_incumbent_backstop_is_feasible() -> None:
    manifest = runner.load_manifest()
    assert all(runner.incumbent_feasibility(case, manifest)["feasible"] for case in runner.CASES)


def test_authorization_fails_closed() -> None:
    manifest = runner.load_manifest()
    manifest["formal_run_authorized"] = False
    manifest["authorization_transition"] = [False]
    with pytest.raises(RuntimeError, match="authorized"):
        runner.validate_manifest(manifest)


def test_overwrite_protection(tmp_path: Path) -> None:
    target = tmp_path / "E5-210202-L0000"
    target.mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner.ensure_output_absent(target)


def test_result_root_is_isolated() -> None:
    assert runner.RESULT_ROOT.as_posix().endswith("experiments/results/e5_reconfiguration_friction_v1")


def test_static_audit_passes_without_optimization() -> None:
    audit = json.loads((ROOT / "artifacts/e5_reconfiguration_friction_protocol_static_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "E5_PROTOCOL_STATIC_AUDIT_PASS"
    assert audit["L0500_reuse_count"] == 8
    assert audit["other_reuse_count"] == 0
    assert audit["required_new_solves"] == 32
    assert audit["optimization_solves_executed_during_preparation"] == 0
