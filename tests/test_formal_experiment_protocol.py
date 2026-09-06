from __future__ import annotations

import json
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.formal_protocol import (
    RESULT_FIELDS,
    RunIdentity,
    canonical_hash,
    load_formal_config,
    materialize_parameters,
    reconfiguration_budget_share,
    reconfiguration_intensity,
    require_formal_authorization,
    validate_formal_config,
    validate_result_row,
    validate_resume_identity,
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


def test_renault_case_identity_is_explicit_and_missing_case_is_not_substituted() -> None:
    assert all(config["case_ids"] == ["210202", "210712"] for config in configs())
    assert Path("data/formal_instances/210202.json").exists()
    assert not Path("data/formal_instances/210712.json").exists()
    assert Path("data/formal_instances/210628.json").exists()


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


def test_direct_prb_identity_audit_exposes_only_known_tolerance_blocker() -> None:
    audit = json.loads(
        Path("experiments/audits/direct_prb_formulation_identity.json").read_text(
            encoding="utf-8"
        )
    )
    checks = audit["checks"]
    assert all(
        check["pass"]
        for name, check in checks.items()
        if name != "same_solver_tolerances"
    )
    assert not checks["same_solver_tolerances"]["pass"]
    assert not audit["overall_identity_pass"]


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


def test_protocol_audit_reports_blockers_without_writing_results() -> None:
    from experiments.audit_protocol import audit

    result = audit()
    assert result["status"] == "BLOCKED"
    assert result["all_formal_runs_unauthorized"]
    assert not result["case_210712_available"]
    assert not result["pr2_to_pr7_integrated_in_main"]
    assert not result["formal_anchor_levels_frozen"]
    assert not result["direct_prb_formulation_identity_pass"]
    assert not result["formal_result_artifacts_written"]
