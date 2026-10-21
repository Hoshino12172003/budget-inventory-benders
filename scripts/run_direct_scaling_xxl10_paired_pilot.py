from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_direct_scaling as runner


DEFAULT_CONFIG = ROOT / "experiments/configs/development/direct_scaling_xxl10_paired_pilot_v1.yaml"
CONDITION_ID = "DIRECT_XXL10_S20260921"


def active_paired_solver_workers() -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (process.info.get("name") or "").lower()
            command = " ".join(process.info.get("cmdline") or []).lower()
            worker = "--worker" in command and (
                "run_direct_scaling.py" in command or "run_ef_benders_scaling.py" in command
            )
            if name.startswith("gurobi") or worker:
                found.append({"pid": process.info["pid"], "name": name, "cmdline": process.info.get("cmdline") or []})
        except psutil.Error:
            continue
    return found


def git_status_for_execution(output: Path) -> dict:
    entries = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True
    ).splitlines()
    allowed = (
        output.resolve().relative_to(ROOT.resolve()).as_posix() + "/",
        "experiments/results/basic_benders_scaling_development_v1/",
        "experiments/results/ef_benders_scaling_development_v1/",
        "experiments/results/ef_benders_scaling_xl10_pilot_v1/",
        "experiments/results/ef_benders_scaling_xl10_remaining9_v1/",
        "experiments/results/ef_benders_scaling_xxl10_paired_pilot_v1/",
        "experiments/results/ef_benders_scaling_xxl10_remaining9_v1/",
        "artifacts/direct_ef_benders_xxl10_paired_preparation_audit.json",
    )
    unexpected = [line for line in entries if not line[3:].replace("\\", "/").startswith(allowed)]
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "clean_for_execution": not unexpected,
        "unexpected": unexpected,
    }


def validate_protocol(config: dict) -> None:
    policy = config["resource_policy"]
    checks = {
        "protocol": config.get("resource_protocol_id") == "DIRECT_XXL10_PAIRED_PILOT_V1_METHOD2_THREADS2",
        "scope": config.get("authorized_condition_ids") == [CONDITION_ID],
        "authorization_boolean": isinstance(config.get("formal_run_authorized"), bool),
        "dimensions": config.get("sizes") == [{"label": "XXL10", "I": 36, "R": 36, "J": 16}],
        "science": config.get("fixed_scientific_parameters") == {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "SL": 0.90, "phi_multiplier": 1.85},
        "solver": config.get("solver_parameters", {}).get("Method") == 2 and config.get("solver_parameters", {}).get("Threads") == 2 and config.get("solver_parameters", {}).get("MIPGap") == 0.0,
        "resource": (
            policy["maximum_process_tree_memory_gib_by_size"] == {"XXL10": 13}
            and policy["minimum_available_memory_gib_by_size"] == {"XXL10": 16}
            and policy["minimum_system_available_memory_gib"] == 3
            and policy["minimum_free_disk_gib"] == 20
            and policy["condition_time_limit_seconds"] == 900
            and policy["memory_monitor_interval_seconds"] == 0.25
            and policy["parallel_workers"] == 1
            and policy["retry_policy"] == "no_automatic_retry"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"Direct XXL10 paired-pilot protocol mismatch: {checks}")


def build_dry_run(config_path: Path = DEFAULT_CONFIG) -> dict:
    config = runner.load_config(config_path)
    validate_protocol(config)
    condition = runner.authorized_conditions(config)[0]
    instance, preparation, hashes = runner.verified_input(config, condition)
    frozen = config["frozen_input_identity"]
    identity_checks = {
        "condition_id": condition["condition_id"] == frozen["condition_id"],
        "source_instance_id": preparation["instance_id"] == frozen["source_instance_id"],
        "dimensions": (instance.num_depots, instance.num_regions, instance.num_products) == (36, 36, 16),
        "instance_hash": preparation["instance_hash"] == frozen["instance_hash"],
        "x0_hash": preparation["x0_hash"] == frozen["x0_hash"],
        "instance_sha256": hashes["instance_sha256"] == frozen["instance_sha256"],
        "preparation_sha256": hashes["preparation_sha256"] == frozen["preparation_sha256"],
    }
    model = runner.model_identity()
    model_checks = {path: model["files"].get(path) == value for path, value in config["frozen_model_files"].items()}
    environment = runner.validate_environment(config)
    output = ROOT / config["output_directory"]
    policy = config["resource_policy"]
    available = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output.parent).free / 2**30
    attempt = f"attempt-{runner.next_attempt_number(output, CONDITION_ID):03d}"
    git = git_status_for_execution(output)
    active = active_paired_solver_workers()
    gates = {
        "frozen_identity": all(identity_checks.values()),
        "frozen_model": all(model_checks.values()),
        "environment": environment["pass"],
        "attempt_absent": attempt == "attempt-001",
        "canonical_absent": not (output / "runs" / CONDITION_ID).exists(),
        "startup_memory": available >= 16,
        "disk": free_disk >= 20,
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
        "schema": "direct_xxl10_paired_pilot_dry_run_v1",
        "decision": decision,
        "formal_run_authorized": config["formal_run_authorized"],
        "condition": condition,
        "next_attempt": attempt,
        "input_identity": {
            "source_instance_id": preparation["instance_id"],
            "instance_hash": preparation["instance_hash"],
            "x0_hash": preparation["x0_hash"],
            **hashes,
        },
        "identity_checks": identity_checks,
        "model_identity_checks": model_checks,
        "environment": environment,
        "resource_gate": {
            "available_memory_gib": available,
            "startup_required_gib": 16,
            "process_tree_cap_gib": 13,
            "system_available_floor_gib": 3,
            "free_disk_gib": free_disk,
            "minimum_free_disk_gib": 20,
            "time_limit_seconds": 900,
            "monitor_interval_seconds": 0.25,
        },
        "git": git,
        "active_paired_solver_workers": active,
        "gates": gates,
        "config_sha256": runner.file_sha256(config_path),
        "config_identity": runner.canonical_hash(config),
        "model_identity": model,
        "optimization_calls": 0,
    }


def execute(config_path: Path = DEFAULT_CONFIG) -> None:
    config = runner.load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: Direct XXL10 paired pilot remains disabled")
    dry = build_dry_run(config_path)
    if dry["decision"] != "AUTHORIZED_READY":
        raise RuntimeError(f"DIRECT_XXL10_PILOT_BLOCKED: {dry['gates']}")
    condition = runner.authorized_conditions(config)[0]
    output = ROOT / config["output_directory"]
    original = runner.validate_execution_gate

    def validated_gate(_config, _condition, _output):
        if _condition["condition_id"] != CONDITION_ID or _output.resolve() != output.resolve():
            raise RuntimeError("Direct XXL10 paired-pilot execution identity mismatch")
        current = build_dry_run(config_path)
        if current["decision"] != "AUTHORIZED_READY":
            raise RuntimeError(f"DIRECT_XXL10_PILOT_BLOCKED: {current['gates']}")
        return current["resource_gate"]

    try:
        runner.validate_execution_gate = validated_gate
        runner.run_monitored(config_path, config, condition, output)
    finally:
        runner.validate_execution_gate = original


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        execute(args.config.resolve())
    else:
        print(json.dumps(build_dry_run(args.config.resolve()), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
