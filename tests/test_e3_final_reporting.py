from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.plot_e3_budget_results import generate_figures, load_rows


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def csv_rows(name: str) -> list[dict[str, str]]:
    with (ARTIFACTS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_final_result_audit_certifies_frozen_40_run_set() -> None:
    audit = json.loads((ARTIFACTS / "e3_final_result_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "E3_FINAL_RESULT_AUDIT_PASS"
    assert audit["expected_run_count"] == audit["observed_run_count"] == 40
    assert audit["B100_reuse_count"] == 8
    assert audit["all_certified"] is True
    assert audit["all_feasible"] is True
    assert audit["all_primary_files_match_frozen_zip"] is True
    assert len(csv_rows("e3_primary_result_hashes.csv")) == 40


def test_paper_tables_have_expected_rows_and_fields() -> None:
    case_rows = csv_rows("e3_table_budget_sensitivity_case_level.csv")
    aggregate_rows = csv_rows("e3_table_budget_sensitivity_aggregate.csv")
    threshold_rows = csv_rows("e3_table_budget_thresholds.csv")
    assert len(case_rows) == 40
    assert len({(row["case"], row["beta"]) for row in case_rows}) == 40
    assert len(aggregate_rows) == 5
    assert len(threshold_rows) == 8
    for field in (
        "objective", "first_stage_economic_cost", "fixed_cost", "inventory_cost",
        "reconfiguration_cost", "robust_recourse_cost", "RI", "RS",
        "budget_utilization", "normalized_objective", "normalized_robust_recourse",
    ):
        assert field in case_rows[0]
    for field in ("B110_budget_slack", "B120_budget_slack", "first_empirical_plateau_beta"):
        assert field in threshold_rows[0]


def test_reported_e3_mechanism_and_plateau_values() -> None:
    aggregate = {float(row["beta"]): row for row in csv_rows("e3_table_budget_sensitivity_aggregate.csv")}
    assert float(aggregate[0.8]["mean_RI"]) == pytest.approx(0.3680661869014031)
    assert float(aggregate[1.0]["mean_RI"]) == pytest.approx(0.04098909454043905)
    assert float(aggregate[1.2]["mean_RI"]) == pytest.approx(0.01038390399204624)
    assert [int(aggregate[beta]["material_reconfiguration_case_count"]) for beta in sorted(aggregate)] == [8, 8, 4, 4, 4]
    thresholds = csv_rows("e3_table_budget_thresholds.csv")
    assert all(abs(float(row["B110_vs_B120_objective_change"])) <= 1e-6 for row in thresholds)


def test_210330_tie_is_reporting_only() -> None:
    audit = json.loads((ARTIFACTS / "e3_210330_b110_b120_tie_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["classification"] == "REPORTING_SCENARIO_SELECTION_TIE"
    assert audit["objective_validity_affected"] is False
    assert audit["feasibility_affected"] is False
    assert audit["budget_conclusion_affected"] is False
    assert audit["new_first_stage_optimization_solves"] == 0
    assert audit["first_stage"]["y_identical"] is True
    assert audit["first_stage"]["x"]["coordinates_differing_above_1e-6"] == 0
    assert audit["fixed_first_stage_recomputation"]["B110"]["tied_worst_recourse_scenario_count"] == 2


@pytest.mark.parametrize(
    "command",
    (
        [sys.executable, "scripts/summarize_e3_budget_results.py", "--help"],
        [sys.executable, "-m", "scripts.summarize_e3_budget_results", "--help"],
    ),
)
def test_summary_entrypoints(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


def test_figure_generation_outputs_png_and_pdf(tmp_path: Path) -> None:
    generate_figures(load_rows(ARTIFACTS / "e3_table_budget_sensitivity_case_level.csv"), tmp_path)
    for stem in (
        "fig_e3_normalized_objective_vs_budget",
        "fig_e3_ri_vs_budget",
        "fig_e3_budget_utilization_vs_budget",
        "fig_e3_recourse_vs_budget",
    ):
        assert (tmp_path / f"{stem}.png").stat().st_size > 0
        assert (tmp_path / f"{stem}.pdf").stat().st_size > 0
