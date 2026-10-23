from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_ef_benders_scaling_xl10_remaining9 import DEFAULT_CONFIG, build_dry_run, sha256


def build_audit(config_path: Path = DEFAULT_CONFIG) -> dict:
    dry = build_dry_run(config_path)
    pilot = dry["pilot"]
    checks = {
        "dry_run_ready": dry["decision"] in ("READY_FOR_AUTHORIZATION", "AUTHORIZED_READY"),
        "authorization_enabled": dry["formal_run_authorized"] is True,
        "pilot_archive": all(pilot["checks"].values()),
        "algorithm_identity": all(dry["algorithm_identity_checks"].values()),
        "environment_identity": all(dry["environment_checks"].values()),
        "all_nine_identities": dry["gates"]["all_nine_identities"],
        "all_nine_attempts_absent": dry["gates"]["all_attempts_absent"],
        "all_nine_canonical_absent": dry["gates"]["all_canonical_absent"],
        "zero_optimization": dry["optimization_calls"] == 0,
    }
    return {
        "schema": "ef_benders_xl10_remaining9_readiness_audit_v1",
        "status": "AUTHORIZED_READY" if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "protocol_id": dry["protocol_id"],
        "config_path": str(config_path.resolve()),
        "config_sha256": sha256(config_path),
        "fixed_denominator": {"completed_pilot": 1, "remaining": 9, "total_xl10": 10},
        "pilot": {
            "condition_id": pilot["condition_id"],
            "attempt": pilot["attempt"],
            "result_sha256": pilot["file_sha256"]["result.json"],
            "provenance_sha256": pilot["file_sha256"]["provenance.json"],
            "resource_monitor_sha256": pilot["file_sha256"]["resource_monitor.json"],
            "peak_process_tree_memory_gib": pilot["resource_monitor"]["peak_process_tree_memory_gib"],
            "result_summary": {
                key: pilot["result"][key]
                for key in (
                    "solver_status", "exact_certification", "cut_validity", "final_objective",
                    "algorithm_core_time", "iterations", "cuts_added", "oracle_time",
                    "certification_time", "total_time", "instance_hash",
                )
            },
            "timing_accounting": pilot["timing_accounting"],
        },
        "conditions": [
            {
                "condition_id": row["condition"]["condition_id"],
                "seed": row["condition"]["seed"],
                "instance_hash": row["instance_hash"],
                "x0_hash": row["x0_hash"],
                "instance_sha256": row["instance_sha256"],
                "preparation_sha256": row["preparation_sha256"],
                "paired_instance_identity": row["paired_instance_identity"],
                "expected_attempt": row["expected_attempt"],
                "attempt_exists": row["attempt_exists"],
                "canonical_exists": row["canonical_result_exists"],
                "identity_status": row["identity_status"],
            }
            for row in dry["conditions"]
        ],
        "resource_policy": dry["resource_policy"],
        "resource_gate_snapshot": dry["conditions"][0]["resource_gate"],
        "failure_policy": dry["failure_policy"],
        "git": dry["git"],
        "active_solver_workers": dry["active_solver_workers"],
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
    return 0 if audit["status"] == "AUTHORIZED_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
