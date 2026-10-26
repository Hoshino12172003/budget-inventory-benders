from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "experiments/audits/e2_historical_runner_hash_audit.json"


def test_historical_runner_blob_matches_the_historical_manifest() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    runner_path = "experiments/run_e2_policy_local.py"
    historical_blob = subprocess.check_output(
        [
            "git",
            "cat-file",
            "blob",
            f"{audit['historical_runner_commit']}:{runner_path}",
        ],
        cwd=ROOT,
    )
    assert hashlib.sha256(historical_blob).hexdigest() == audit[
        "historical_manifest_runner_sha256"
    ]
    assert audit["historical_blob_matches_manifest"] is True


def test_current_runner_mismatch_is_preserved_as_audit_evidence() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "HISTORICAL_IDENTITY_MISMATCH_CONFIRMED"
    assert audit["current_committed_runner_matches_manifest"] is False
    assert audit["current_worktree_runner_matches_manifest"] is False
    assert audit["semantic_change"]["changed"] is True
    assert audit["historical_e2_raw_results_present"] is False
