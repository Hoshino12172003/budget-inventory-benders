from __future__ import annotations

from pathlib import Path

from robust_inventory_reconfiguration.e1_formal import (
    E1_NEW_RUN_IDS,
    E1_RESULT_FIELDS,
    e1_output_path,
    synthetic_reproducibility_audit,
    validate_e1_authorization,
)
from robust_inventory_reconfiguration.formal_protocol import load_formal_config
from experiments.run_e1_formal import E1_CONFIG, FREEZE, reuse_identity_audit, reused_rows


ROOT = Path(__file__).resolve().parents[1]


def test_e1_authorization_is_exactly_ten_new_runs() -> None:
    manifest = load_formal_config(
        ROOT / "experiments" / "configs" / "e1_formal_authorization_attempt_001.yaml"
    )
    validate_e1_authorization(manifest)
    assert tuple(manifest["authorized_run_ids"]) == E1_NEW_RUN_IDS
    assert manifest["e2_e7_authorization"] is False
    assert e1_output_path(ROOT, manifest).name == "attempt_001"
    retry = load_formal_config(
        ROOT / "experiments" / "configs" / "e1_formal_authorization_attempt_002.yaml"
    )
    validate_e1_authorization(retry)
    assert e1_output_path(ROOT, retry).name == "attempt_002"


def test_synthetic_reproducibility_gate_blocks_design_only_config() -> None:
    ladder = load_formal_config(ROOT / "experiments" / "configs" / "synthetic_scaling_ladder.json")
    audit = synthetic_reproducibility_audit(ladder)
    assert audit["status"] == "BLOCK_E1_SYNTHETIC_REPRODUCIBILITY"
    assert audit["checks"]["dimensions_frozen"]
    assert audit["checks"]["seed_frozen"]
    assert not audit["checks"]["generator_implementation_frozen"]
    assert not audit["checks"]["budget_construction_frozen"]


def test_e1_result_schema_contains_common_and_method_fields() -> None:
    assert len(E1_RESULT_FIELDS) == len(set(E1_RESULT_FIELDS))
    for field in (
        "first_stage_solution_hash",
        "unique_product_cuts",
        "product_subproblem_solves",
        "variable_count",
        "constraint_count",
        "uncertainty_representation_size",
    ):
        assert field in E1_RESULT_FIELDS


def test_reuse_rows_load_historical_snake_case_fields() -> None:
    audit = reuse_identity_audit(load_formal_config(E1_CONFIG), load_formal_config(FREEZE))
    assert audit["status"] == "E1_REUSE_ACCEPTED"
    rows = reused_rows(audit)
    assert len(rows) == 2
    assert rows[0]["variable_count"] == 122376
