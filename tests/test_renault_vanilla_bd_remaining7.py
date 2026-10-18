from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_renault_vanilla_bd_remaining7.py"
SPEC = importlib.util.spec_from_file_location("renault_remaining7", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_remaining_set_is_fixed_and_excludes_completed_baseline() -> None:
    assert runner.CASES == (
        "210628", "210129", "210310", "210330", "210323", "210428", "210611"
    )
    assert "210202" not in runner.CASES


def test_baseline_hash_manifest_and_code_identity_pass() -> None:
    audit = runner.verify_baseline()
    assert audit["manifest_entries"] == 20
    assert audit["manifest_failures"] == []
    assert audit["valid_exact_pair"] is True


def test_static_protocol_audit_passes_without_optimization() -> None:
    audit = runner.static_protocol_audit()
    assert audit["status"] == "PASS"
    assert set(audit["cases"]) == set(runner.CASES)
    assert all(row["Gamma"] == 2 for row in audit["cases"].values())
    assert all(row["lambda_R"] == 0.05 for row in audit["cases"].values())
    assert all(row["scenario_count"] <= 5000 for row in audit["cases"].values())
