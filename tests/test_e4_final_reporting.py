from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.plot_e4_gamma_results import generate_figures, load_rows


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def csv_rows(name: str) -> list[dict[str, str]]:
    with (ARTIFACTS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_final_audit_certifies_frozen_40_run_set() -> None:
    audit = json.loads((ARTIFACTS / "e4_final_result_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "E4_FINAL_AUDIT_PASS"
    assert audit["expected_run_count"] == audit["observed_run_count"] == 40
    assert all(audit["checks"].values())
    assert audit["frozen_zip_comparison"] == {
        "available": True, "file_count": 120, "all_match": True
    }
    assert audit["new_first_stage_optimization_solves"] == 0
    assert audit["primary_results_overwritten"] is False


def test_publication_tables_have_expected_shape_and_metrics() -> None:
    case_rows = csv_rows("e4_table_gamma_sensitivity_case_level.csv")
    aggregate_rows = csv_rows("e4_table_gamma_sensitivity_aggregate.csv")
    threshold_rows = csv_rows("e4_table_reconfiguration_thresholds.csv")
    assert len(case_rows) == 40
    assert len({(row["case"], row["Gamma"]) for row in case_rows}) == 40
    assert len(aggregate_rows) == 5
    assert len(threshold_rows) == 8
    for field in (
        "normalized_objective", "normalized_robust_recourse", "RI", "RS",
        "budget_utilization", "total_adjustment", "active_depots",
        "shortage_cost", "service_penalty", "average_fill_rate",
        "runtime_seconds", "iterations", "cuts_added",
    ):
        assert field in case_rows[0]


def test_material_thresholds_are_recomputed_from_case_rows() -> None:
    rows = csv_rows("e4_table_gamma_sensitivity_case_level.csv")
    thresholds = {row["case"]: row for row in csv_rows("e4_table_reconfiguration_thresholds.csv")}
    for case, threshold in thresholds.items():
        material = sorted(
            int(row["Gamma"]) for row in rows
            if row["case"] == case and float(row["RI"]) > 1e-6
        )
        expected = f"G{material[0]}" if material else "NONE_THROUGH_G4"
        assert threshold["first_material_reconfiguration_status"] == expected


def test_inventory_response_is_nondecreasing_without_depot_set_changes() -> None:
    thresholds = csv_rows("e4_table_reconfiguration_thresholds.csv")
    assert all(row["RI_weakly_nondecreasing"] == "True" for row in thresholds)
    assert all(row["active_depot_set_changed_from_G0"] == "False" for row in thresholds)


def test_210330_g3_global_coupling_is_numerical_only() -> None:
    audit = json.loads((ARTIFACTS / "e4_210330_g3_global_coupling_audit.json").read_text(encoding="utf-8"))
    assert audit["classification"] == "NUMERICAL_DIAGNOSTIC_TOLERANCE_ISSUE"
    assert audit["reported_pass"] is False
    assert audit["fresh_vs_stored_recourse_difference"] == 0.0
    assert audit["Gamma_feasible"] is True
    assert audit["objective_reconstruction_difference"] == 0.0
    assert audit["first_stage_reoptimized"] is False


def test_reused_g2_missing_field_is_classified_by_source_provenance() -> None:
    audit = json.loads((ARTIFACTS / "e4_final_result_audit.json").read_text(encoding="utf-8"))
    assert audit["G2_reuse"]["identity_safe_count"] == 8
    for row in audit["G2_reuse"]["rows"]:
        assert row["e4_field_present"] is False
        assert row["diagnostic_schema_classification"] == "MISSING_BY_REUSE_SCHEMA_SOURCE_DIAGNOSTIC_REFERENCED"
        assert row["primary_certification_affected"] is False


def test_figure_generation_outputs_png_and_pdf(tmp_path: Path) -> None:
    generate_figures(load_rows(), tmp_path)
    for stem in (
        "fig_e4_normalized_objective_vs_gamma",
        "fig_e4_ri_vs_gamma",
        "fig_e4_material_reconfiguration_cases_vs_gamma",
        "fig_e4_normalized_recourse_vs_gamma",
    ):
        assert (tmp_path / f"{stem}.png").stat().st_size > 0
        assert (tmp_path / f"{stem}.pdf").stat().st_size > 0
