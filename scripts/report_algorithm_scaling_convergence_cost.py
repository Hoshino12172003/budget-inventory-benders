from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.algorithm_scaling import (
    enumerate_conditions,
    load_config,
    validate_config,
)
from robust_inventory_reconfiguration.algorithm_scaling_reporting import (
    CHARACTERISTIC_FIELDS,
    RESULT_FIELDS,
    TRAJECTORY_FIELDS,
    write_reports,
)


CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost.yaml"


def load_complete_results(config: dict):
    output_root = ROOT / config["output_directory"]
    results = []
    trajectories = []
    characteristics = []
    seen_instances = set()
    for condition in enumerate_conditions():
        run_root = output_root / "runs" / condition.condition_id
        result = json.loads((run_root / "result.json").read_text(encoding="utf-8"))
        monitor_root = output_root / "worker_logs" / condition.condition_id
        monitor_paths = sorted(monitor_root.glob("attempt-*/monitor.json"))
        if monitor_paths:
            monitor = json.loads(monitor_paths[-1].read_text(encoding="utf-8"))
            result["peak_process_tree_memory_gib"] = monitor["peak_process_tree_memory_gib"]
        raw_trajectory = json.loads((run_root / "iteration_trajectory.json").read_text(encoding="utf-8"))
        results.append(result)
        for item in raw_trajectory:
            trajectories.append({
                "experiment_id": result["experiment_id"],
                "condition_id": result["condition_id"],
                "method": result["method"],
                "size": result["size"],
                "seed": result["seed"],
                "instance_id": result["instance_id"],
                **item,
            })
        if result["instance_id"] not in seen_instances:
            preparation = json.loads((output_root / "instances" / result["size"] / str(result["seed"]) / "preparation.json").read_text(encoding="utf-8"))
            characteristics.append({
                "instance_id": result["instance_id"],
                "instance_hash": result["instance_hash"],
                "seed": result["seed"],
                **preparation["characteristics"],
            })
            seen_instances.add(result["instance_id"])
    return results, trajectories, characteristics


def main() -> None:
    parser = argparse.ArgumentParser(description="Algorithm scaling formal reporting")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    validate_config(config)
    if args.validate_only:
        print(json.dumps({
            "result_fields": RESULT_FIELDS,
            "trajectory_fields": TRAJECTORY_FIELDS,
            "characteristic_fields": CHARACTERISTIC_FIELDS,
            "required_outputs": config["required_outputs"],
        }, indent=2))
        return
    results, trajectories, characteristics = load_complete_results(config)
    classification = write_reports(
        results, trajectories, characteristics,
        ROOT / config["output_directory"],
        objective_tolerance=config["algorithm"]["objective_equivalence_tolerance"],
    )
    print(json.dumps({"status": "REPORTING_COMPLETE", "classification": classification}, indent=2))


if __name__ == "__main__":
    main()
