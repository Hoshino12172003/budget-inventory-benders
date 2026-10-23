from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_ef_benders_scaling_l10_preparation import theoretical_size
from scripts.run_ef_benders_scaling_xl10_pilot import (
    DEFAULT_CONFIG,
    build_dry_run,
    l10_frozen_audit,
    sha256,
)


DIRECT_ROOT = ROOT / "experiments/results/direct_scaling_extension_v1"


def direct_xl10_resource_evidence() -> dict:
    rows = []
    for path in sorted(DIRECT_ROOT.glob("worker_logs/DIRECT_XL10_S*/attempt-*/resource_monitor.json")):
        monitor = json.loads(path.read_text(encoding="utf-8"))
        rows.append({
            "attempt_path": str(path.parent.relative_to(DIRECT_ROOT)),
            "peak_process_tree_memory_gib": monitor.get("peak_process_tree_memory_gib"),
            "stop_reason": monitor.get("stop_reason"),
            "worker_return_code": monitor.get("worker_return_code"),
        })
    same_seed = [row for row in rows if row["attempt_path"].startswith("worker_logs\\DIRECT_XL10_S20260921\\")]
    certified = json.loads((DIRECT_ROOT / "runs/DIRECT_XL10_S20260921/result.json").read_text(encoding="utf-8"))
    return {
        "attempts": rows,
        "same_seed_attempts": same_seed,
        "same_seed_certified_core_time_seconds": certified["T_core_seconds"],
        "same_seed_certified_instance_hash": certified["instance_hash"],
    }


def build_audit(config_path: Path = DEFAULT_CONFIG) -> dict:
    dry = build_dry_run(config_path)
    l10 = l10_frozen_audit()
    l10_size = theoretical_size(25, 24, 12, 2)
    xl10_size = theoretical_size(30, 30, 14, 2)
    ratio = {
        key: xl10_size["ef_oracle"][key] / l10_size["ef_oracle"][key]
        for key in ("variables", "constraints", "nonzeros")
    }
    projected_peak = l10["maximum_peak_process_tree_memory_gib"] * ratio["nonzeros"]
    direct = direct_xl10_resource_evidence()
    checks = {
        "authorization_boolean": isinstance(dry["formal_run_authorized"], bool),
        "dry_run_ready": dry["decision"] in ("READY_FOR_AUTHORIZATION", "AUTHORIZED_READY"),
        "zero_optimization": dry["optimization_calls"] == 0,
        "l10_frozen_10_of_10": l10["certified"] == l10["expected"] == 10,
        "identity": all(dry["identity_checks"].values()),
        "environment": all(dry["environment_checks"].values()),
        "attempt_absent": dry["gates"]["attempt_absent"],
        "canonical_absent": dry["gates"]["canonical_absent"],
        "scope": dry["condition"]["condition"]["condition_id"] == "EF_XL10_S20260921",
        "static_direct_count_match": xl10_size["direct_extensive_form"] == {
            "variables": 6075177, "constraints": 405479, "nonzeros": 18422892,
        },
    }
    return {
        "schema": "ef_benders_xl10_pilot_preparation_audit_v1",
        "status": dry["decision"] if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "optimization_calls": 0,
        "config_path": str(config_path.resolve()),
        "config_sha256": sha256(config_path),
        "condition_id": "EF_XL10_S20260921",
        "next_attempt": "attempt-001",
        "dry_run": dry,
        "l10_frozen_baseline": l10,
        "model_size": {
            "XL10": xl10_size,
            "relative_to_L10": ratio,
            "count_evidence": "Exact algebraic count from the current model structure; no Gurobi model was built or optimized.",
        },
        "resource_assessment": {
            "configured_process_cap_gib": 8,
            "configured_startup_gate_gib": 12,
            "configured_system_floor_gib": 3,
            "maximum_observed_ef_l10_peak_gib": l10["maximum_peak_process_tree_memory_gib"],
            "linear_nonzero_scaled_projection_gib": projected_peak,
            "same_seed_direct_xl10_certified_peak_gib": next(
                row["peak_process_tree_memory_gib"]
                for row in direct["same_seed_attempts"]
                if row["stop_reason"] is None and row["worker_return_code"] == 0
            ),
            "direct_evidence": direct,
            "risk": "MODERATE_TO_HIGH",
            "conclusion": "Eight GiB is a conservative single-pilot safety cap, not a completion guarantee. It is 3.193 GiB above the linear EF-L10 nonzero-scaled projection and 1.148 GiB above the certified same-seed Direct XL10 peak. The 12 GiB startup gate leaves 4 GiB at the cap, above the 3 GiB system floor.",
        },
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
