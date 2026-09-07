from __future__ import annotations

import json
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.formal_protocol import (
    RESULT_FIELDS,
    RunIdentity,
    canonical_hash,
    committed_file_sha256,
    load_formal_config,
    materialize_parameters,
    reconfiguration_budget_share,
    reconfiguration_intensity,
    require_formal_authorization,
    validate_formal_config,
    validate_result_row,
    validate_resume_identity,
)
from robust_inventory_reconfiguration.solver_profile import (
    FORMAL_SOLVER_NATIVE_PROFILE,
    FORMAL_SOLVER_PROFILE_ID,
    apply_formal_solver_profile,
)
from robust_inventory_reconfiguration.risk_budget_composition import (
    enumerate_gamma_allocations,
)


CONFIG_DIR = Path("experiments/configs/formal")


def configs():
    return [load_formal_config(path) for path in sorted(CONFIG_DIR.glob("e*.yaml"))]


def test_e1_to_e7_config_schema() -> None:
    loaded = configs()
    assert {config["experiment_id"] for config in loaded} == {
        "E1", "E2", "E3", "E4", "E5", "E6", "E7"
    }
    for config in loaded:
        validate_formal_config(config)


def test_all_formal_runs_are_unauthorized() -> None:
    for config in configs():
        assert config["formal_run_authorized"] is False
        with pytest.raises(PermissionError, match="not authorized"):
            require_formal_authorization(config)


def test_renault_case_identity_is_explicit_and_raw_only_case_is_not_substituted() -> None:
    assert all(config["case_ids"] == ["210202", "210628"] for config in configs())
    assert Path("data/formal_instances/210202.json").exists()
    assert Path("data/formal_instances/210628.json").exists()
    assert not Path("data/formal_instances/210712.json").exists()


def test_budget_gamma_lambda_parameter_propagation() -> None:
    assert materialize_parameters(
        b_ref=100.0, beta=0.9, gamma=4, lambda_r=0.05
    ) == {"B": 90.0, "Gamma": 4, "lambda_R": 0.05}


def test_ri_formula_uses_adjustment_variables_and_positive_x0() -> None:
    assert reconfiguration_intensity([[1.0, 2.0]], [[3.0, 0.0]], [[4.0, 2.0]]) == 1.0
    with pytest.raises(ValueError, match="must be positive"):
        reconfiguration_intensity([[0.0]], [[0.0]], [[0.0]])


def test_rs_uses_the_master_budget_denominator() -> None:
    assert reconfiguration_budget_share(5.0, 100.0) == 0.05
    with pytest.raises(ValueError, match="must be positive"):
        reconfiguration_budget_share(0.0, 0.0)


def test_e2_three_baseline_semantics() -> None:
    config = next(config for config in configs() if config["experiment_id"] == "E2")
    variants = {variant["id"]: variant for variant in config["variants"]}
    assert set(variants) == {
        "existing_system", "nominal_reconfiguration", "robust_reconfiguration"
    }
    assert variants["existing_system"]["fix_x_to_x0"] is True
    assert variants["nominal_reconfiguration"]["fix_x_to_x0"] is False
    assert variants["robust_reconfiguration"]["fix_x_to_x0"] is False


def test_nominal_gamma_is_zero_and_existing_system_fixes_x() -> None:
    config = next(config for config in configs() if config["experiment_id"] == "E2")
    variants = {variant["id"]: variant for variant in config["variants"]}
    assert variants["nominal_reconfiguration"]["Gamma"] == 0
    assert variants["existing_system"]["fix_x_to_x0"]


def test_e4_gamma_levels_are_supported_and_explicit() -> None:
    config = next(config for config in configs() if config["experiment_id"] == "E4")
    assert config["parameter_grid"]["Gamma"] == [0, 1, 2, 3, 4]
    for gamma in range(5):
        allocations = enumerate_gamma_allocations(8, gamma)
        assert allocations
        assert all(sum(allocation) <= gamma for allocation in allocations)


def test_formal_baseline_and_sensitivity_levels_are_frozen() -> None:
    freeze = json.loads(
        Path("experiments/configs/formal/formal_parameter_freeze.json").read_text(
            encoding="utf-8"
        )
    )
    assert freeze["baseline"] == {
        "beta": 1.0,
        "B": {"210202": 84614.30513135393, "210628": 50558.18771213083},
        "Gamma": 2,
        "lambda_R": 0.05,
    }
    assert freeze["levels"]["E3_beta"] == [0.8, 0.9, 1.0, 1.1, 1.2]
    assert freeze["levels"]["E4_Gamma"] == [0, 1, 2, 3, 4]
    assert freeze["levels"]["E5_lambda_R"] == [0.0, 0.0025, 0.01, 0.05, 0.2]
    assert freeze["levels"]["E6_beta"] == [0.8, 1.0, 1.2]
    assert freeze["levels"]["E6_Gamma"] == [0, 2, 4]
    assert freeze["levels"]["E7_Gamma"] == [0, 2, 4]
    assert freeze["levels"]["E7_lambda_R"] == [0.0025, 0.05, 0.2]
    for b_ref in freeze["B_ref"].values():
        assert all(beta * b_ref > 0 for beta in freeze["levels"]["E3_beta"])


