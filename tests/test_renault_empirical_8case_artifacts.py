from __future__ import annotations

import csv
import json
from pathlib import Path

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.renault_empirical import CASES, DATASET_ID, MAPPING_SHA256, sha256_file


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts" / DATASET_ID.lower()


def rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_all_new_instances_and_identity_hashes_match() -> None:
    identity = {row["case"]: row for row in rows("table_empirical_8case_identity.csv")}
    assert tuple(identity) == CASES
    for case in CASES:
        instance_path = ROOT / "data/formal_instances_v2" / f"{case}.json"
        instance = load_instance(instance_path)
        assert (instance.num_depots, instance.num_regions, instance.num_products) == (
            {"210202": 15, "210628": 15, "210129": 15, "210310": 16,
             "210330": 11, "210323": 13, "210428": 18, "210611": 19}[case], 12, 8
        )
        assert instance.initial_inventory is not None
        assert identity[case]["mapping_hash"] == MAPPING_SHA256
        assert sha256_file(instance_path) == identity[case]["instance_hash"]
        assert sha256_file(BASE / "x0" / f"{case}.json") == identity[case]["x0_hash"]
        assert sha256_file(BASE / "calibration" / f"{case}.json") == identity[case]["calibration_hash"]


def test_dataset_is_ready_with_canonical_incumbents() -> None:
    summary = json.loads((BASE / "dataset_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "RENAULT_EMPIRICAL_8CASE_V1_READY"
    assert summary["blocked_cases"] == []
    assert summary["canonical_rule"] == "lexicographic_min_y_then_x_on_primary_optimal_face_v1"
    assert all(
        value["stability"]["canonical_incumbent_status"] == "PASS"
        for value in summary["cases"].values()
    )
    assert all(value["objective_delta"] <= 1e-7 for value in summary["cases"].values())
    assert summary["cases"]["210428"]["stability"]["primary_optimal_face_nonunique"] is True
    assert summary["deterministic_regeneration"] == "PASS"
    assert summary["data_preparation_optimization_solve_count"] == 4302
    assert summary["gamma2_e1_direct_solves"] == 0
    assert summary["gamma2_e1_prb_solves"] == 0
    assert summary["synthetic_execution"] == 0
    assert summary["e2_e7_authorization"] is False
    assert summary["old_formal_artifacts_overwritten"] is False
    assert all(value["feasibility"]["capacity_violation_count"] == 0 for value in summary["cases"].values())
    assert all(value["feasibility"]["ub_violation_count"] == 0 for value in summary["cases"].values())


def test_historical_artifact_hashes_still_match() -> None:
    summary = json.loads((BASE / "dataset_summary.json").read_text(encoding="utf-8"))
    assert summary["historical_protection_hashes"]["data/formal_instances"]
    assert summary["historical_protection_hashes"]["experiments/results/e1_algorithm_benchmark/attempt_001"]
    assert summary["historical_protection_hashes"]["experiments/results/e1_algorithm_benchmark/attempt_002"]
