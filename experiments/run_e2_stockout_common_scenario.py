from __future__ import annotations

import argparse
import json
from pathlib import Path

from robust_inventory_reconfiguration.e2_stockout_common_scenario import (
    build_common_scenario_manifest,
    build_policy_identity_manifest,
    file_sha256,
    run_pilot,
    static_source_audit,
    validate_manifest_hash,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
IDENTITY_MANIFEST = ROOT / "artifacts/e2_stockout_policy_identity_manifest.json"
SCENARIO_MANIFEST = ROOT / "experiments/configs/e2_stockout_common_scenario_manifest.json"
STATIC_AUDIT = ROOT / "experiments/audits/e2_stockout_common_scenario_static_audit.json"
PILOT_ROOT = ROOT / "experiments/results/e2_stockout_common_scenario_pilot_v1"
DELIVERY_HASHES = ROOT / "experiments/audits/e2_stockout_delivery_hashes.json"


def freeze() -> None:
    identity = build_policy_identity_manifest(ROOT)
    scenario = build_common_scenario_manifest(ROOT, identity)
    write_json(IDENTITY_MANIFEST, identity)
    write_json(SCENARIO_MANIFEST, scenario)


def audit() -> None:
    identity = json.loads(IDENTITY_MANIFEST.read_text(encoding="utf-8"))
    scenario = json.loads(SCENARIO_MANIFEST.read_text(encoding="utf-8"))
    validate_manifest_hash(identity)
    validate_manifest_hash(scenario)
    source_audit = static_source_audit(
        ROOT
        / "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py"
    )
    checks = {
        "identity_manifest_hash_valid": True,
        "scenario_manifest_hash_valid": True,
        "formal_run_authorized_is_false": scenario["formal_run_authorized"] is False,
        "identity_requires_human_confirmation": (
            identity["identity_freeze_status"]
            == "PARTIAL_REQUIRES_HUMAN_CONFIRMATION"
        ),
        "all_scenario_counts_are_4657": all(
            row["scenario_count"] == 4657 for row in scenario["cases"]
        ),
        "all_dimensions_are_12_by_8": all(
            row["num_regions"] == 12
            and row["num_products"] == 8
            and row["uncertain_components"] == 96
            for row in scenario["cases"]
        ),
        "no_first_stage_solver_call_path": source_audit["pass"],
        "only_existing_is_pilot_authorized": all(
            row["pilot_authorized"] == row["policy_id"].startswith("EXISTING")
            for row in identity["policies"]
        ),
        "no_policy_is_formal_authorized": not any(
            row["formal_authorized"] for row in identity["policies"]
        ),
    }
    audit_result = {
        "schema_version": "1.0",
        "experiment_id": "E2_STOCKOUT_COMMON_SCENARIO_V1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "source_audit": source_audit,
    }
    write_json(STATIC_AUDIT, audit_result)
    if audit_result["status"] != "PASS":
        raise RuntimeError("E2 stockout static audit failed")


def pilot(resume: bool) -> None:
    output_dir = PILOT_ROOT / "PILOT-210202-EXISTING_CANONICAL"
    result = run_pilot(
        ROOT,
        IDENTITY_MANIFEST,
        SCENARIO_MANIFEST,
        output_dir,
        resume=resume,
    )
    print(
        json.dumps(
            {
                "classification": result["classification"],
                "case_id": result["case_id"],
                "policy_id": result["policy_id"],
                "runtime_seconds": result["runtime_seconds"],
                "peak_process_rss_bytes": result["peak_process_rss_bytes"],
                "scenario_count": len(result["evaluation"]["scenarios"]),
            },
            indent=2,
        )
    )


def hashes() -> None:
    paths = (
        "artifacts/e2_stockout_policy_identity_manifest.json",
        "docs/e2_stockout_policy_identity_audit.md",
        "docs/e2_stockout_common_scenario_protocol.md",
        "docs/e2_stockout_pilot_report.md",
        "experiments/configs/e2_stockout_common_scenario_manifest.json",
        "experiments/audits/e2_stockout_common_scenario_static_audit.json",
        "experiments/run_e2_stockout_common_scenario.py",
        "experiments/schemas/e2_stockout_scenario_result.schema.json",
        "experiments/schemas/e2_stockout_checkpoint.schema.json",
        "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py",
        "tests/test_e2_stockout_common_scenario.py",
        "experiments/results/e2_stockout_common_scenario_pilot_v1/PILOT-210202-EXISTING_CANONICAL/checkpoint.json",
        "experiments/results/e2_stockout_common_scenario_pilot_v1/PILOT-210202-EXISTING_CANONICAL/checkpoint.json.sha256",
        "experiments/results/e2_stockout_common_scenario_pilot_v1/PILOT-210202-EXISTING_CANONICAL/hashes.json",
    )
    write_json(
        DELIVERY_HASHES,
        {
            "schema_version": "1.0",
            "classification": "AUDIT_AND_PILOT_DELIVERABLES_NOT_FORMAL_RESULTS",
            "files": {
                path: file_sha256(ROOT / path)
                for path in paths
            },
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("freeze", "audit", "pilot", "resume-pilot", "hashes")
    )
    args = parser.parse_args()
    if args.command == "freeze":
        freeze()
    elif args.command == "audit":
        audit()
    elif args.command == "hashes":
        hashes()
    else:
        pilot(resume=args.command == "resume-pilot")


if __name__ == "__main__":
    main()
