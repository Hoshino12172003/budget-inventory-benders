import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts" / "historical_benders_lineage_audit.json"


def _audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def test_lineage_finds_and_distinguishes_cut_artifacts() -> None:
    audit = _audit()
    assert audit["four_thousand_cut_artifact_found"] is True
    assert audit["two_thousand_one_hundred_fifty_four_cut_artifact_found"] is True
    names = [family["name"] for family in audit["historical_families"]]
    assert any("2154-cut" in name for name in names)
    assert any("fairness" in name.lower() for name in names)


def test_historical_variants_are_not_relabelled_vanilla() -> None:
    audit = _audit()
    assert {
        family["classification"] for family in audit["historical_families"]
    } == {"LEGACY_STRENGTHENED_BENDERS"}


def test_static_comparability_failure_blocks_reproduction() -> None:
    audit = _audit()
    assert audit["status"] == "HISTORICAL_BENDERS_NOT_COMPARABLE"
    assert audit["static_comparability_gate_pass"] is False
    assert audit["reproduction"]["status"] == "NOT_RUN_STATIC_COMPARABILITY_BLOCK"
    assert audit["reproduction"]["optimization_runs"] == 0
    assert audit["reproduction"]["speed_ratio"] is None


def test_noncomparable_source_is_not_migrated() -> None:
    audit = _audit()
    assert audit["compatibility_repairs"] == []
    assert audit["restored_source_files"] == []
    assert not (ROOT / "src" / "historical_benders_baseline.py").exists()
    assert not (
        ROOT / "experiments" / "run_e1_historical_benders_development.py"
    ).exists()
