from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "artifacts/e1c_development_probe_summary.json"


def test_resource_preflight_blocks_all_probe_runs_fail_closed() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "E1C_DEVELOPMENT_RESOURCE_BLOCKED"
    assert summary["development_only"] is True
    assert summary["paper_final_observation"] is False
    assert summary["formal_run_authorized"] is False
    assert summary["development_probe_authorized"] is True
    assert summary["probe_execution_started"] is False
    assert summary["preflight"]["pass"] is False
    assert max(summary["preflight"]["available_memory_gib_samples"]) < 24
    assert len(summary["probe_results"]) == 8
    assert all(
        row["status"] == "NOT_RUN_RESOURCE_PREFLIGHT_BLOCK"
        for row in summary["probe_results"]
    )
    assert summary["formal_optimization_runs"] == 0
    assert summary["development_optimization_runs"] == 0


def test_authorization_is_narrow_and_development_only() -> None:
    authorization = json.loads(
        (ROOT / "experiments/configs/e1c_development_probe_authorization.json").read_text(
            encoding="utf-8"
        )
    )
    assert authorization["development_probe_authorized"] is True
    assert authorization["formal_run_authorized"] is False
    assert authorization["seed"] == 20260911
    assert authorization["Gamma"] == 2
    assert authorization["method_order"] == [
        "pure_benders",
        "prb_benders",
        "aggregate_benders_structured_oracle",
        "direct_exact",
    ]
    assert authorization["authorized_instances"] == [
        {"scale": "L", "I": 25, "R": 24, "J": 12},
        {"scale": "XL_low", "I": 30, "R": 30, "J": 14},
    ]
    assert authorization["minimum_available_memory_gib_before_launch"] == 18
    assert authorization["process_memory_hard_stop_gib"] == 14
    assert authorization["system_available_memory_emergency_stop_gib"] == 3
    assert authorization["memory_poll_interval_seconds_max"] <= 0.5
    assert authorization["preflight_consecutive_samples"] == 3
    assert authorization["execution_status"] == (
        "AUTHORIZED_PENDING_REVISED_MEMORY_PREFLIGHT"
    )


def test_pending_recommendation_does_not_freeze_xl_or_ten_replicates() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    recommendation = summary["recommendation_pending_probe"]
    assert recommendation["scale_grid"] == ["S", "M", "L"]
    assert recommendation["include_XL"] is False
    assert recommendation["replicates"] == 5
    assert recommendation["estimated_formal_run_count"] == 60
    assert recommendation["freeze_status"] == "NOT_FROZEN_RESOURCE_EVIDENCE_MISSING"
