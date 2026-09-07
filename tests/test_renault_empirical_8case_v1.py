from __future__ import annotations

import json
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.renault_empirical import (
    CASES, MAPPING_SHA256, PRODUCTS, quantile_linear, verify_mapping,
)


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_identity_contract() -> None:
    assert CASES == ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
    assert len(PRODUCTS) == 8
    mapping = json.loads((ROOT / "artifacts/e1_empirical_region_mapping_v1.json").read_text(encoding="utf-8"))
    verify_mapping(mapping)
    assert mapping["mapping_sha256"] == MAPPING_SHA256


def test_linear_quantile_matches_frozen_definition() -> None:
    assert quantile_linear([0.0, 10.0], 0.90) == pytest.approx(9.0)
    assert quantile_linear([3.0], 0.90) == 3.0


def test_authorization_is_fail_closed_and_exact() -> None:
    manifest = json.loads(
        (ROOT / "experiments/configs/formal/e1_empirical_8case_authorization.json").read_text(encoding="utf-8")
    )
    assert manifest["formal_run_authorized"] is True
    assert manifest["synthetic_execution_authorized"] is False
    assert manifest["e2_e7_authorization"] is False
    assert manifest["objective_match_tolerance"] == 1e-4
    assert manifest["mapping_sha256"] == MAPPING_SHA256
    assert len(manifest["authorized_run_ids"]) == 16
    assert manifest["authorized_run_ids"] == [
        f"E1-{case}-{method}" for case in CASES for method in ("DIRECT", "PRB")
    ]
