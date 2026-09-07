from __future__ import annotations

from pathlib import Path
from typing import Any


E1_ATTEMPT_ID = "e1_formal_algorithm_benchmark_attempt_001"
E1_NEW_RUN_IDS = (
    "E1-210628-DIRECT",
    "E1-210628-PRB",
    "E1-SMALL-DIRECT",
    "E1-SMALL-PRB",
    "E1-MEDIUM-DIRECT",
    "E1-MEDIUM-PRB",
    "E1-RENAULTLIKE-DIRECT",
    "E1-RENAULTLIKE-PRB",
    "E1-LARGE-DIRECT",
    "E1-LARGE-PRB",
)

E1_RESULT_FIELDS = (
    "run_id", "instance_id", "instance_type", "scale", "I", "R", "J",
    "uncertain_item_count", "method", "beta", "B", "Gamma", "lambda_R",
    "objective", "first_stage_cost", "depot_fixed_cost", "inventory_cost",
    "reconfiguration_cost", "recourse_cost", "runtime_seconds", "peak_memory_gb",
    "final_gap", "termination_status", "certification_status", "solver_profile",
    "seed", "instance_hash", "config_hash", "first_stage_solution_hash",
    "git_commit", "result_origin", "benders_iterations", "master_solves",
    "unique_product_cuts", "active_cuts", "product_subproblem_solves",
    "master_runtime_seconds", "subproblem_runtime_seconds",
    "global_coupling_runtime_seconds", "lower_bound", "upper_bound",
    "final_relative_gap", "global_coupling_residual", "variable_count",
    "constraint_count", "integer_variable_count", "continuous_variable_count",
    "uncertainty_representation_size", "node_count", "nonzero_count",
)


def validate_e1_authorization(manifest: dict[str, Any]) -> None:
    if manifest.get("attempt_id") != E1_ATTEMPT_ID:
        raise ValueError("unexpected E1 attempt id")
    if manifest.get("authorization_scope") != "e1_new_runs_only":
        raise ValueError("E1 authorization scope is invalid")
    if manifest.get("e1_run_authorized") is not True:
        raise PermissionError("E1 attempt is not authorized")
    if tuple(manifest.get("authorized_run_ids", ())) != E1_NEW_RUN_IDS:
        raise ValueError("E1 authorization must use the exact ten-run allowlist")
    if manifest.get("e2_e7_authorization") is not False:
        raise ValueError("E2-E7 must remain unauthorized")
    if manifest.get("objective_absolute_tolerance") != 1e-4:
        raise ValueError("E1 objective tolerance changed")
    runs = manifest.get("runs", [])
    if [run.get("run_id") for run in runs] != list(E1_NEW_RUN_IDS):
        raise ValueError("E1 run order or identity is invalid")
    for run in runs[:2]:
        if any(
            run.get(key) != value
            for key, value in {
                "instance_id": "210628",
                "instance_type": "Renault",
                "beta": 1.0,
                "B": 50558.18771213083,
                "Gamma": 2,
                "lambda_R": 0.05,
                "solver_profile": "gurobi-balanced-1e-8-v1",
            }.items()
        ):
            raise ValueError("210628 E1 parameters changed")


def e1_output_path(repository_root: Path, manifest: dict[str, Any]) -> Path:
    expected = (
        repository_root / "experiments" / "results" / "e1_algorithm_benchmark" / "attempt_001"
    ).resolve()
    configured = (repository_root / manifest["output_directory"]).resolve()
    if configured != expected:
        raise ValueError("E1 output directory is outside the authorized attempt")
    return configured


def synthetic_reproducibility_audit(config: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "dimensions_frozen": all(
            set(scale) >= {"id", "I", "R", "J"} for scale in config.get("scales", [])
        ),
        "seed_frozen": isinstance(config.get("seed"), int),
        "generator_implementation_frozen": False,
        "generator_version_frozen": False,
        "x0_construction_frozen": False,
        "cost_construction_frozen": False,
        "budget_construction_frozen": False,
        "uncertainty_construction_and_ranges_frozen": False,
        "resource_timeout_and_disk_guards_frozen": False,
    }
    return {
        "status": (
            "PASS" if config.get("status") != "DESIGN_ONLY" and all(checks.values())
            else "BLOCK_E1_SYNTHETIC_REPRODUCIBILITY"
        ),
        "source_status": config.get("status"),
        "checks": checks,
        "reason": (
            "The repository freezes scale dimensions and seed only; it has no formal "
            "synthetic generator or frozen construction rules."
        ),
    }
