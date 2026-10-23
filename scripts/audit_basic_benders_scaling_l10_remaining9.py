from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_basic_benders_l10_pilot import build_audit as build_pilot_audit
from scripts.run_basic_benders_scaling_l10_remaining9 import DEFAULT_CONFIG, EXPECTED, build_dry_run


OUTPUT = ROOT / "artifacts/basic_benders_l10_remaining9_static_audit.json"
REPORT = ROOT / "docs/basic_benders_l10_remaining9_readiness.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit() -> dict:
    dry = build_dry_run(DEFAULT_CONFIG)
    pilot, _, _ = build_pilot_audit()
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    batch_source = (ROOT / "scripts/run_basic_benders_scaling_l10_remaining9.py").read_text(encoding="utf-8")
    runner_source = (ROOT / "experiments/run_basic_benders_scaling.py").read_text(encoding="utf-8")
    checks = {
        "authorization_closed": config["formal_run_authorized"] is False,
        "exact_scope": config["authorized_condition_ids"] == EXPECTED,
        "fixed_denominator_nine": dry["fixed_denominator"] == 9,
        "all_identity_checks": dry["gates"]["all_nine_identities"],
        "all_attempts_absent": dry["gates"]["all_attempts_absent"],
        "all_canonical_absent": dry["gates"]["all_canonical_results_absent"],
        "pilot_preserved": pilot["status"] == "PASS_EXACT_CERTIFIED_DEVELOPMENT_PILOT",
        "sequential_execution": 'for condition_id in EXPECTED:' in batch_source,
        "preflight_each_condition": "runner.validate_execution_gate(config_path, condition_id)" in batch_source,
        "no_automatic_retry": 'attempt = output / "worker_logs" / selected["condition_id"] / "attempt-001"' in runner_source,
        "failures_preserved": '"RESOURCE_OR_TIME_FAILURE"' in batch_source,
        "integrity_failure_stops": 'INTEGRITY_FAILURE stops batch' in batch_source,
        "zero_optimization_dry_run": dry["optimization_calls"] == 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"remaining-nine static audit failed: {checks}")
    decision = "READY_FOR_AUTHORIZATION" if all(dry["gates"].values()) else "BLOCKED"
    return {
        "schema": "basic_benders_l10_remaining9_static_audit_v1",
        "status": "STATIC_AUDIT_PASS",
        "decision": decision,
        "formal_run_authorized": False,
        "optimization_calls": 0,
        "checks": checks,
        "protocol_id": config["protocol_id"],
        "config_sha256": sha256(DEFAULT_CONFIG),
        "runner_sha256": sha256(ROOT / "experiments/run_basic_benders_scaling.py"),
        "batch_runner_sha256": sha256(ROOT / "scripts/run_basic_benders_scaling_l10_remaining9.py"),
        "conditions": [
            {
                "condition_id": row["condition"]["condition_id"],
                "seed": row["condition"]["seed"],
                "expected_attempt": row["expected_attempt"],
                "instance_hash": row["instance_hash"],
                "x0_hash": row["x0_hash"],
                "instance_sha256": row["instance_sha256"],
                "preparation_sha256": row["preparation_sha256"],
                "identity_status": row["identity_status"],
            }
            for row in dry["conditions"]
        ],
        "resource_gate": dry["conditions"][0]["resource_gate"],
        "failure_policy": config["failure_policy"],
        "pilot_preservation": {
            "condition_id": pilot["condition_id"],
            "attempt": pilot["attempt"],
            "result_sha256": sha256(
                ROOT / "experiments/results/basic_benders_scaling_development_v1/runs/BASIC_L10_S20260921/result.json"
            ),
            "status": pilot["status"],
        },
        "dry_run": dry,
    }


def write_outputs() -> dict:
    audit = build_audit()
    OUTPUT.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    resource = audit["resource_gate"]
    REPORT.write_text("\n".join([
        "# Basic-BD L10 remaining-nine readiness",
        "",
        f"Decision: `{audit['decision']}`",
        "",
        "Authorization remains false and the dry-run made zero optimization calls.",
        "",
        "## Fixed scope",
        "",
        "- Conditions: `BASIC_L10_S20260922` through `BASIC_L10_S20260930` (nine fixed denominator conditions).",
        "- Each next identity is `attempt-001`; no attempt or canonical output currently exists for the nine conditions.",
        "- The certified `BASIC_L10_S20260921 / attempt-001` archive remains unchanged.",
        "",
        "## Resource contract",
        "",
        f"- 900 seconds, 4 GiB process tree, 7 GiB startup gate, 3 GiB system floor, 20 GiB disk gate, and 0.25-second monitoring. Snapshot available RAM: {resource['available_memory_gib']:.3f} GiB; free disk: {resource['free_disk_gib']:.3f} GiB.",
        "- Conditions run serially in seed order. Resource/time failures are preserved and may continue only after worker exit and renewed gates. Identity, hash, numerical-certification, or unknown worker failures stop the batch immediately.",
        "",
        "## Execution command after a separate authorization commit",
        "",
        "```powershell",
        "python scripts\\run_basic_benders_scaling_l10_remaining9.py --config experiments\\configs\\development\\basic_benders_scaling_l10_remaining9_v1.yaml --execute",
        "```",
    ]) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    audit = write_outputs()
    print(json.dumps({
        "status": audit["status"],
        "decision": audit["decision"],
        "formal_run_authorized": audit["formal_run_authorized"],
        "conditions": len(audit["conditions"]),
        "optimization_calls": audit["optimization_calls"],
    }, indent=2))
