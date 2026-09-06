import csv
import json
from collections import Counter
from pathlib import Path


ARTIFACTS = Path("artifacts")


def test_all_renault_cases_are_reclassified_without_failures() -> None:
    with (ARTIFACTS / "prb_correctness_reclassification.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    summary = json.loads(
        (ARTIFACTS / "prb_correctness_contract_summary.json").read_text(encoding="utf-8")
    )
    observed = Counter(row["comparison_status"] for row in rows)
    assert len(rows) == 72
    assert all(
        observed[status] == count
        for status, count in summary["classification_counts"].items()
    )
    assert observed["FAIL"] == 0


def test_former_mismatches_have_independent_fixed_x_evidence() -> None:
    with (ARTIFACTS / "prb_optimal_face_audit.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    assert {(row["gamma"], row["method"]) for row in rows} == {
        ("1", "exact"),
        ("1", "prb"),
        ("2", "exact"),
        ("2", "prb"),
    }
    assert all(row["first_stage_feasible"] == "True" for row in rows)
    assert all(row["recourse_certified"] == "True" for row in rows)
    assert all(row["on_global_optimal_level"] == "True" for row in rows)
    assert all(row["exactly_certified"] == "True" for row in rows)


def test_updated_correctness_contract_passes() -> None:
    summary = json.loads(
        (ARTIFACTS / "prb_correctness_contract_summary.json").read_text(encoding="utf-8")
    )
    assert summary["optimal_face_equivalence_confirmed"]
    assert summary["prb_benders_correctness_pass"]
    assert summary["classification_counts"]["FAIL"] == 0
    assert not summary["main_mathematical_model_changed"]
    assert not summary["prb_benders_algorithm_changed"]
    assert not summary["secondary_tie_break_introduced"]
    assert not summary["frozen_parameter_changed"]
