from __future__ import annotations

import csv
import json
from pathlib import Path

from robust_inventory_reconfiguration.reconfiguration_model import (
    product_risk_budget_value,
)
from robust_inventory_reconfiguration.robust_service import (
    select_worst_reporting_identity,
)
from robust_inventory_reconfiguration.scenarios import (
    enumerate_scenario_components,
    scenario_count,
)


ROOT = Path(__file__).resolve().parents[1]


def load_summary() -> dict:
    return json.loads(
        (ROOT / "artifacts" / "reconfiguration_correctness_summary.json").read_text()
    )


def test_uncertainty_set_scenario_count_and_canonical_order(tiny_instance) -> None:
    assert scenario_count(tiny_instance, 2) == 11
    scenarios = enumerate_scenario_components(tiny_instance, 1)
    assert scenarios[:3] == [(), ((0, 0),), ((0, 1),)]


def test_product_risk_budget_value_matches_direct_tiny_enumeration() -> None:
    product_values = [[10.0, 14.0, 16.0], [20.0, 23.0, 25.0]]
    direct_global_values = [30.0, 34.0, 33.0, 36.0, 37.0, 35.0]
    assert product_risk_budget_value(product_values, 2) == max(direct_global_values)


def test_robust_service_reporting_tie_break_is_deterministic() -> None:
    scenario, region, value = select_worst_reporting_identity(
        [[0.8, 0.7], [0.7, 0.9]]
    )
    assert (scenario, region, value) == (0, 1, 0.7)


def test_accounting_and_reconfiguration_audits_pass() -> None:
    summary = load_summary()
    assert summary["budget_accounting_pass"] is True
    assert summary["objective_accounting_pass"] is True
    assert summary["reconfiguration_identity_pass"] is True


def test_zero_friction_and_nominal_recovery_pass() -> None:
    summary = load_summary()
    assert summary["zero_friction_equivalence_full_grid"] is True
    assert summary["nominal_baseline_recovery_pass"] is True


def test_gamma_and_budget_nesting_pass() -> None:
    summary = load_summary()
    assert summary["robust_objective_nesting_pass"] is True
    assert summary["budget_feasibility_nesting_pass"] is True


def test_all_correctness_runs_are_certified_optimal() -> None:
    summary = load_summary()
    assert summary["attempted"] == 72
    assert summary["status_counts"] == {
        "OPTIMAL": 72,
        "INFEASIBLE": 0,
        "TIME_LIMIT": 0,
        "MEMORY_LIMIT": 0,
        "ERROR": 0,
    }


def test_direct_scenarios_match_exact_extensive_form() -> None:
    with (ROOT / "artifacts" / "reconfiguration_correctness_runs.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert max(float(row["direct_robust_recourse_difference"]) for row in rows) <= 1e-6
    assert load_summary()["productwise_reformulation_exact"] is True


def test_service_evaluation_covers_every_certified_solution() -> None:
    with (ROOT / "artifacts" / "robust_service_evaluation.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 72
    assert {int(row["scenario_count"]) for row in rows if row["gamma"] == "2"} == {4657}
    assert all(row["worst_region"] for row in rows)


def test_future_algorithm_contract_is_frozen() -> None:
    contract = json.loads(
        (ROOT / "artifacts" / "exact_benchmark_contract.json").read_text()
    )
    assert contract["required_comparisons"]["feasibility_max_violation"] == 1e-6
    assert contract["required_comparisons"]["activation_vector"] == "exact identity"
    assert contract["productwise_benders_implementation_included"] is False
