from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_ef_benders_scaling_l10_remaining9 import DEFAULT_CONFIG, EXPECTED, build_dry_run, sha256


def build_audit(config_path: Path = DEFAULT_CONFIG) -> dict:
    dry = build_dry_run(config_path)
    pilot = dry["pilot"]
    ef = pilot["result"]
    source = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard/runs"
    direct = json.loads((ROOT / "experiments/results/direct_scaling_extension_v1/runs/DIRECT_L10_S20260921/result.json").read_text(encoding="utf-8"))
    aggregate = json.loads((source / "ASC_L10_S20260921_AGGREGATE_BENDERS_STRUCTURED_ORACLE/result.json").read_text(encoding="utf-8"))
    prb = json.loads((source / "ASC_L10_S20260921_PRB_BENDERS/result.json").read_text(encoding="utf-8"))
    paired = {"Direct": direct, "EF-BD": ef, "Aggregate-BD": aggregate, "PRB-BD": prb}
    times = {"Direct": direct["T_core_seconds"], "EF-BD": ef["algorithm_core_time"], "Aggregate-BD": aggregate["total_core_solve_time"], "PRB-BD": prb["total_core_solve_time"]}
    engineering = ef["oracle_engineering"]
    known = engineering["oracle_build_seconds"] + ef["oracle_time"] + ef["master_time"]
    checks = {
        "dry_run_ready": dry["decision"] in ("READY_FOR_AUTHORIZATION", "AUTHORIZED_READY"),
        "pilot_archive": all(pilot["checks"].values()),
        "paired_instance_hash": all(row["instance_hash"] == ef["instance_hash"] for row in paired.values()),
        "paired_exact": all(row.get("exact_certification") is True for row in paired.values()),
        "all_nine_identities": dry["gates"]["all_nine_identities"],
        "all_nine_attempts_absent": dry["gates"]["all_attempts_absent"],
        "all_nine_canonical_absent": dry["gates"]["all_canonical_absent"],
        "zero_optimization": dry["optimization_calls"] == 0,
    }
    return {
        "schema": "ef_benders_l10_remaining9_authorization_audit_v1",
        "status": dry["decision"] if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "protocol_id": dry["protocol_id"],
        "config_sha256": sha256(config_path),
        "fixed_denominator": {"completed_pilot": 1, "authorized_remaining": 9, "total": 10},
        "pilot": {
            "condition_id": "EF_L10_S20260921", "attempt": "attempt-001",
            "result_sha256": pilot["file_sha256"]["result.json"],
            "provenance_sha256": pilot["file_sha256"]["provenance.json"],
            "resource_monitor_sha256": pilot["file_sha256"]["resource_monitor.json"],
            "peak_process_tree_memory_gib": pilot["resource_monitor"]["peak_process_tree_memory_gib"],
            "timing_accounting": {
                "algorithm_core_time_seconds": ef["algorithm_core_time"],
                "oracle_build_seconds_in_core": engineering["oracle_build_seconds"],
                "oracle_optimize_seconds_in_core": ef["oracle_time"],
                "master_optimize_seconds_in_core": ef["master_time"],
                "other_core_seconds": ef["algorithm_core_time"] - known,
                "independent_certification_seconds_outside_core": ef["certification_time"],
                "total_time_seconds": ef["total_time"],
            },
        },
        "paired_core_times_seconds": times,
        "paired_time_order_slowest_to_fastest": [name for name, _ in sorted(times.items(), key=lambda item: item[1], reverse=True)],
        "conditions": [{"condition_id": row["condition"]["condition_id"], "seed": row["condition"]["seed"], "instance_hash": row["instance_hash"], "instance_sha256": row["instance_sha256"], "preparation_sha256": row["preparation_sha256"], "expected_attempt": row["expected_attempt"], "identity_status": row["identity_status"]} for row in dry["conditions"]],
        "resource_gate": dry["conditions"][0]["resource_gate"],
        "git": dry["git"], "active_solver_workers": dry["active_solver_workers"],
        "optimization_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit = build_audit(args.config.resolve())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, allow_nan=False))
    return 0 if audit["status"] in ("READY_FOR_AUTHORIZATION", "AUTHORIZED_READY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
