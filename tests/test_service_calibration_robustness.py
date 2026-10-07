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
    enumerate_conditions,
    load_config,
    new_solve_conditions,
    phi_vector,
    require_formal_authorization,
    validate_config,
)
from robust_inventory_reconfiguration.service_calibration_audit import baseline_reuse_audit
from robust_inventory_reconfiguration.service_calibration_reporting import (
    RESULT_FIELDS,
    validate_result_schema,
    write_reports,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/formal/service_calibration_robustness_formal.yaml"


def config() -> dict:
    value = load_config(CONFIG)
    validate_config(value)
    return value


def test_exact_cases_and_ofat_enumeration_have_no_interactions() -> None:
    conditions = enumerate_conditions()
    assert FORMAL_CASES == ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")
    assert SL_GRID == (0.85, 0.90, 0.95)
    assert PHI_GRID == (1.50, 1.85, 2.50)
    assert len(conditions) == 48
    assert len(new_solve_conditions()) == 32
    assert sum(row.baseline for row in conditions) == 16
    assert len({row.physical_result_id for row in conditions}) == 40
    assert all(
        row.phi_multiplier == BASELINE_PHI_MULTIPLIER
        if row.run_type == "sl_sensitivity"
        else row.service_level == BASELINE_SL
        for row in conditions
    )


def test_condition_ids_are_deterministic_and_duplicate_safe() -> None:
    first = enumerate_conditions()
    second = enumerate_conditions()
    assert first == second
    assert len({row.condition_id for row in first}) == 48
    baseline_ids = [row.physical_result_id for row in first if row.baseline]
    assert len(baseline_ids) == 16
    assert len(set(baseline_ids)) == 8


def test_dry_run_counts_are_exact() -> None:
    plan = dry_run_plan(config())
    assert plan["sl_sensitivity"] == {
        "table_conditions": 24,
        "potentially_reusable_baseline_conditions": 8,
        "new_solves": 16,
    }
    assert plan["phi_sensitivity"] == {
        "table_conditions": 24,
        "potentially_reusable_baseline_conditions": 8,
        "new_solves": 16,
    }
    assert plan["reported_OFAT_conditions"] == 48
    assert plan["unique_physical_results"] == 40
    assert plan["new_formal_optimization_solves_if_baseline_reuse_authorized"] == 32


def test_sl_and_phi_parameters_propagate_to_instance_and_preserve_baseline() -> None:
    original = load_instance(ROOT / "data/formal_instances_v2/210129.json")
    baseline = calibrated_instance(
        original, service_level=BASELINE_SL, phi_multiplier=BASELINE_PHI_MULTIPLIER
    )
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


def test_soft_service_parameters_are_consumed_by_frozen_model_sources() -> None:
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


def test_baseline_reuse_requires_complete_identity_chain() -> None:
    rows = baseline_reuse_audit(ROOT, config())
    assert len(rows) == 8
    assert all(row["classification"] in {"IDENTITY_SAFE_BASELINE_REUSE", "BASELINE_REUSE_NOT_AUTHORIZED"} for row in rows)
    assert all(row["reuse_authorized"] == (row["failed_checks"] == "") for row in rows)


def test_unauthorized_formal_run_is_blocked() -> None:
    with pytest.raises(PermissionError, match="SERVICE_CALIBRATION_FORMAL_RUN_NOT_AUTHORIZED"):
        require_formal_authorization(config())


def test_authorized_config_still_enumerates_only_32_new_solves() -> None:
    value = config()
    value["formal_run_authorized"] = True
    value["authorization_transition"] = [False, True]
    validate_config(value)
    require_formal_authorization(value)
    assert dry_run_plan(value)["new_formal_optimization_solves_if_baseline_reuse_authorized"] == 32


def _physical_results() -> list[dict]:
    rows = []
    seen = set()
    for condition in enumerate_conditions():
        if condition.physical_result_id in seen:
            continue
        seen.add(condition.physical_result_id)
        row = {field: None for field in RESULT_FIELDS}
        row.update({
            "experiment_id": "TEST", "case_id": condition.case_id,
            "condition_id": condition.physical_result_id, "run_type": condition.run_type,
            "SL": condition.service_level, "phi_multiplier": condition.phi_multiplier,
            "objective": 100.0, "RI": 0.0, "RS": 0.0,
            "material_reconfiguration": False, "total_shortage": 1.0,
            "service_penalty_cost": 2.0, "aggregate_fill_rate": 0.9,
            "budget_utilization": 1.0, "active_depot_set": json.dumps(["D1"]),
            "activated_depots_vs_baseline": json.dumps([]),
            "deactivated_depots_vs_baseline": json.dumps([]),
        })
        rows.append(row)
    return rows


def test_output_schema_and_reporting_preserve_case_and_aggregate_views(tmp_path: Path) -> None:
    rows = _physical_results()
    validate_result_schema(rows[0])
    audit = [{"case_id": case, "reuse_authorized": True} for case in FORMAL_CASES]
    write_reports(rows, audit, tmp_path)
    expected = set(config()["required_outputs"])
    assert expected == {path.name for path in tmp_path.iterdir()}
    case_rows = (tmp_path / "service_calibration_case_level.csv").read_text(encoding="utf-8").splitlines()
    all_rows = (tmp_path / "service_calibration_all_results.csv").read_text(encoding="utf-8").splitlines()
    assert len(case_rows) == 49
    assert len(all_rows) == 41
