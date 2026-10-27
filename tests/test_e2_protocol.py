from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/configs/formal/e2_existing_nominal_robust_authorization.json"

def test_e2_policy_and_gamma_contract() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["formal_run_authorized"] is True
    assert manifest["authorization_transition"] == [False, True]
    assert manifest["Gamma_nominal_plan"] == 0
    assert manifest["Gamma_robust_plan"] == manifest["Gamma_eval"] == 2
    assert manifest["beta"] == 1.0 and manifest["lambda_R"] == 0.05
    assert manifest["e3_e7_authorization"] is False
    assert len(manifest["authorized_run_ids"]) == 24

def test_e2_identity_and_reuse_contract() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    historical = json.loads(
        (ROOT / "experiments/audits/e2_historical_runner_hash_audit.json").read_text(
            encoding="utf-8"
        )
    )
    runner_path = "experiments/run_e2_policy_local.py"
    historical_blob = subprocess.check_output(
        [
            "git",
            "cat-file",
            "blob",
            f"{historical['historical_runner_commit']}:{runner_path}",
        ],
        cwd=ROOT,
    )
    assert hashlib.sha256(historical_blob).hexdigest() == manifest["runner_sha256"]
    assert historical["historical_blob_matches_manifest"] is True
    assert historical["current_committed_runner_matches_manifest"] is False
    audit = json.loads((ROOT / "artifacts/e2_protocol_static_audit.json").read_text(encoding="utf-8"))
    assert all(all(checks.values()) for checks in audit["identity_checks"].values())
    assert audit["e1_robust_reuse_count"] == 8
    assert audit["direct_reruns"] == 0 and audit["e2_executed"] is False

def test_e2_output_schemas_are_header_only() -> None:
    for filename, expected in (("table_e2_policy_comparison.csv", 32), ("table_e2_policy_contrasts.csv", 17)):
        with (ROOT / filename).open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        assert len(rows) == 1 and len(rows[0]) == expected

def test_e2_runner_refuses_overwrite_and_unauthorized(monkeypatch, tmp_path) -> None:
    import experiments.run_e2_policy_local as runner
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["formal_run_authorized"] = False
    temporary = tmp_path / "authorization.json"
    temporary.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(runner, "MANIFEST", temporary)
    with pytest.raises(PermissionError):
        runner.validate_gate("210202", "EXISTING", tmp_path)

def test_existing_semantics_are_explicit() -> None:
    text = (ROOT / "docs/e2_existing_nominal_robust_protocol.md").read_text(encoding="utf-8")
    assert "fixes `x=x0`, `y=y0`, and both adjustment matrices to zero" in text
    assert "Direct is not run" in text
    assert "Gamma_eval=2" in text
