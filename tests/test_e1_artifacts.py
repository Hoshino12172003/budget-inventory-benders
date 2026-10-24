from __future__ import annotations

import csv
import json
from pathlib import Path

from robust_inventory_reconfiguration.e1_formal import E1_RESULT_FIELDS
from robust_inventory_reconfiguration.first_stage_solution import (
    load_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.formal_protocol import file_sha256, load_formal_config
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results" / "e1_algorithm_benchmark"
ATTEMPT = RESULTS / "attempt_002"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_e1_attempts_are_hashed_and_first_failure_is_preserved() -> None:
    for attempt in (RESULTS / "attempt_001", ATTEMPT):
        hashes = load_json(attempt / "hashes.json")
        for relative, expected in hashes.items():
            assert file_sha256(attempt / relative) == expected, relative
    failure = load_json(RESULTS / "attempt_001" / "failure.json")
    assert failure["new_optimization_solves"] == 0
    assert failure["artifacts_overwritten"] is False


def test_e1_summary_stops_only_at_synthetic_reproducibility_gate() -> None:
    summary = load_json(ATTEMPT / "e1_summary.json")
    assert summary["status"] == "BLOCK_E1_SYNTHETIC_REPRODUCIBILITY"
    assert summary["reuse_status"] == "E1_REUSE_ACCEPTED"
    assert summary["planned_observations"] == 12
    assert summary["completed_observations"] == 4
    assert summary["new_optimization_solves"] == 2
    assert summary["unauthorized_runs_executed"] == 0
    assert summary["e2_e7_authorization"] is False
    assert summary["failures"] == []
    assert summary["retries"] == 0


def test_e1_table_has_four_results_and_eight_explicit_not_run_rows() -> None:
    with (ATTEMPT / "table_e1_algorithm_benchmark.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        assert tuple(reader.fieldnames or ()) == E1_RESULT_FIELDS
    assert len(rows) == 12
    assert sum(row["termination_status"] == "OPTIMAL" for row in rows) == 4
    assert sum(row["termination_status"] == "NOT_RUN" for row in rows) == 8
    assert all(
        row["solver_profile"] == FORMAL_SOLVER_PROFILE_ID
        for row in rows[:4]
    )


def test_renault_pairs_are_certified_and_objective_consistent() -> None:
    with (ATTEMPT / "table_e1_objective_consistency.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert all(float(row["Abs Diff"]) <= 1e-4 and row["PASS"] == "PASS" for row in rows[:2])
    assert all(row["PASS"] == "NOT_COMPARABLE" for row in rows[2:])


def test_new_210628_solutions_have_complete_persisted_decisions() -> None:
    instance = load_instance(ROOT / "data" / "formal_instances" / "210628.json")
    for run_id in ("E1-210628-DIRECT", "E1-210628-PRB"):
        artifact = load_first_stage_solution_artifact(
            ATTEMPT / "runs" / run_id / "first_stage_solution.json", instance
        )
        assert len(artifact["x"]) == 120
        assert len(artifact["a_plus"]) == 120
        assert len(artifact["a_minus"]) == 120
        assert len(artifact["y"]) == 15


def test_synthetic_gate_and_reporting_correction_are_explicit() -> None:
    gate = load_json(ATTEMPT / "audits" / "synthetic_reproducibility_gate.json")
    assert gate["status"] == "BLOCK_E1_SYNTHETIC_REPRODUCIBILITY"
    assert gate["source_status"] == "DESIGN_ONLY"
    correction = load_json(ROOT / "artifacts" / "e1_reporting_corrections.json")
    assert correction["immutable_source_preserved"] is True
    assert correction["optimization_results_affected"] is False
    assert correction["corrections"][0]["reporting_value"] is None
    assert all(
        load_formal_config(path)["formal_run_authorized"] is False
        for path in (ROOT / "experiments" / "configs" / "formal").glob("e[2-7]*.yaml")
    )
