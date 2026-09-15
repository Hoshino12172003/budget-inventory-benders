from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_e1_performance_summary_is_complete() -> None:
    summary = json.loads(
        (ROOT / "artifacts/e1_empirical_performance_summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "E1_COMPUTATIONAL_PERFORMANCE_COMPLETE"
    assert summary["completed_runs"] == 16
    assert summary["completed_pairs"] == 8
    assert summary["correctness_pass_pairs"] == 8
    assert summary["correctness_tolerance"] == 1e-4
    assert summary["completeness"]["resource_limited"] == 0
    assert summary["speedup_direct_over_prb"]["prb_faster_count"] == 8


def test_pair_table_recomputes_speedup_and_objective_difference() -> None:
    with (ROOT / "table_e1_empirical_performance.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8
    for row in rows:
        direct_runtime = float(row["direct_runtime_seconds"])
        prb_runtime = float(row["prb_runtime_seconds"])
        assert abs(float(row["speedup_direct_over_prb"]) - direct_runtime / prb_runtime) < 1e-12
        direct_objective = float(row["direct_objective"])
        prb_objective = float(row["prb_objective"])
        assert abs(float(row["absolute_objective_difference"]) - abs(direct_objective - prb_objective)) < 1e-15


def test_210330_is_retained_as_a_diagnostic_exception() -> None:
    summary = json.loads(
        (ROOT / "artifacts/e1_empirical_performance_summary.json").read_text(encoding="utf-8")
    )
    row = next(row for row in summary["rows"] if row["case"] == "210330")
    assert row["prb_global_coupling_diagnostic_status"] == "DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH"
    assert row["absolute_objective_difference"] < summary["correctness_tolerance"]
    exception = summary["prb_diagnostics"]["global_coupling_exception"]
    assert exception["objective_consistency_pass"]
    assert exception["exact_recourse_recertification_pass"]
    assert exception["gamma_allocation_feasible"]


def test_summary_records_no_execution_or_frozen_input_changes() -> None:
    summary = json.loads(
        (ROOT / "artifacts/e1_empirical_performance_summary.json").read_text(encoding="utf-8")
    )
    control = summary["change_control"]
    assert control == {
        "optimization_reruns": 0,
        "model_changed": False,
        "dataset_changed": False,
        "tolerance_changed": False,
        "authorization_changed": False,
        "e2_e7_authorization": False,
    }
