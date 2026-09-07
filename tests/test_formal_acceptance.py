from __future__ import annotations

import copy
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.formal_acceptance import (
    AUTHORIZED_RUN_IDS,
    acceptance_output_path,
    validate_acceptance_manifest,
    validate_formal_result_shape,
)
from robust_inventory_reconfiguration.formal_protocol import RESULT_FIELDS, load_formal_config


MANIFEST = Path("experiments/configs/formal_acceptance_batch_1.yaml")


def manifest() -> dict:
    return load_formal_config(MANIFEST)


def test_acceptance_authorization_is_exactly_five_runs_for_210202() -> None:
    value = manifest()
    validate_acceptance_manifest(value)
    assert tuple(value["authorized_run_ids"]) == AUTHORIZED_RUN_IDS
    assert value["case_ids"] == ["210202"]
    assert value["full_e1_e7_authorization"] is False


def test_wildcard_or_extra_run_authorization_is_rejected() -> None:
    value = copy.deepcopy(manifest())
    value["authorized_run_ids"] = ["*"]
    with pytest.raises(ValueError, match="exact run allowlist"):
        validate_acceptance_manifest(value)


def test_parameter_or_case_drift_is_rejected() -> None:
    value = copy.deepcopy(manifest())
    value["runs"][1]["Gamma"] = 1
    with pytest.raises(ValueError, match="A2 parameters"):
        validate_acceptance_manifest(value)
    value = copy.deepcopy(manifest())
    value["case_ids"] = ["210202", "210628"]
    with pytest.raises(ValueError, match="restricted"):
        validate_acceptance_manifest(value)


def test_output_path_is_the_nonoverwriting_authorized_attempt() -> None:
    root = Path.cwd().resolve()
    assert acceptance_output_path(root, manifest()) == (
        root / "experiments/results/formal_acceptance_batch_1/attempt_001"
    ).resolve()
    value = copy.deepcopy(manifest())
    value["output_directory"] = "experiments/results/formal"
    with pytest.raises(ValueError, match="outside the authorized attempt"):
        acceptance_output_path(root, value)


def test_acceptance_result_shape_reuses_formal_schema_fields() -> None:
    row = {field: None for field in RESULT_FIELDS}
    validate_formal_result_shape(row, RESULT_FIELDS)
    row["unexpected"] = True
    with pytest.raises(ValueError, match="schema mismatch"):
        validate_formal_result_shape(row, RESULT_FIELDS)


def test_full_e1_e7_configs_remain_unauthorized() -> None:
    for path in Path("experiments/configs/formal").glob("e*.yaml"):
        assert load_formal_config(path)["formal_run_authorized"] is False
