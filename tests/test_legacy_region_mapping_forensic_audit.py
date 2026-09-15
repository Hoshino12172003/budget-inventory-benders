from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "artifacts" / "legacy_region_mapping_recovery_summary.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_forensic_decision_does_not_claim_unproved_recovery() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "LEGACY_REGION_MAPPING_NOT_RECOVERABLE"
    assert summary["recovery_level"] == "D"
    assert summary["formal_base_demand_validation"]["210202"]["l1_error"] is None
    assert summary["formal_base_demand_validation"]["210628"]["l1_error"] is None
    assert summary["extension_audit"]["status"] == "NOT_ASSESSED_NO_RECOVERED_MAPPING"


def test_existing_formal_instances_are_unchanged() -> None:
    assert sha256(ROOT / "data" / "formal_instances" / "210202.json") == (
        "d40beacd55c43b045db79140e38ee211e904dd72f7d6ca95dfb34c1f5a2cdb35"
    )
    assert sha256(ROOT / "data" / "formal_instances" / "210628.json") == (
        "32321a9dc18d1b0134a73b45ed4695f44c8425f544ceb498d7c8f7eeda8d6ba9"
    )


def test_recovery_outputs_are_fail_closed() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert not (ROOT / "artifacts" / "legacy_region_mapping_v1.json").exists()
    assert not (ROOT / "table_legacy_region_mapping_validation.csv").exists()
    assert not (ROOT / "table_legacy_region_extension_audit.csv").exists()
    assert summary["optimization_solves_executed"] == 0
    assert summary["existing_formal_results_modified"] is False
    assert summary["existing_formal_artifacts_modified"] is False
    assert summary["e2_e7_authorization"] is False
