from __future__ import annotations

import json
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.service_calibration import (
    BASELINE_PHI_MULTIPLIER,
    BASELINE_SL,
    FORMAL_CASES,
    PHI_GRID,
    SL_GRID,
    calibrated_instance,
    dry_run_plan,
    enumerate_analysis_conditions,
    enumerate_conditions,
    load_config,
    phi_vector,
    require_formal_authorization,
    validate_config,
)
from robust_inventory_reconfiguration.service_calibration_reporting import (
    RESULT_FIELDS,
    build_case_rows,
    validate_result_schema,
    write_reports,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/formal/service_calibration_robustness_formal.yaml"


def config() -> dict:
    value = load_config(CONFIG)
    validate_config(value)
    return value


def test_exact_40_solve_enumeration_and_run_types() -> None:
    conditions = enumerate_conditions()
    assert FORMAL_CASES == ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")
    assert len(conditions) == len({row.condition_id for row in conditions}) == 40
    assert sum(row.run_type == "baseline" for row in conditions) == 8
    assert sum(row.run_type == "sl_sensitivity" for row in conditions) == 16
    assert sum(row.run_type == "phi_sensitivity" for row in conditions) == 16
    assert all(row.requires_solve for row in conditions)


def test_physical_conditions_are_ofat_with_one_baseline_per_case() -> None:
    conditions = enumerate_conditions()
    assert len({row.condition_id for row in conditions if row.run_type == "baseline"}) == 8
    assert all(
        row.service_level == BASELINE_SL and row.phi_multiplier == BASELINE_PHI_MULTIPLIER
        for row in conditions if row.run_type == "baseline"
    )
    assert all(
        row.phi_multiplier == BASELINE_PHI_MULTIPLIER and row.service_level in {0.85, 0.95}
        for row in conditions if row.run_type == "sl_sensitivity"
    )
    assert all(
        row.service_level == BASELINE_SL and row.phi_multiplier in {1.50, 2.50}
        for row in conditions if row.run_type == "phi_sensitivity"
    )


def test_48_analysis_rows_map_to_40_physical_results() -> None:
    physical = enumerate_conditions()
    analysis = enumerate_analysis_conditions()
    physical_ids = {row.condition_id for row in physical}
    assert len(analysis) == len({row.condition_id for row in analysis}) == 48
    assert {row.physical_result_id for row in analysis} == physical_ids
    assert len({row.physical_result_id for row in analysis}) == 40
    assert sum(row.physical_result_id.startswith("SCAL_BASE_") for row in analysis) == 16


def test_condition_ids_are_deterministic() -> None:
    assert enumerate_conditions() == enumerate_conditions()
    assert enumerate_analysis_conditions() == enumerate_analysis_conditions()
    assert enumerate_conditions()[0].condition_id == "SCAL_BASE_210129"
    assert {row.condition_id for row in enumerate_conditions() if row.case_id == "210129"} == {
        "SCAL_BASE_210129", "SCAL_SL085_210129", "SCAL_SL095_210129",
        "SCAL_PHI150_210129", "SCAL_PHI250_210129",
    }


def test_dry_run_reports_exact_new_design() -> None:
    plan = dry_run_plan(config())
    assert plan["legacy_baseline_reuse"] == "disabled"
    assert plan["current_version_baseline_regeneration"] == "required"
    assert plan["physical_solves"] == 40
    assert plan["baseline_solves"] == 8
    assert plan["sl_sensitivity_solves"] == 16
    assert plan["phi_sensitivity_solves"] == 16
    assert plan["logical_analysis_conditions"] == 48
    assert plan["SL_x_phi_interaction_solves"] == 0
    assert plan["f_multiplier_sensitivity_solves"] == 0
    assert plan["other_Gamma_beta_lambda_grid_solves"] == 0


def test_current_baseline_and_sensitivity_parameters_propagate() -> None:
    original = load_instance(ROOT / "data/formal_instances_v2/210129.json")
    baseline = calibrated_instance(original, service_level=BASELINE_SL, phi_multiplier=BASELINE_PHI_MULTIPLIER)
    higher_sl = calibrated_instance(original, service_level=0.95, phi_multiplier=BASELINE_PHI_MULTIPLIER)
    lower_phi = calibrated_instance(original, service_level=BASELINE_SL, phi_multiplier=1.50)
    assert baseline.service_level == original.service_level
    assert baseline.service_penalty == original.service_penalty
    assert higher_sl.service_level == [0.95] * original.num_products
    assert higher_sl.service_penalty == original.service_penalty
    assert lower_phi.service_level == original.service_level
    assert lower_phi.service_penalty == phi_vector(original, 1.50)
    assert len({tuple(phi_vector(original, multiplier)) for multiplier in PHI_GRID}) == 3
    assert lower_phi.shortage_penalty == original.shortage_penalty


def test_soft_service_form_is_unchanged() -> None:
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "src/robust_inventory_reconfiguration/product_risk_subproblem.py",
            "src/robust_inventory_reconfiguration/reconfiguration_model.py",
            "src/robust_inventory_reconfiguration/robust_service.py",
        )
    )
    assert "instance.service_level" in sources
    assert "instance.service_penalty" in sources
    assert "- e" in sources


