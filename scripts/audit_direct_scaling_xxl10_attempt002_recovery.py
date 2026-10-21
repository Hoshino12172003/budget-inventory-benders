from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.run_direct_scaling_xxl10_paired_pilot import (
    CORE_RUNNER_PATH,
    CORE_RUNNER_SHA256,
    DEFAULT_CONFIG,
    ROOT,
    build_dry_run,
    sha256,
)


DEFAULT_OUTPUT = ROOT / "artifacts/direct_scaling_xxl10_attempt002_recovery_audit.json"


def build_audit(config_path: Path = DEFAULT_CONFIG) -> dict:
    dry = build_dry_run(config_path.resolve())
    actual_core_sha256 = sha256(ROOT / CORE_RUNNER_PATH)
    return {
        "schema": "direct_xxl10_attempt002_recovery_audit_v1",
        "condition_id": dry["condition"]["condition_id"],
        "recovery_attempt": dry["next_attempt"],
        "decision": dry["decision"],
        "optimization_calls": 0,
        "core_runner": {
            "path": CORE_RUNNER_PATH,
            "expected_sha256": CORE_RUNNER_SHA256,
            "actual_sha256": actual_core_sha256,
            "unchanged": actual_core_sha256 == CORE_RUNNER_SHA256,
        },
        "config_sha256": dry["config_sha256"],
        "attempt_001": dry["attempt_001"],
        "identity_checks": dry["identity_checks"],
        "model_identity_checks": dry["model_identity_checks"],
        "environment": dry["environment"],
        "resource_gate": dry["resource_gate"],
        "git": dry["git"],
        "active_paired_solver_workers": dry["active_paired_solver_workers"],
        "gates": dry["gates"],
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
        "decision": audit["decision"],
        "core_runner_unchanged": audit["core_runner"]["unchanged"],
        "attempt_001_classification": audit["attempt_001"]["classification"],
        "optimization_calls": audit["optimization_calls"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
