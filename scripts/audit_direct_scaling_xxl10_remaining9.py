from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_direct_scaling_xxl10_remaining9 import DEFAULT_CONFIG, build_dry_run, sha256


DEFAULT_OUTPUT = ROOT / "artifacts/direct_scaling_xxl10_remaining9_readiness_audit.json"


def build_audit(config_path: Path = DEFAULT_CONFIG) -> dict:
    dry = build_dry_run(config_path.resolve())
    return {
        "schema": "direct_xxl10_remaining9_readiness_audit_v1",
        "status": dry["decision"],
        "formal_run_authorized": dry["formal_run_authorized"],
        "fixed_denominator": dry["fixed_denominator"],
        "config_sha256": dry["config_sha256"],
        "core_runner_sha256": sha256(ROOT / "experiments/run_direct_scaling.py"),
        "pilot": dry["pilot"],
        "baseline_archives": dry["baseline_archives"],
        "conditions": dry["conditions"],
        "model_identity": dry["model_identity"],
        "environment": dry["environment"],
        "resource_policy": dry["resource_policy"],
        "resource_gate": dry["resource_gate"],
        "git": dry["git"],
        "active_workers": dry["active_workers"],
        "gates": dry["gates"],
        "optimization_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    audit = build_audit(args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": audit["status"], "identity_passes": sum(
            all(row["identity_checks"].values()) and all(row["paired_identity_checks"].values())
            for row in audit["conditions"]
        ), "optimization_calls": 0,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
