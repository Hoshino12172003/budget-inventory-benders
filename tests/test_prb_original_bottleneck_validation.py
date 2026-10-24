from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_validation_summary_separates_oracle_and_master_conclusions() -> None:
    summary = json.loads(
        (ROOT / "artifacts/prb_original_bottleneck_validation.json").read_text(encoding="utf-8")
    )
    assert summary["question_A_global_oracle_bottleneck"] == "EVIDENCE_INSUFFICIENT"
    assert summary["question_B_product_level_master_benefit"] == "SUPPORTED"
    assert summary["overall"] == "PRB_MASTER_BENEFIT_ONLY"
    assert summary["formal_optimization_runs"] == 0
    assert summary["development_method_runs"] == 9


def test_existing_evidence_table_has_three_methods_for_ten_exact_points() -> None:
    with (ROOT / "table_prb_bottleneck_existing_evidence.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 30
    assert {row["method"] for row in rows} == {
        "pure_benders",
        "aggregate_benders_structured_oracle",
        "prb_benders",
    }
    assert len({row["scale_or_case"] for row in rows}) == 10


def test_j_scaling_table_retains_all_predeclared_points_and_exactness_gate() -> None:
    with (ROOT / "table_prb_j_scaling_development.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12
    assert {int(row["J"]) for row in rows} == {12, 24, 48, 96}
    assert all(row["exactness_gate"] == "PASS" for row in rows if row["J"] == "12")
    assert all(row["exactness_gate"] == "NOT_ELIGIBLE" for row in rows if row["J"] != "12")
    assert all(row["status"] == "NOT_RUN_PREPARATION_BLOCKED" for row in rows if row["J"] == "96")
