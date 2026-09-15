import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_mechanism_audit_records_exact_available_comparisons() -> None:
    audit = json.loads(
        (ROOT / "artifacts/e1c_pure_benders_mechanism_audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert audit["status"] == "PURE_BENDERS_MECHANISM_AUDIT_PASS"
    assert audit["empirical_objective_consistency"]["passed"] == 8
    assert audit["development_objective_consistency"]["status"] == (
        "E1C_OBJECTIVE_CONSISTENCY_PASS"
    )
    for scale in audit["development_objective_consistency"]["scales"]:
        assert scale["max_abs_difference"] <= audit["objective_tolerance"]


def test_mechanism_audit_preserves_evidence_limits() -> None:
    audit = json.loads(
        (ROOT / "artifacts/e1c_pure_benders_mechanism_audit.json").read_text(
            encoding="utf-8"
        )
    )

    structure = audit["structure_audit"]
    assert structure["PURE_BENDERS_STRUCTURE_LEAKAGE"] is False
    assert structure["product_risk_decomposition_used"] is False
    assert structure["gamma_allocation_dp_used"] is False
    assert audit["mechanism_ratings"]["presolve_fixes_most_z"] == "UNKNOWN"
    assert audit["mechanism_ratings"]["gamma_allocation_dp_overhead"] == "UNKNOWN"
    assert audit["optimization_runs_during_audit"] == {"formal": 0, "development": 0}