def test_each_config_uses_beta_budget_provenance_and_shared_profile() -> None:
    for config in configs():
        assert config["budget_rule"] == "B = beta * B_ref_case"
        assert config["budget_reference_by_case"] == {
            "210202": 84614.30513135393,
            "210628": 50558.18771213083,
        }
        assert config["solver_profile_id"] == FORMAL_SOLVER_PROFILE_ID
        assert config["git_commit_at_execution"] == "CAPTURE_AT_EXECUTION"
        assert config["blockers"] == []
        assert config["formal_parameter_freeze_sha256"] == committed_file_sha256(
            "experiments/configs/formal/formal_parameter_freeze.json", Path.cwd()
        )


def test_formal_run_count_is_84_with_explicit_e1_breakdown() -> None:
    by_id = {config["experiment_id"]: config for config in configs()}
    assert {key: value["estimated_run_count"] for key, value in by_id.items()} == {
        "E1": 12, "E2": 6, "E3": 10, "E4": 10,
        "E5": 10, "E6": 18, "E7": 18,
    }
    assert sum(config["estimated_run_count"] for config in by_id.values()) == 84
    assert by_id["E1"]["run_count_breakdown"] == {
        "Renault": "2 cases * 2 methods = 4",
        "synthetic": "4 scales * 2 methods = 8",
    }


def test_direct_prb_identity_and_shared_tolerance_profile_pass() -> None:
    audit = json.loads(
        Path("experiments/audits/direct_prb_formulation_identity.json").read_text(
            encoding="utf-8"
        )
    )
    checks = audit["checks"]
    assert all(check["pass"] for check in checks.values())
    assert checks["same_solver_tolerances"]["profile_id"] == FORMAL_SOLVER_PROFILE_ID
    assert audit["overall_identity_pass"]


def test_shared_solver_profile_values_and_application() -> None:
    assert FORMAL_SOLVER_NATIVE_PROFILE == {
        "MIPGap": 0.0,
        "FeasibilityTol": 1e-8,
        "OptimalityTol": 1e-8,
        "IntFeasTol": 1e-8,
        "NumericFocus": 0,
        "BarConvTol": None,
    }

    class Parameters:
        pass

    class Model:
        Params = Parameters()

    apply_formal_solver_profile(Model(), mixed_integer=True)
    assert Model.Params.MIPGap == 0.0
    assert Model.Params.FeasibilityTol == 1e-8
    assert Model.Params.OptimalityTol == 1e-8
    assert Model.Params.IntFeasTol == 1e-8
    assert Model.Params.NumericFocus == 0


def test_direct_and_prb_solver_code_uses_the_shared_profile() -> None:
    for name in (
        "reconfiguration_model.py",
        "product_risk_budget_benders.py",
        "product_risk_subproblem.py",
    ):
        source = Path("src/robust_inventory_reconfiguration", name).read_text(
            encoding="utf-8"
        )
        assert "apply_formal_solver_profile" in source
        assert ".Params.FeasibilityTol =" not in source
        assert ".Params.OptimalityTol =" not in source


def test_output_schema_is_complete_and_nulls_are_explicit() -> None:
    schema = json.loads(
        Path("experiments/schemas/formal_result.schema.json").read_text(encoding="utf-8")
    )
    assert set(schema["required"]) == set(RESULT_FIELDS)
    row = {field: None for field in RESULT_FIELDS}
    row.update({
        "experiment_id": "E1",
        "case_id": "210202",
        "method": "prb_benders",
        "config_hash": "a",
        "source_data_hash": "b",
        "data_hash": "c",
        "parameter_hash": "c",
        "x0_hash": "d",
        "git_commit": "e",
        "python_version": "3.12",
    })
    validate_result_row(row)


def test_checkpoint_resume_identity() -> None:
    identity = RunIdentity("a", "b", "c", "d", "e", "f")
    checkpoint = identity.__dict__.copy()
    validate_resume_identity(checkpoint, identity)


@pytest.mark.parametrize("field", ["config_hash", "data_hash"])
def test_checkpoint_hash_mismatch_is_rejected(field) -> None:
    identity = RunIdentity("a", "b", "c", "d", "e", "f")
    checkpoint = identity.__dict__.copy()
    checkpoint[field] = canonical_hash({"different": field})
    with pytest.raises(ValueError, match=f"{field} mismatch"):
        validate_resume_identity(checkpoint, identity)


def test_no_formal_result_artifact_exists_during_protocol_freeze() -> None:
    assert not Path("experiments/results/formal").exists()


def test_protocol_audit_reports_ready_without_writing_results() -> None:
    from experiments.audit_protocol import audit

    result = audit()
    assert result["status"] == "PROTOCOL_READY"
    assert result["all_formal_runs_unauthorized"]
    assert result["formal_case_identity_pass"]
    assert not result["case_210712_in_formal_chain"]
    assert result["pr2_to_pr7_integrated_in_main"]
    assert result["formal_anchor_levels_frozen"]
    assert result["uncertainty_item_counts"] == {"210202": 96, "210628": 96}
    assert result["gamma_0_to_4_supported"]
    assert result["budget_baseline_freeze_pass"]
    assert result["gamma_baseline_freeze_pass"]
    assert result["lambda_baseline_freeze_pass"]
    assert result["e3_to_e7_level_freeze_pass"]
    assert result["direct_prb_formulation_identity_pass"]
    assert result["solver_tolerance_identity_pass"]
    assert result["evidence_hashes_pass"]
    assert result["formal_case_hashes_pass"]
    assert result["x0_hashes_pass"]
    assert result["parameter_freeze_hash_references_pass"]
    assert result["formal_total_run_count"] == 84
    assert result["blockers"] == []
    assert not result["formal_result_artifacts_written"]
