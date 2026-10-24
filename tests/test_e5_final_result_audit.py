from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def read_csv(name: str) -> list[dict[str, str]]:
    with (ARTIFACTS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_e5_final_audit_passes_all_correctness_gates() -> None:
    audit = json.loads((ARTIFACTS / "e5_final_result_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "E5_FINAL_AUDIT_PASS"
    assert audit["expected_run_count"] == audit["observed_run_count"] == 40
    assert all(audit["checks"].values())
    assert audit["archive_comparison"] == {"available": True, "file_count": 120, "all_match": True}
    assert audit["new_first_stage_optimization_solves"] == 0


def test_case_table_has_complete_unique_grid_and_recomputed_metrics() -> None:
    rows = read_csv("e5_table_friction_sensitivity_case_level.csv")
    identities = {(row["case"], row["lambda_token"]) for row in rows}
    assert len(rows) == len(identities) == 40
    assert {float(row["lambda_R"]) for row in rows} == {0.0, 0.0025, 0.01, 0.05, 0.2}
    assert all(abs(float(row["RI"]) - float(row["canonical_RI"])) <= 1e-12 for row in rows)
    assert all(
        abs(float(row["objective"]) - float(row["budget_used"]) - float(row["robust_recourse_cost"])) <= 1e-4
        for row in rows
    )


def test_aggregate_table_preserves_material_incidence_and_budget_binding() -> None:
    rows = read_csv("e5_table_friction_sensitivity_aggregate.csv")
    assert len(rows) == 5
    assert [int(row["material_reconfiguration_case_count"]) for row in rows] == [4, 4, 4, 4, 4]
    assert [int(row["stay_put_case_count"]) for row in rows] == [4, 4, 4, 4, 4]
    assert all(abs(float(row["mean_budget_utilization"]) - 1.0) <= 1e-9 for row in rows)


def test_nonmonotone_response_is_not_known_optimal_face_variation() -> None:
    audit = json.loads((ARTIFACTS / "e5_final_result_audit.json").read_text(encoding="utf-8"))
    assert audit["reverse_RI_adjacent_pair_count"] == 13
    assert audit["known_optimal_face_reverse_pair_count"] == 0
    assert audit["lambda_zero_audit"]["observed_material_optimal_face_RI_variation"] is False
    assert audit["main_mechanism_classification"] == "FRICTION_INTENSITY_COMPOSITION_EFFECT"


def test_depot_network_and_l0500_reuse_are_stable() -> None:
    audit = json.loads((ARTIFACTS / "e5_final_result_audit.json").read_text(encoding="utf-8"))
    assert audit["active_depot_set_change_conditions"] == 0
    assert audit["L0500_reuse"]["identity_safe_count"] == 8


def test_required_figures_exist_in_both_formats() -> None:
    stems = (
        "fig_e5_normalized_objective_vs_lambda",
        "fig_e5_ri_vs_lambda",
        "fig_e5_rs_vs_lambda",
        "fig_e5_recourse_vs_lambda",
    )
    assert all((ARTIFACTS / f"{stem}.{suffix}").stat().st_size > 0 for stem in stems for suffix in ("png", "pdf"))
