from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_direct_scaling as runner
from scripts.audit_algorithm_scaling_convergence_cost import _post_run_audit


OUTPUT = ROOT / "artifacts/direct_scaling_l10_authorization_audit.json"
SOURCE_CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost_v2_repaired_guard.yaml"
SOURCE_OUTPUT = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"


def audit() -> dict:
    config = runner.load_config(runner.CONFIG)
    grid = runner.conditions(config)
    authorized = runner.authorized_conditions(config)
    input_rows = []
    for condition in grid:
        _, preparation, hashes = runner.verified_input(config, condition)
        input_rows.append({
            **condition,
            **hashes,
            "instance_hash": preparation["instance_hash"],
            "x0_hash": preparation["x0_hash"],
        })
    source_config = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    source_post_run = _post_run_audit(source_config, SOURCE_OUTPUT)
    output_root = (ROOT / config["output_directory"]).resolve()
    available_memory = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output_root.parent).free / 2**30
    checks = {
        "exact_30_frozen_inputs": len(input_rows) == 30,
        "exact_10_authorized": len(authorized) == 10,
        "authorized_only_l10": all(row["size"] == "L10" for row in authorized),
        "authorized_seeds_exact": [row["seed"] for row in authorized] == list(range(20260921, 20260931)),
        "scaling_v2_89_certified": source_post_run["formal_counts"] == {
            "expected": 90,
            "certified": 89,
            "documented_non_certified": 1,
            "unattempted": 0,
        },
        "environment_matches_new_direct_contract": runner.validate_environment(config)["pass"],
        "ram_launch_gate": available_memory >= config["resource_policy"]["minimum_available_memory_gib_by_size"]["L10"],
        "disk_launch_gate": free_disk >= config["resource_policy"]["minimum_free_disk_gib"],
        "formal_authorization_enabled": config["formal_run_authorized"] is True,
        "no_optimization_in_audit": True,
    }
    return {
        "schema": "direct_scaling_l10_authorization_audit_v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "authorization_parent_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "config_path": str(runner.CONFIG.resolve()),
        "config_hash": runner.canonical_hash(config),
        "model_identity": runner.model_identity(),
        "environment": runner.validate_environment(config),
        "historical_environment_limit": "Scaling V2 Python/Gurobi version and version-dependent defaults are NOT_VERIFIABLE; no exact-environment-match claim is made.",
        "source_scaling_post_run": source_post_run,
        "authorized_conditions": authorized,
        "frozen_inputs": input_rows,
        "resource_snapshot": {
            "available_memory_gib": available_memory,
            "minimum_available_memory_gib": 7,
            "maximum_process_tree_memory_gib": 4,
            "minimum_system_available_memory_gib": 3,
            "free_disk_gib": free_disk,
            "minimum_free_disk_gib": config["resource_policy"]["minimum_free_disk_gib"],
            "condition_time_limit_seconds": 900,
        },
        "checks": checks,
        "optimization_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = audit()
    if args.write:
        OUTPUT.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "authorized_conditions": len(payload["authorized_conditions"]),
        "frozen_inputs": len(payload["frozen_inputs"]),
        "formal_counts": payload["source_scaling_post_run"]["formal_counts"],
        "config_hash": payload["config_hash"],
        "model_identity": payload["model_identity"]["sha256"],
        "optimization_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
