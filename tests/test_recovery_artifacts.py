from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from robust_inventory_reconfiguration.first_stage_solution import (
    load_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.formal_protocol import file_sha256, load_formal_config
from robust_inventory_reconfiguration.formal_recovery import RECOVERY_RUN_IDS
from robust_inventory_reconfiguration.instance import load_instance


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = (
    ROOT
    / "experiments"
    / "results"
    / "formal_acceptance_batch_1"
    / "recovery_attempt_002"
)
ORIGINAL = RECOVERY.parent / "attempt_001"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_recovery_passes_with_exact_scope_and_no_retry() -> None:
    summary = load_json(RECOVERY / "recovery_summary.json")
    assert summary["status"] == "RECOVERY_PASS"
    assert summary["classification"] == "A5_RESULT_VALID_METRIC_TRADEOFF"
    assert summary["completed_run_ids"] == list(RECOVERY_RUN_IDS)
    assert summary["recovery_run_count"] == 3
    assert summary["failures"] == []
    assert summary["retries"] == 0
    assert summary["e1_authorization"] is False
    assert summary["e2_e7_authorization"] is False
    assert summary["original_attempt_immutable"] is True


def test_recovery_objectives_identically_match_acceptance() -> None:
    with (RECOVERY / "recovery_identity.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["run_id"] for row in rows] == list(RECOVERY_RUN_IDS)
    assert all(float(row["objective_absolute_difference"]) <= 1e-4 for row in rows)


def test_recovered_solution_artifacts_are_complete_and_hashed() -> None:
    instance = load_instance(ROOT / "data" / "formal_instances" / "210202.json")
    for run_id in RECOVERY_RUN_IDS:
        path = RECOVERY / "solutions" / f"{run_id.lower()}_first_stage_solution.json"
        artifact = load_first_stage_solution_artifact(path, instance)
        assert len(artifact["x"]) == 120
        assert len(artifact["a_plus"]) == 120
        assert len(artifact["a_minus"]) == 120
        assert len(artifact["y"]) == 15


def test_unified_and_common_scenario_tables_are_complete() -> None:
    with (RECOVERY / "table_a5_common_evaluation.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        unified = list(csv.DictReader(stream))
    with (RECOVERY / "table_a5_common_scenario_cross_evaluation.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        common = list(csv.DictReader(stream))
    assert [row["solution"] for row in unified] == list(RECOVERY_RUN_IDS)
    assert {int(row["scenario_count"]) for row in unified} == {4657}
    assert len(common) == 9
    assert {row["common_scenario"] for row in common} == {"C_A3", "C_A4", "C_A5"}
    assert float(unified[2]["worst_recourse"]) < float(unified[0]["worst_recourse"])
    assert float(unified[2]["FR_min"]) < float(unified[0]["FR_min"])


def test_recovery_and_original_attempt_hashes_pass() -> None:
    for directory in (ORIGINAL, RECOVERY):
        hashes = load_json(directory / "hashes.json")
        for relative, expected in hashes.items():
            assert file_sha256(directory / relative) == expected, relative
    manifest = RECOVERY / "authorization_manifest.yaml"
    provenance = load_json(RECOVERY / "provenance.json")
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == provenance[
        "authorization_manifest_hash"
    ]
    assert all(
        load_formal_config(path)["formal_run_authorized"] is False
        for path in (ROOT / "experiments" / "configs" / "formal").glob("e*.yaml")
    )
