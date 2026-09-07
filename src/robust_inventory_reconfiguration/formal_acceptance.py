from __future__ import annotations

from pathlib import Path
from typing import Any


ACCEPTANCE_BATCH_ID = "formal_acceptance_batch_1"
AUTHORIZED_RUN_IDS = ("A1", "A2", "A3", "A4", "A5")
EXPECTED_RUNS = {
    "A1": ("E1", "direct_exact", 2, False),
    "A2": ("E1", "prb_benders", 2, False),
    "A3": ("E2", "existing_system", 0, True),
    "A4": ("E2", "nominal_reconfiguration", 0, False),
    "A5": ("E2", "robust_reconfiguration", 2, False),
}


def validate_acceptance_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("batch_id") != ACCEPTANCE_BATCH_ID:
        raise ValueError("unexpected acceptance batch id")
    if manifest.get("formal_run_authorized") is not True:
        raise PermissionError("acceptance batch is not authorized")
    if manifest.get("authorization_scope") != "acceptance_batch_only":
        raise ValueError("authorization must be acceptance-specific")
    if manifest.get("full_e1_e7_authorization") is not False:
        raise ValueError("full E1-E7 authorization must remain false")
    if tuple(manifest.get("authorized_run_ids", ())) != AUTHORIZED_RUN_IDS:
        raise ValueError("acceptance authorization must use the exact run allowlist")
    if manifest.get("case_ids") != ["210202"]:
        raise ValueError("batch 1 is restricted to Renault case 210202")
    runs = manifest.get("runs", [])
    if [run.get("acceptance_run_id") for run in runs] != list(AUTHORIZED_RUN_IDS):
        raise ValueError("manifest run order or identity is invalid")
    for run in runs:
        run_id = run["acceptance_run_id"]
        experiment, method, gamma, fix_x = EXPECTED_RUNS[run_id]
        expected = {
            "experiment_id": experiment,
            "case_id": "210202",
            "method": method,
            "beta": 1.0,
            "B": 84614.30513135393,
            "Gamma": gamma,
            "lambda_R": 0.05,
            "solver_profile_id": "gurobi-balanced-1e-8-v1",
            "fix_x_to_x0": fix_x,
        }
        if any(run.get(key) != value for key, value in expected.items()):
            raise ValueError(f"{run_id} parameters differ from the authorized contract")


def acceptance_output_path(repository_root: Path, manifest: dict[str, Any]) -> Path:
    expected = (
        repository_root
        / "experiments"
        / "results"
        / "formal_acceptance_batch_1"
        / "attempt_001"
    ).resolve()
    configured = (repository_root / manifest["output_directory"]).resolve()
    if configured != expected:
        raise ValueError("acceptance output directory is outside the authorized attempt")
    return configured


def validate_formal_result_shape(row: dict[str, Any], required: tuple[str, ...]) -> None:
    if set(row) != set(required):
        missing = sorted(set(required) - set(row))
        extra = sorted(set(row) - set(required))
        raise ValueError(f"formal result schema mismatch: missing={missing}, extra={extra}")
