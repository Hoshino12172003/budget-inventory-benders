from __future__ import annotations

import json
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    load_first_stage_solution_artifact,
    matrix_from_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.formal_protocol import load_formal_config
from robust_inventory_reconfiguration.formal_recovery import (
    RECOVERY_RUN_IDS,
    recovery_output_path,
    validate_recovery_manifest,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.reconfiguration_model import ReconfigurationSolution
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service


ROOT = Path(__file__).resolve().parents[1]


def solution(x: list[list[float]]) -> ReconfigurationSolution:
    zeros = [[0.0 for _ in row] for row in x]
    return ReconfigurationSolution(
        objective=12.0,
        first_stage_expenditure=5.0,
        robust_recourse_cost=7.0,
        y=[1] * len(x),
        x=x,
        a_plus=zeros,
        a_minus=zeros,
        reconfiguration_cost=0.0,
    )


def identity() -> dict[str, str]:
    return {
        "config_hash": "config",
        "data_hash": "data",
        "x0_hash": "x0",
        "git_commit": "commit",
    }


def test_solution_serialization_round_trip_and_hash_stability(
    tiny_instance, tmp_path
) -> None:
    x = [[2.0, 1.0]]
    artifact = build_first_stage_solution_artifact(
        tiny_instance,
        x,
        solution(x),
        case_id="tiny",
        mode="test",
        identity=identity(),
        solver_profile="test-profile",
    )
    path = tmp_path / "solution.json"
    write_first_stage_solution_artifact(path, artifact)
    loaded = load_first_stage_solution_artifact(path, tiny_instance)
    assert loaded == artifact
    assert matrix_from_artifact(loaded, tiny_instance) == x
    rebuilt = build_first_stage_solution_artifact(
        tiny_instance,
        x,
        solution(x),
        case_id="tiny",
        mode="test",
        identity=identity(),
        solver_profile="test-profile",
    )
    assert rebuilt["solution_payload_sha256"] == artifact["solution_payload_sha256"]


def test_renault_solution_has_exactly_120_complete_x_entries() -> None:
    instance = load_instance(ROOT / "data" / "formal_instances" / "210202.json")
    x = [[1.0] * instance.num_products for _ in range(instance.num_depots)]
    artifact = build_first_stage_solution_artifact(
        instance,
        x,
        solution(x),
        case_id="210202",
        mode="serialization_test",
        identity=identity(),
        solver_profile="test-profile",
    )
    assert len(artifact["x"]) == 120
    assert len({(row["depot_id"], row["product_id"]) for row in artifact["x"]}) == 120


def test_solution_payload_tampering_is_rejected(tiny_instance, tmp_path) -> None:
    x = [[2.0, 1.0]]
    artifact = build_first_stage_solution_artifact(
        tiny_instance,
        x,
        solution(x),
        case_id="tiny",
        mode="test",
        identity=identity(),
        solver_profile="test-profile",
    )
    artifact["x"][0]["value"] = 3.0
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(ValueError, match="payload hash mismatch"):
        load_first_stage_solution_artifact(path, tiny_instance)


def test_post_evaluator_consumes_persisted_x_without_first_stage_solve(
    tiny_instance, tmp_path
) -> None:
    x = [[2.0, 1.0]]
    artifact = build_first_stage_solution_artifact(
        tiny_instance,
        x,
        solution(x),
        case_id="tiny",
        mode="test",
        identity=identity(),
        solver_profile="test-profile",
    )
    path = tmp_path / "solution.json"
    write_first_stage_solution_artifact(path, artifact)
    persisted_x = matrix_from_artifact(
        load_first_stage_solution_artifact(path, tiny_instance), tiny_instance
    )
    assert evaluate_robust_service(tiny_instance, persisted_x, 0).scenario_count == 1


def test_recovery_manifest_is_exactly_scoped() -> None:
    manifest = load_formal_config(
        ROOT / "experiments" / "configs" / "formal_acceptance_recovery_attempt_002.yaml"
    )
    validate_recovery_manifest(manifest)
    assert tuple(manifest["authorized_run_ids"]) == RECOVERY_RUN_IDS
    assert manifest["e1_authorization"] is False
    assert manifest["e2_e7_authorization"] is False
    assert recovery_output_path(ROOT, manifest).name == "recovery_attempt_002"
