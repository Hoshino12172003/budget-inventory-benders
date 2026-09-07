from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .solver_profile import FORMAL_SOLVER_PROFILE_ID


FORMAL_CONFIG_SCHEMA_VERSION = "1.0"
EXPERIMENT_IDS = {f"E{number}" for number in range(1, 8)}
FORMAL_CASE_IDS = ["210202", "210628"]
FORMAL_PARAMETER_FREEZE = "experiments/configs/formal/formal_parameter_freeze.json"
RESULT_FIELDS = (
    "experiment_id",
    "case_id",
    "method",
    "B",
    "Gamma",
    "lambda_R",
    "objective",
    "first_stage_cost",
    "inventory_cost",
    "depot_fixed_cost",
    "reconfiguration_cost",
    "recourse_cost",
    "RI",
    "RS",
    "total_inventory",
    "active_depots",
    "fr_min_robust",
    "average_fill_rate_in_worst_service_scenario",
    "worst_region",
    "worst_scenario",
    "total_shortage_in_worst_service_scenario",
    "service_penalty_cost",
    "runtime_seconds",
    "master_runtime_seconds",
    "subproblem_runtime_seconds",
    "certification_runtime_seconds",
    "iterations",
    "cuts",
    "peak_memory_gb",
    "optimality_gap",
    "termination_status",
    "certification_status",
    "config_hash",
    "source_data_hash",
    "data_hash",
    "parameter_hash",
    "x0_hash",
    "git_commit",
    "solver_version",
    "python_version",
    "random_seed",
)


@dataclass(frozen=True)
class RunIdentity:
    config_hash: str
    source_data_hash: str
    data_hash: str
    parameter_hash: str
    x0_hash: str
    git_commit: str


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_formal_config(path: str | Path) -> dict[str, Any]:
    """Load JSON-compatible YAML without adding a YAML dependency."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_formal_config(config: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "experiment_id",
        "formal_run_authorized",
        "protocol_status",
        "case_ids",
        "parameter_grid",
        "outputs",
        "blockers",
        "solver_profile_id",
        "formal_parameter_freeze",
        "formal_parameter_freeze_sha256",
        "git_commit_at_execution",
        "budget_reference_by_case",
        "budget_rule",
    }
    missing = required - config.keys()
    if missing:
        raise ValueError(f"formal config is missing: {sorted(missing)}")
    if config["schema_version"] != FORMAL_CONFIG_SCHEMA_VERSION:
        raise ValueError("unsupported formal config schema version")
    if config["experiment_id"] not in EXPERIMENT_IDS:
        raise ValueError("unknown formal experiment id")
    if not isinstance(config["formal_run_authorized"], bool):
        raise ValueError("formal_run_authorized must be boolean")
    if config["formal_run_authorized"]:
        raise ValueError("protocol-freeze configs must remain unauthorized")
    if config["case_ids"] != FORMAL_CASE_IDS:
        raise ValueError("formal Renault identity must be explicit and ordered")
    if config["protocol_status"] != "PROTOCOL_READY":
        raise ValueError("formal protocol must pass before configuration freeze")
    if config["blockers"]:
        raise ValueError("protocol-ready config cannot retain blockers")
    if config["solver_profile_id"] != FORMAL_SOLVER_PROFILE_ID:
        raise ValueError("formal config must use the shared solver profile")
    if config["formal_parameter_freeze"] != FORMAL_PARAMETER_FREEZE:
        raise ValueError("formal config must reference the frozen parameter source")
    if len(config["formal_parameter_freeze_sha256"]) != 64:
        raise ValueError("formal parameter freeze SHA-256 must be explicit")
    if config["git_commit_at_execution"] != "CAPTURE_AT_EXECUTION":
        raise ValueError("execution commit must be captured at execution time")
    if config["budget_reference_by_case"] != {
        "210202": 84614.30513135393,
        "210628": 50558.18771213083,
    }:
        raise ValueError("formal config must use the frozen case budget references")
    if config["budget_rule"] != "B = beta * B_ref_case":
        raise ValueError("formal budget must be derived from beta and case B_ref")


def require_formal_authorization(config: dict[str, Any]) -> None:
    if not config.get("formal_run_authorized", False):
        raise PermissionError("formal run is not authorized")


def reconfiguration_intensity(
    a_plus: list[list[float]],
    a_minus: list[list[float]],
    x0: list[list[float]],
) -> float:
    denominator = sum(sum(row) for row in x0)
    if denominator <= 0:
        raise ValueError("RI denominator sum(x0) must be positive")
    return (
        sum(sum(row) for row in a_plus) + sum(sum(row) for row in a_minus)
    ) / denominator


def reconfiguration_budget_share(reconfiguration_cost: float, budget: float) -> float:
    if budget <= 0:
        raise ValueError("RS denominator B must be positive")
    return reconfiguration_cost / budget


def materialize_parameters(
    *, b_ref: float, beta: float, gamma: int, lambda_r: float
) -> dict[str, float | int]:
    return {"B": beta * b_ref, "Gamma": gamma, "lambda_R": lambda_r}


def validate_result_row(row: dict[str, Any]) -> None:
    missing = set(RESULT_FIELDS) - row.keys()
    if missing:
        raise ValueError(f"result row is missing: {sorted(missing)}")


def validate_resume_identity(checkpoint: dict[str, str], expected: RunIdentity) -> None:
    for field in (
        "config_hash",
        "source_data_hash",
        "data_hash",
        "parameter_hash",
        "x0_hash",
        "git_commit",
    ):
        if checkpoint.get(field) != getattr(expected, field):
            raise ValueError(f"checkpoint {field} mismatch")
