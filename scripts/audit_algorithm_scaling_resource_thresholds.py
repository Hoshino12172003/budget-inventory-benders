from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.algorithm_scaling import (
    METHODS,
    SIZES,
    instance_characteristics,
    load_config,
    resource_preflight_passes,
    resource_thresholds,
    validate_config,
)


CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost.yaml"
EVIDENCE = ROOT / "experiments/results/prb_large_scale_simulation_v1/simulation_run_table.csv"
OUTPUT = ROOT / "artifacts/algorithm_scaling_resource_threshold_audit.json"


def _development_evidence() -> list[dict]:
    with EVIDENCE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    evidence = []
    for size in SIZES:
        for method in METHODS:
            group = [row for row in rows if row["scale"] == size.scale and row["method"] == method]
            peaks = sorted(float(row["peak_process_tree_memory_gib"]) for row in group)
            runtimes = sorted(float(row["core_runtime_seconds"]) for row in group if row["core_runtime_seconds"])
            evidence.append({
                "size": size.scale,
                "method": method,
                "observations": len(group),
                "optimal": sum(row["status"] == "OPTIMAL" for row in group),
                "nonoptimal": sum(row["status"] != "OPTIMAL" for row in group),
                "resource_stop": sum(row["status"] == "RESOURCE_STOP" for row in group),
                "peak_process_tree_memory_gib": {
                    "minimum": min(peaks),
                    "median": median(peaks),
                    "maximum": max(peaks),
                    "evidence_type": "EMPIRICAL_DEVELOPMENT_MEASUREMENT",
                },
                "core_runtime_seconds": {
                    "minimum": min(runtimes) if runtimes else None,
                    "median": median(runtimes) if runtimes else None,
                    "maximum": max(runtimes) if runtimes else None,
                    "evidence_type": "EMPIRICAL_DEVELOPMENT_MEASUREMENT",
                },
            })
    return evidence


def main() -> None:
    config = load_config(CONFIG)
    validate_config(config)
    evidence = _development_evidence()
    recommendations = []
    for size in SIZES:
        size_rows = [row for row in evidence if row["size"] == size.scale]
        empirical_peak = max(row["peak_process_tree_memory_gib"]["maximum"] for row in size_rows)
        thresholds = resource_thresholds(config, size.scale)
        process_cap = thresholds["maximum_process_tree_memory_gib"]
        launch_threshold = thresholds["minimum_available_memory_gib"]
        recommendations.append({
            "size": size.scale,
            "empirical_worst_peak_gib": empirical_peak,
            "recommended_minimum_free_ram_gib": launch_threshold,
            "recommended_process_tree_cap_gib": process_cap,
            "system_emergency_floor_gib": thresholds["minimum_system_available_memory_gib"],
            "process_margin_above_empirical_peak_gib": process_cap - empirical_peak,
            "launch_margin_above_empirical_peak_gib": launch_threshold - empirical_peak,
            "reserve_at_process_cap_gib": launch_threshold - process_cap,
            "threshold_evidence_type": "INFERRED_CONSERVATIVE_MARGIN_FROM_EMPIRICAL_PEAK",
            "twelve_gib_preflight_passes": resource_preflight_passes(
                config, size.scale, [12.0, 12.0, 12.0]
            ),
        })
    checks = {
        "evidence_has_90_observations": sum(row["observations"] for row in evidence) == 90,
        "no_development_memory_failure": sum(row["resource_stop"] for row in evidence) == 0,
        "thresholds_are_size_dependent": len({row["recommended_minimum_free_ram_gib"] for row in recommendations}) == 3,
        "process_caps_exceed_empirical_peaks": all(row["process_margin_above_empirical_peak_gib"] >= 1 for row in recommendations),
        "system_reserve_is_at_least_3_gib": all(row["reserve_at_process_cap_gib"] >= 3 for row in recommendations),
        "twelve_gib_allows_L10": recommendations[0]["twelve_gib_preflight_passes"],
        "twelve_gib_allows_XL10": recommendations[1]["twelve_gib_preflight_passes"],
        "twelve_gib_blocks_XXL10": not recommendations[2]["twelve_gib_preflight_passes"],
        "sequential_execution_preserved": config["resource_policy"]["execution"] == "sequential" and config["resource_policy"]["parallel_workers"] == 1,
    }
    payload = {
        "schema": "algorithm_scaling_resource_threshold_audit_v1",
        "status": "RESOURCE_THRESHOLD_AUDIT_PASS" if all(checks.values()) else "RESOURCE_THRESHOLD_AUDIT_FAIL",
        "checks": checks,
        "legacy_18_gib_origin": {
            "finding": "CONSERVATIVE_FIXED_RESERVE_POLICY_NOT_SIZE_SPECIFIC_PEAK_ESTIMATE",
            "preflight_gib": 18,
            "process_cap_gib": 14,
            "nominal_reserve_gib": 4,
            "evidence": [
                "docs/e1c_scaling_resource_audit.md",
                "docs/e1c_development_probe_report.md",
                "experiments/run_prb_large_scale_simulation.py",
            ],
            "interpretation": "18 GiB replaced an unattainable 24-GiB gate because a cleaned 31.5-GiB host exposed about 19.15 GiB; it was not calibrated separately for L10, XL10, or XXL10.",
        },
        "measurement_limits": {
            "gurobi_memory_info": "NOT_RECORDED",
            "shared_instance_preparation_peak": "NOT_RECORDED_IN_TRACKED_SUMMARY",
            "raw_per-run_monitor_logs": "NOT_PRESENT_ON_CURRENT_CODE_LINE",
            "fabricated_values": False,
        },
        "development_evidence": evidence,
        "instance_characteristics": [instance_characteristics(size) for size in SIZES],
        "recommendations": recommendations,
        "formal_optimization_runs_executed_by_audit": 0,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if payload["status"] != "RESOURCE_THRESHOLD_AUDIT_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