def test_no_legacy_baseline_execution_dependency() -> None:
    value = config()
    assert value["baseline_policy"] == {
        "legacy_E4_reuse": False,
        "current_version_regeneration_required": True,
    }
    runner = (ROOT / "experiments/run_service_calibration_robustness.py").read_text(encoding="utf-8")
    reporter = (ROOT / "scripts/report_service_calibration_robustness.py").read_text(encoding="utf-8")
    assert "BASELINE_REUSE_NOT_AUTHORIZED" not in runner
    assert "normalized_baseline" not in reporter
    assert "load_current_results" in reporter


def test_unauthorized_execution_is_blocked() -> None:
    with pytest.raises(PermissionError, match="SERVICE_CALIBRATION_FORMAL_RUN_NOT_AUTHORIZED"):
        require_formal_authorization(config())


def test_authorized_config_still_enumerates_exactly_40_solves() -> None:
    value = config()
    value["formal_run_authorized"] = True
    value["authorization_transition"] = [False, True]
    validate_config(value)
    require_formal_authorization(value)
    assert dry_run_plan(value)["physical_solves"] == 40


def _physical_results() -> list[dict]:
    rows = []
    for condition in enumerate_conditions():
        row = {field: None for field in RESULT_FIELDS}
        row.update({
            "experiment_id": "TEST", "case_id": condition.case_id,
            "condition_id": condition.condition_id, "run_type": condition.run_type,
            "SL": condition.service_level, "phi_multiplier": condition.phi_multiplier,
            "objective": 100.0, "RI": 0.0, "RS": 0.0,
            "material_reconfiguration": False, "total_shortage": 1.0,
            "service_penalty_cost": 2.0, "aggregate_fill_rate": 0.9,
            "budget_utilization": 1.0, "active_depot_set": json.dumps(["D1"]),
            "activated_depots_vs_baseline": json.dumps([]),
            "deactivated_depots_vs_baseline": json.dumps([]),
            "reused": False, "reuse_source_run": None,
        })
        rows.append(row)
    return rows


def _execution_manifest() -> list[dict]:
    return [
        {"condition_id": row.condition_id, "case_id": row.case_id, "run_type": row.run_type}
        for row in enumerate_conditions()
    ]


def test_reporting_uses_current_baseline_and_writes_execution_manifest(tmp_path: Path) -> None:
    rows = _physical_results()
    validate_result_schema(rows[0])
    case_rows = build_case_rows(rows)
    assert len(case_rows) == 48
    assert all(
        row["normalized_objective_relative_to_baseline"] == 1.0
        for row in case_rows if row["physical_result_id"].startswith("SCAL_BASE_")
    )
    write_reports(
        rows, _execution_manifest(), tmp_path,
        historical_diagnostic={"status": "UNAVAILABLE", "blocking": False},
    )
    expected = set(config()["required_outputs"])
    assert expected == {path.name for path in tmp_path.iterdir()}
    assert len((tmp_path / "service_calibration_case_level.csv").read_text(encoding="utf-8").splitlines()) == 49
    assert len((tmp_path / "service_calibration_all_results.csv").read_text(encoding="utf-8").splitlines()) == 41
    assert len((tmp_path / "service_calibration_execution_manifest.csv").read_text(encoding="utf-8").splitlines()) == 41


def test_historical_comparison_status_cannot_change_formal_reporting(tmp_path: Path) -> None:
    rows = _physical_results()
    write_reports(
        rows, _execution_manifest(), tmp_path,
        historical_diagnostic={"status": "MISMATCH", "blocking": False},
    )
    summary = (tmp_path / "service_calibration_robustness_summary.md").read_text(encoding="utf-8")
    assert "MISMATCH (non-blocking; not used for formal identity)" in summary
    assert len((tmp_path / "service_calibration_all_results.csv").read_text(encoding="utf-8").splitlines()) == 41
