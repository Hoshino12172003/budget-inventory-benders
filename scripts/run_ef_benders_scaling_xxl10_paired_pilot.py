from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_ef_benders_scaling as runner
from scripts.run_direct_scaling_xxl10_paired_pilot import active_paired_solver_workers, git_status_for_execution


DEFAULT_CONFIG = ROOT / "experiments/configs/development/ef_benders_scaling_xxl10_paired_pilot_v1.yaml"
CONDITION_ID = "EF_XXL10_S20260921"


def validate_protocol(config: dict) -> None:
    policy = config["resource_policy"]
    checks = {
        "protocol": config.get("protocol_id") == "EF_BD_XXL10_PAIRED_PILOT_V1",
        "scope": config.get("authorized_condition_ids") == [CONDITION_ID],
        "authorization_boolean": isinstance(config.get("formal_run_authorized"), bool),
        "dimensions": config.get("sizes") == [{"label": "XXL10", "I": 36, "R": 36, "J": 16}],
        "science": config.get("fixed_scientific_parameters") == {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "SL": 0.90, "phi_multiplier": 1.85},
        "solver": config.get("solver_parameters") == {"Threads": 2},
        "algorithm": config.get("algorithm", {}).get("global_theta_count") == 1 and config.get("algorithm", {}).get("cuts_per_iteration_maximum") == 1,
        "resource": (
            policy["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
            and policy["minimum_available_memory_gib_by_size"] == {"XXL10": 17}
            and policy["minimum_system_available_memory_gib"] == 3
            and policy["minimum_free_disk_gib"] == 20
            and policy["condition_time_limit_seconds"] == 900
            and policy["memory_monitor_interval_seconds"] == 0.25
            and policy["parallel_workers"] == 1
            and policy["retry_policy"] == "no_automatic_retry"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"EF-BD XXL10 paired-pilot protocol mismatch: {checks}")


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    row = runner.dry_run(config_path, CONDITION_ID)
    frozen = config["frozen_input_identity"]
    identity_checks = {
        "condition_id": row["condition"]["condition_id"] == frozen["condition_id"],
        "source_instance_id": row["source_instance_id"] == frozen["source_instance_id"],
        "instance_hash": row["instance_hash"] == frozen["instance_hash"],
        "x0_hash": row["x0_hash"] == frozen["x0_hash"],
        "instance_sha256": row["instance_sha256"] == frozen["instance_sha256"],
        "preparation_sha256": row["preparation_sha256"] == frozen["preparation_sha256"],
        "paired_methods": all(row["paired_instance_identity"].values()),
    }
    model = runner.model_identity()
    model_checks = {
        path: model["files"].get(path) == expected
        for path, expected in config["frozen_algorithm_files"].items()
    }
    required = config["required_environment"]
    environment_checks = {
        "python_version": row["environment"]["python_version"] == required["python_version"],
        "gurobipy_version": row["environment"]["gurobipy_version"] == required["gurobipy_version"],
        "gurobi_native_version": row["environment"]["gurobi_native_version"] == required["gurobi_native_version"],
    }
    output = ROOT / config["output_directory"]
    git = git_status_for_execution(output)
    active = active_paired_solver_workers()
    gate = row["resource_gate"]
    gates = {
        "frozen_identity": all(identity_checks.values()),
        "frozen_algorithm": all(model_checks.values()),
        "environment": all(environment_checks.values()),
        "attempt_absent": not row["attempt_exists"],
        "canonical_absent": not row["canonical_result_exists"],
        "startup_memory": gate["available_memory_gib"] >= gate["startup_required_gib"],
        "disk": gate["free_disk_gib"] >= gate["minimum_free_disk_gib"],
        "git_identity": git["clean_for_execution"],
        "no_active_paired_worker": not active,
    }
    nonresource_ready = all(value for key, value in gates.items() if key != "startup_memory")
    if all(gates.values()):
        decision = "AUTHORIZED_READY" if config["formal_run_authorized"] else "READY_FOR_AUTHORIZATION"
    elif nonresource_ready and not gates["startup_memory"]:
        decision = "RESOURCE_BLOCKED"
    else:
        decision = "BLOCKED"
    return {
        "schema": "ef_benders_xxl10_paired_pilot_dry_run_v1",
        "decision": decision,
        "formal_run_authorized": config["formal_run_authorized"],
        "condition": row,
        "identity_checks": identity_checks,
        "model_identity_checks": model_checks,
        "environment_checks": environment_checks,
        "model_identity": model,
        "git": git,
        "active_paired_solver_workers": active,
        "gates": gates,
        "next_attempt": "attempt-001",
        "optimization_calls": 0,
    }


def execute(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: EF-BD XXL10 paired pilot remains disabled")
    dry = build_dry_run(config_path)
    if dry["decision"] != "AUTHORIZED_READY":
        raise RuntimeError(f"EF_BD_XXL10_PILOT_BLOCKED: {dry['gates']}")
    return runner.run_condition(config_path, CONDITION_ID)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    value = execute(args.config.resolve()) if args.execute else build_dry_run(args.config.resolve())
    print(json.dumps(value, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
