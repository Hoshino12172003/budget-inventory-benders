from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from experiments.run_e1_empirical_local import validate_execution_gate


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "experiments" / "configs" / "formal" / "e1_empirical_case_freeze.json"
MAPPING = ROOT / "artifacts" / "e1_empirical_region_mapping_v1.json"
CASES = ["210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611"]


def read_rows(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_case_identity_and_dimensions_are_frozen_pre_solve() -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert freeze["schema"] == "E1_EMPIRICAL_CASES_V1"
    assert freeze["selected_case_order"] == CASES
    assert [case["final_I"] for case in freeze["cases"]] == [15, 15, 15, 16, 11, 13, 18, 19]
    assert freeze["products"] == [
        "BAC---1041", "BAC-O-4312", "BAC-O-4325", "BAC-O-6423",
        "BAC-O-6433", "CON-S-0130", "SLI---0770", "SLI---1200",
    ]
    assert freeze["new_gamma2_e1_benchmark_solves"] == 0
    assert freeze["baseline_preparation_solves"] == 0
    assert freeze["synthetic_execution"] == 0
    assert freeze["e2_e7_authorization"] is False


def test_mapping_is_complete_nonempty_and_identity_consistent() -> None:
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    rows = read_rows("table_e1_empirical_region_mapping_audit.csv")
    assert len(rows) == 8 * 12
    assert mapping["common_customer_identity_count"] == 298
    assert mapping["coverage_complete"] is True
    assert mapping["empty_region_count"] == 0
    assert {row["mapping_sha256"] for row in rows} == {mapping["mapping_sha256"]}
    for case in CASES:
        case_rows = [row for row in rows if row["case_id"] == case]
        assert len(case_rows) == 12
        assert all(float(row["coverage_ratio"]) == 1.0 for row in case_rows)
        assert all(int(row["customers_in_region"]) > 0 for row in case_rows)


def test_legacy_formal_region_contract_is_proven_incompatible() -> None:
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    assert mapping["status"] == "BLOCK_E1_EMPIRICAL_REGION_MAPPING"
    for case in ("210202", "210628"):
        check = mapping["legacy_formal_compatibility"][case]
        assert check["compatible_with_existing_formal_instance"] is False
        assert check["maximum_cell_difference_under_best_permutation"] > 100.0
        assert check["exact_cells_under_best_permutation"] < check["total_cells"]


def test_blocked_cases_have_no_fabricated_baseline_or_identity() -> None:
    for name in (
        "table_e1_empirical_x0_summary.csv",
        "table_e1_empirical_bref_summary.csv",
        "table_e1_empirical_instance_identity.csv",
    ):
        rows = read_rows(name)
        assert [row["case_id"] for row in rows] == CASES
        for row in rows[2:]:
            assert "BLOCKED_BY_REGION_MAPPING" in row["status"]
    assert all(not row["total_x0"] for row in read_rows("table_e1_empirical_x0_summary.csv")[2:])
    assert all(not row["B_ref"] for row in read_rows("table_e1_empirical_bref_summary.csv")[2:])
    assert all(not row["instance_sha256"] for row in read_rows("table_e1_empirical_instance_identity.csv")[2:])
    for case in CASES[2:]:
        assert not (ROOT / "data" / "formal_instances" / f"{case}.json").exists()
        assert not (ROOT / "artifacts" / f"nominal_baseline_{case}.csv").exists()


def test_local_runner_fails_before_execution_while_dataset_is_partial() -> None:
    with pytest.raises(PermissionError, match="E1_EMPIRICAL_8CASE_FORMAL_RUN_NOT_AUTHORIZED"):
        validate_execution_gate("210129", "direct", ROOT / "unused-output", False)
