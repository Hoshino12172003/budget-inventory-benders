from __future__ import annotations

import csv
import json
from pathlib import Path


ARTIFACTS = Path("artifacts")


def _rows(name: str) -> list[dict[str, str]]:
    with (ARTIFACTS / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_x0_artifacts_are_complete_and_source_traceable() -> None:
    for case in ("210202", "210628"):
        rows = _rows(f"renault_x0_{case}.csv")
        assert len(rows) == 120
        assert len({(row["depot_id"], row["product_id"]) for row in rows}) == 120
        assert all(row["mapping_method"] == "exact_identity_match" for row in rows)
        assert all(row["x0"] == row["source_initial_inventory"] for row in rows)
        assert all(row["source_file"] and row["source_sha256"] for row in rows)


def test_compatibility_artifact_dimensions() -> None:
    assert len(_rows("renault_x0_capacity_audit.csv")) == 30
    assert len(_rows("renault_x0_ub_audit.csv")) == 240
    assert len(_rows("renault_x0_scale_audit.csv")) == 18


def test_summary_freezes_static_audit_guardrails() -> None:
    summary = json.loads(
        (ARTIFACTS / "renault_x0_compatibility_summary.json").read_text(encoding="utf-8")
    )
    assert summary["optimization_run"] is False
    assert summary["step_1_3_parameters_modified"] is False
    assert summary["PRODUCTWISE_BENDERS_COMPATIBLE"] is True
    assert summary["observed_initial_inventory_recommended_directly_as_x0"] is False
    assert summary["safe_to_proceed_to_lambda_R_calibration_and_new_B_ref"] is False
    for case in ("210202", "210628"):
        assert summary["cases"][case]["mapped_count"] == 120
        assert summary["cases"][case]["classification"] == "DIRECTLY_COMPATIBLE"
