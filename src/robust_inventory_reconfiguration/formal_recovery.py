from __future__ import annotations

from pathlib import Path
from typing import Any


RECOVERY_ID = "formal_acceptance_batch_1_recovery_attempt_002"
RECOVERY_RUN_IDS = ("A3", "A4", "A5")
EXPECTED_RECOVERY_RUNS = {
    "A3": ("existing_system", 0, True, 108999.13573275977),
    "A4": ("nominal_reconfiguration", 0, False, 108999.13573275965),
    "A5": ("robust_reconfiguration", 2, False, 116875.3457619544),
}


def validate_recovery_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("recovery_id") != RECOVERY_ID:
        raise ValueError("unexpected recovery id")
    if manifest.get("recovery_run_authorized") is not True:
        raise PermissionError("recovery attempt is not authorized")
    if manifest.get("authorization_scope") != "a3_a4_a5_persistence_recovery_only":
        raise ValueError("recovery authorization scope is invalid")
    if tuple(manifest.get("authorized_run_ids", ())) != RECOVERY_RUN_IDS:
        raise ValueError("recovery allowlist must contain exactly A3, A4, and A5")
    if manifest.get("case_ids") != ["210202"]:
        raise ValueError("recovery is restricted to Renault case 210202")
    if manifest.get("e1_authorization") is not False:
        raise ValueError("E1 must remain unauthorized")
    if manifest.get("e2_e7_authorization") is not False:
        raise ValueError("E2-E7 must remain unauthorized")
    runs = manifest.get("runs", [])
    if [run.get("acceptance_run_id") for run in runs] != list(RECOVERY_RUN_IDS):
        raise ValueError("recovery run order or identity is invalid")
    for run in runs:
        run_id = run["acceptance_run_id"]
        mode, gamma, fix_x, objective = EXPECTED_RECOVERY_RUNS[run_id]
        expected = {
            "case_id": "210202",
            "mode": mode,
            "beta": 1.0,
            "B": 84614.30513135393,
            "Gamma": gamma,
            "lambda_R": 0.05,
            "solver_profile_id": "gurobi-balanced-1e-8-v1",
            "fix_x_to_x0": fix_x,
            "original_objective": objective,
        }
        if any(run.get(key) != value for key, value in expected.items()):
            raise ValueError(f"{run_id} differs from the recovery authorization")


def recovery_output_path(repository_root: Path, manifest: dict[str, Any]) -> Path:
    expected = (
        repository_root
        / "experiments"
        / "results"
        / "formal_acceptance_batch_1"
        / "recovery_attempt_002"
    ).resolve()
    configured = (repository_root / manifest["output_directory"]).resolve()
    if configured != expected:
        raise ValueError("recovery output directory is outside the authorized attempt")
    return configured
