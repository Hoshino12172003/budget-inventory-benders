from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import experiments.run_e6_budget_risk_local as runner
from scripts import audit_and_summarize_e6_results as summary


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def rows(name: str) -> list[dict[str, str]]:
    with (ARTIFACTS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_final_audit_is_complete_and_exactly_certified() -> None:
    audit = json.loads((ARTIFACTS / "e6_final_result_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "E6_FINAL_AUDIT_PASS_WITH_RUNTIME_ACCOUNTING_LIMITATION"
    assert audit["E6_RESULTS_COMPLETE"] is True
    assert (audit["total_conditions"], audit["optimal_status_count"], audit["exact_certification_pass_count"]) == (72, 72, 72)
    assert (audit["reuse_count"], audit["new_solve_count"]) == (40, 32)
    assert audit["failures"] == {}
    if audit["review_package_comparison"]["available"]:
        assert audit["review_package_comparison"]["classification"] == "216_OF_216_BYTE_IDENTICAL"


def test_aggregate_interaction_and_material_counts() -> None:
    indexed = {
        (row["beta_token"], int(row["Gamma"])): row
        for row in rows("e6_table_budget_risk_interaction_aggregate.csv")
    }
    assert len(indexed) == 9
    assert float(indexed[("B080", 0)]["mean_RI"]) == pytest.approx(0.3680661869014027)
    assert float(indexed[("B080", 4)]["mean_RI"]) == pytest.approx(0.3680661869014126)
    assert float(indexed[("B100", 4)]["mean_RI"]) == pytest.approx(0.12453631727980913)
    assert float(indexed[("B120", 4)]["mean_RI"]) == pytest.approx(0.03155211345961889)
    assert [int(indexed[("B100", gamma)]["material_case_count"]) for gamma in (0, 2, 4)] == [0, 4, 5]
    assert [int(indexed[("B120", gamma)]["budget_binding_case_count"]) for gamma in (0, 2, 4)] == [0, 0, 0]


def test_composition_and_observed_threshold_classification() -> None:
    indexed = {row["case"]: row for row in rows("e6_table_interaction_contrasts.csv")}
    changed = [case for case, row in indexed.items() if row["composition_change_G0_to_G4_B080"] == "True"]
    assert changed == ["210310"]
    assert int(indexed["210310"]["x_coordinate_changes_G0_to_G4_B080"]) == 2
    assert indexed["210310"]["first_material_gamma_B100"] == "4"
    assert indexed["210628"]["first_material_gamma_B100"] == "none_through_4"


def test_depot_response_uses_y_and_preserves_positive_inventory_distinction() -> None:
    depot = rows("e6_table_depot_response.csv")
    assert len(depot) == 72
    b080 = [row for row in depot if row["beta_token"] == "B080"]
    assert sum(row["y_network_change"] == "True" for row in b080 if row["Gamma"] == "0") == 6
    assert not any(row["y_network_change"] == "True" for row in depot if row["beta_token"] != "B080")
    assert all(row["final_y_active_depot_count"] == row["final_positive_inventory_depot_count"] for row in depot)


def test_runtime_scope_is_explicit_and_wallclock_is_not_fabricated() -> None:
    runtime = rows("e6_runtime_accounting_audit.csv")
    new_g4 = [row for row in runtime if row["reuse_or_new"] == "NEW_SOLVE" and row["Gamma"] == "4"]
    assert len(new_g4) == 16
    assert all(row["global_scenarios_in_post_evaluation"] == "3469497" for row in new_g4)
    assert all(row["product_risk_blocks_in_post_evaluation"] == "6352" for row in new_g4)
    assert all(row["reconstructed_wallclock_seconds"] == "" for row in new_g4)
    assert all(row["wallclock_reconstruction_status"] == "UNAVAILABLE_NO_RUNNER_START_TIMESTAMP" for row in new_g4)
    assert all(row["timing_anomaly_flag"] == "True" for row in new_g4)


def test_summary_generation_never_calls_optimizer_or_overwrites_primary(monkeypatch) -> None:
    before = summary.tree_identity(runner.RESULT_ROOT)
    monkeypatch.setattr(
        runner,
        "solve_prb_benders",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("optimizer invoked")),
    )
    summary.main()
    assert summary.tree_identity(runner.RESULT_ROOT) == before


def test_all_requested_figures_exist_in_png_and_pdf() -> None:
    stems = (
        "fig_e6_ri_interaction",
        "fig_e6_normalized_objective_interaction",
        "fig_e6_budget_utilization_heatmap",
        "fig_e6_material_cases_heatmap",
        "fig_e6_active_depot_change_heatmap",
        "fig_e6_case_level_ri_trajectories",
    )
    assert all((ARTIFACTS / f"{stem}.{suffix}").stat().st_size > 0 for stem in stems for suffix in ("png", "pdf"))
