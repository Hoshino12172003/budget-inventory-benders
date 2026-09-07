from __future__ import annotations

import hashlib
import json
from pathlib import Path

from robust_inventory_reconfiguration.formal_acceptance import AUTHORIZED_RUN_IDS
from robust_inventory_reconfiguration.formal_protocol import RESULT_FIELDS, load_formal_config


ROOT = Path("experiments/results/formal_acceptance_batch_1/attempt_001")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_acceptance_summary_and_run_set_pass_exactly_once() -> None:
    summary = load_json(ROOT / "acceptance_summary.json")
    assert summary["status"] == "FORMAL_ACCEPTANCE_PASS"
    assert summary["run_count"] == 5
    assert tuple(summary["authorized_run_ids"]) == AUTHORIZED_RUN_IDS
    assert summary["failures"] == []
    assert summary["retries"] == 0
    assert summary["full_e1_e7_authorization"] is False
    assert not (ROOT / "failure.json").exists()


def test_each_result_matches_the_frozen_formal_schema_and_provenance() -> None:
    for run_id in AUTHORIZED_RUN_IDS:
        result = load_json(ROOT / "runs" / run_id / "result.json")
        provenance = load_json(ROOT / "runs" / run_id / "provenance.json")
        assert set(result) == set(RESULT_FIELDS)
        assert result["termination_status"] == "OPTIMAL"
        assert result["certification_status"].startswith("CERTIFIED")
        assert result["case_id"] == "210202"
        assert result["git_commit"] == "1b06be7cc3a6108871d0dc40c6d0da2165b470b7"
        assert provenance["acceptance_run_id"] == run_id
        assert provenance["source_data_hash"] == result["source_data_hash"]
        assert provenance["processed_data_hash"] == result["data_hash"]
        assert provenance["x0_hash"] == result["x0_hash"]
        assert provenance["formal_config_hash"] == result["config_hash"]
        assert provenance["solver_profile"] == "gurobi-balanced-1e-8-v1"


def test_direct_prb_and_e2_semantic_audits_pass() -> None:
    comparison = load_json(ROOT / "diagnostics" / "direct_prb_comparison.json")
    semantics = load_json(ROOT / "diagnostics" / "e2_semantics.json")
    assert comparison["status"] == "PASS"
    assert comparison["objective_absolute_difference"] <= 1e-4
    assert comparison["first_stage_absolute_difference"] <= 1e-4
    assert comparison["recourse_absolute_difference"] <= 1e-4
    assert semantics["status"] == "PASS"
    assert semantics["A3_existing"]["x_equals_x0"]
    assert semantics["A3_existing"]["RI"] <= 1e-6
    assert semantics["A4_nominal"] == {
        "reconfiguration_allowed": True,
        "Gamma": 0,
        "uncertainty_budget_active": False,
    }
    assert semantics["A5_robust"]["Gamma"] == 2
    assert semantics["A5_robust"]["robust_recourse_active"]
    assert semantics["A5_robust"]["certified"]


def test_checkpoint_resume_and_all_recorded_hashes_pass() -> None:
    checkpoint = load_json(ROOT / "diagnostics" / "checkpoint_resume_audit.json")
    assert checkpoint == {
        "status": "PASS",
        "checkpoint_identity_valid": True,
        "restart_identity_valid": True,
        "config_hash_valid": True,
        "case_hash_valid": True,
    }
    hashes = load_json(ROOT / "hashes.json")
    for relative, expected in hashes.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected, relative


def test_authorization_manifest_hash_and_full_configs_remain_safe() -> None:
    manifest_hash = hashlib.sha256((ROOT / "authorization_manifest.yaml").read_bytes()).hexdigest()
    provenance = load_json(ROOT / "provenance.json")
    assert provenance["authorization_manifest_hash"] == manifest_hash
    assert all(
        run["authorization_manifest_hash"] == manifest_hash
        for run in provenance["runs"].values()
    )
    for path in Path("experiments/configs/formal").glob("e*.yaml"):
        assert load_formal_config(path)["formal_run_authorized"] is False
