from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts/e1_objective_mismatch_audit_210310_210330.json"


def test_alleged_mismatches_pass_the_frozen_absolute_gate() -> None:
    audit = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert audit["correctness_threshold"] == 1e-4
    assert audit["correctness_threshold_changed"] is False
    assert [case["case"] for case in audit["cases"]] == ["210310", "210330"]
    for case in audit["cases"]:
        assert case["classification"] == "NUMERICAL_REPORTING_ONLY"
        assert case["blocker"] == ""
        assert case["component_differences"]["total_objective"] < 1e-4
        assert max(case["same_x_recourse_errors"].values()) < 1e-8
        assert case["same_y"] is True


def test_audit_is_fixed_first_stage_and_preserves_primary_results() -> None:
    audit = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert audit["audit_only_fixed_first_stage_evaluations"] == 8
    assert audit["primary_result_hashes_preserved"] is True
    assert audit["other_six_cases_rerun"] is False
    assert audit["model_changed"] is False
    assert audit["dataset_changed"] is False
    assert audit["e2_e7_authorization"] is False


def test_audit_table_contains_both_cross_evaluations() -> None:
    with (ROOT / "table_e1_objective_mismatch_audit.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert [row["case"] for row in rows] == ["210310", "210330"]
    required = {
        "Q_DirectEval_on_DirectX",
        "Q_PRBEval_on_DirectX",
        "Q_DirectEval_on_PRBX",
        "Q_PRBEval_on_PRBX",
    }
    assert required <= rows[0].keys()
