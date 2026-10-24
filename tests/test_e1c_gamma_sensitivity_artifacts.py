import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_blocked_artifact_preserves_preregistered_contract() -> None:
    audit = json.loads(
        (ROOT / "artifacts/e1c_gamma_sensitivity_development.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["status"] == "EVIDENCE_INSUFFICIENT"
    assert audit["static_audit"] == "PASS"
    assert audit["dry_run"] == {
        "status": "PASS",
        "condition_count": 12,
        "optimization_calls": 0,
    }
    assert audit["execution"]["status"] == "E1C_GAMMA_RESOURCE_PREFLIGHT_BLOCKED"
    assert audit["execution"]["solver_called"] is False
    assert audit["frozen_protocol"]["gamma_grid"] == [2, 4, 6, 8]
    assert audit["development_optimization_runs"] == 0
    assert audit["formal_optimization_runs"] == 0


def test_static_block_counts_are_exact() -> None:
    audit = json.loads(
        (ROOT / "artifacts/e1c_gamma_sensitivity_development.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["static_sizes"]["product_risk_blocks"] == {
        "2": 3612,
        "4": 155412,
        "6": 2280612,
        "8": 15259512,
    }
