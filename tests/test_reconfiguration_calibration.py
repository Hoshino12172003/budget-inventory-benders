from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.reconfiguration_model import (
    first_stage_expenditure_value,
    gamma_allocations,
    reconfiguration_cost_value,
    reconfiguration_index,
)


ROOT = Path(__file__).resolve().parents[1]


def test_reconfiguration_balance_and_ri_representations() -> None:
    x0 = [[4.0, 2.0]]
    x = [[5.0, 0.5]]
    a_plus = [[1.0, 0.0]]
    a_minus = [[0.0, 1.5]]
    assert x[0][0] - x0[0][0] == a_plus[0][0] - a_minus[0][0]
    assert x[0][1] - x0[0][1] == a_plus[0][1] - a_minus[0][1]
    direct, represented = reconfiguration_index(x, x0, a_plus, a_minus)
    assert direct == represented


def test_budget_accounting_includes_all_first_stage_terms(tiny_instance) -> None:
    y = [1]
    x = [[2.0, 1.0]]
    a_plus = [[1.0, 0.0]]
    a_minus = [[0.0, 2.0]]
    reconfiguration = reconfiguration_cost_value(tiny_instance, a_plus, a_minus, 0.5)
    assert reconfiguration == pytest.approx(1.5)
    assert first_stage_expenditure_value(
        tiny_instance, y, x, a_plus, a_minus, 0.5
    ) == pytest.approx(9.5)


def test_exact_risk_budget_allocations_remain_product_separable() -> None:
    assert gamma_allocations(2, 1) == [(0, 0), (0, 1), (1, 0)]


def test_development_correctness_audit_passes() -> None:
    audit = json.loads(
        (ROOT / "artifacts" / "reconfiguration_correctness_audit.json").read_text()
    )
    assert audit["zero_friction_equivalence"] is True
    assert audit["incumbent_nominal_recovery"] is True
    assert audit["reconfiguration_balance_identity"] is True
    assert audit["no_material_simultaneous_adjustments_when_positive_cost"] is True
    assert audit["ri_representations_equivalent"] is True
    assert audit["objective_accounting_consistent"] is True


def test_development_grid_is_complete() -> None:
    with (ROOT / "artifacts" / "lambda_calibration_runs.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 132
    assert {row["case"] for row in rows} == {"210202", "210628"}
    assert {int(row["gamma"]) for row in rows} == {1, 2}
    assert {float(row["beta"]) for row in rows} == {0.9, 1.0, 1.1}
