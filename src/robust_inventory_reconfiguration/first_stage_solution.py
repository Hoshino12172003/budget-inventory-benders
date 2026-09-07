from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .instance import InventoryInstance
from .reconfiguration_model import ReconfigurationSolution, reconfiguration_index


MATRIX_FIELDS = ("x", "a_plus", "a_minus")


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _matrix_entries(
    instance: InventoryInstance, matrix: list[list[float]]
) -> list[dict[str, Any]]:
    if len(matrix) != instance.num_depots or any(
        len(row) != instance.num_products for row in matrix
    ):
        raise ValueError("first-stage matrix dimensions are invalid")
    entries = []
    for i, depot_id in enumerate(instance.depot_ids):
        for j, product_id in enumerate(instance.product_ids):
            value = float(matrix[i][j])
            if not math.isfinite(value):
                raise ValueError("first-stage matrix contains a non-finite value")
            entries.append(
                {"depot_id": depot_id, "product_id": product_id, "value": value}
            )
    return entries


def build_first_stage_solution_artifact(
    instance: InventoryInstance,
    x0: list[list[float]],
    solution: ReconfigurationSolution,
    *,
    case_id: str,
    mode: str,
    identity: dict[str, str],
    solver_profile: str,
) -> dict[str, Any]:
    ri, represented_ri = reconfiguration_index(
        solution.x, x0, solution.a_plus, solution.a_minus
    )
    if abs(ri - represented_ri) > 1e-6:
        raise ValueError("reconfiguration-index representations disagree")
    if len(solution.y) != instance.num_depots:
        raise ValueError("depot activation dimensions are invalid")
    payload = {
        "schema_version": "1.0",
        "case_id": case_id,
        "mode": mode,
        "dimensions": {
            "depots": instance.num_depots,
            "products": instance.num_products,
            "x_entries": instance.num_depots * instance.num_products,
        },
        "depot_ids": list(instance.depot_ids),
        "product_ids": list(instance.product_ids),
        "y": [
            {"depot_id": depot_id, "value": int(solution.y[i])}
            for i, depot_id in enumerate(instance.depot_ids)
        ],
        "x": _matrix_entries(instance, solution.x),
        "a_plus": _matrix_entries(instance, solution.a_plus),
        "a_minus": _matrix_entries(instance, solution.a_minus),
        "objective": float(solution.objective),
        "first_stage_expenditure": float(solution.first_stage_expenditure),
        "robust_recourse_cost": float(solution.robust_recourse_cost),
        "total_inventory": float(sum(map(sum, solution.x))),
        "active_depots": int(sum(solution.y)),
        "RI": float(ri),
        "reconfiguration_cost": float(solution.reconfiguration_cost),
        "config_hash": identity["config_hash"],
        "data_hash": identity["data_hash"],
        "x0_hash": identity["x0_hash"],
        "git_commit": identity["git_commit"],
        "solver_profile": solver_profile,
    }
    return {
        **payload,
        "solution_payload_sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
    }


def validate_first_stage_solution_artifact(
    artifact: dict[str, Any], instance: InventoryInstance
) -> None:
    recorded_hash = artifact.get("solution_payload_sha256")
    payload = {key: value for key, value in artifact.items() if key != "solution_payload_sha256"}
    if recorded_hash != hashlib.sha256(_canonical_bytes(payload)).hexdigest():
        raise ValueError("first-stage solution payload hash mismatch")
    if artifact.get("dimensions") != {
        "depots": instance.num_depots,
        "products": instance.num_products,
        "x_entries": instance.num_depots * instance.num_products,
    }:
        raise ValueError("first-stage solution dimensions do not match the instance")
    expected_pairs = {
        (depot_id, product_id)
        for depot_id in instance.depot_ids
        for product_id in instance.product_ids
    }
    for field in MATRIX_FIELDS:
        entries = artifact.get(field, [])
        pairs = [(entry.get("depot_id"), entry.get("product_id")) for entry in entries]
        if len(entries) != len(expected_pairs) or len(set(pairs)) != len(pairs):
            raise ValueError(f"{field} entries are incomplete or duplicated")
        if set(pairs) != expected_pairs:
            raise ValueError(f"{field} identity set does not match the instance")
        if any(
            not isinstance(entry.get("value"), (int, float))
            or not math.isfinite(float(entry["value"]))
            for entry in entries
        ):
            raise ValueError(f"{field} contains a non-finite or nonnumeric value")
    y_entries = artifact.get("y", [])
    if [entry.get("depot_id") for entry in y_entries] != list(instance.depot_ids):
        raise ValueError("depot activation identities are invalid")
    if any(entry.get("value") not in (0, 1) for entry in y_entries):
        raise ValueError("depot activation values must be binary")


def matrix_from_artifact(
    artifact: dict[str, Any], instance: InventoryInstance, field: str = "x"
) -> list[list[float]]:
    if field not in MATRIX_FIELDS:
        raise ValueError(f"unknown first-stage matrix field: {field}")
    validate_first_stage_solution_artifact(artifact, instance)
    values = {
        (entry["depot_id"], entry["product_id"]): float(entry["value"])
        for entry in artifact[field]
    }
    return [
        [values[(depot_id, product_id)] for product_id in instance.product_ids]
        for depot_id in instance.depot_ids
    ]


def write_first_stage_solution_artifact(
    path: Path, artifact: dict[str, Any]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def load_first_stage_solution_artifact(
    path: Path, instance: InventoryInstance
) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    validate_first_stage_solution_artifact(artifact, instance)
    return artifact
