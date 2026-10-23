from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from robust_inventory_reconfiguration.scenario_generation_single_cut import (
    ScenarioEvaluation,
    build_affine_scenario_upper_bound,
    enumerate_patterns,
    exact_separation,
    feasible_greedy_upper_bound,
    no_shipment_upper_bound,
)


ROOT = Path(__file__).resolve().parents[1]


def tiny_instance() -> SimpleNamespace:
    return SimpleNamespace(
        num_depots=1,
        num_regions=2,
        num_products=1,
        base_demand=[[2.0], [1.0]],
        demand_deviation=[[2.0], [3.0]],
        transport_cost=[[[1.0], [4.0]]],
        shortage_penalty=[[5.0], [6.0]],
        service_level=[0.5],
        service_penalty=[10.0],
    )


def exact_integer_recourse(instance: SimpleNamespace, x: list[list[float]], pattern: tuple) -> float:
    active = set(pattern)
    demand = [
        int(instance.base_demand[r][0] + (instance.demand_deviation[r][0] if (r, 0) in active else 0))
        for r in range(instance.num_regions)
    ]
    supply = int(x[0][0])
    best = float("inf")
    for q0 in range(min(demand[0], supply) + 1):
        for q1 in range(min(demand[1], supply - q0) + 1):
            shortage = [demand[0] - q0, demand[1] - q1]
            allowance = (1.0 - instance.service_level[0]) * sum(demand)
            violation = max(0.0, sum(shortage) - allowance)
            value = q0 + 4.0 * q1 + 5.0 * shortage[0] + 6.0 * shortage[1] + 10.0 * violation
            best = min(best, value)
    return best


def test_feasible_policy_bounds_exact_recourse_for_every_scenario() -> None:
    instance = tiny_instance()
    x = [[2.0]]
    affine = build_affine_scenario_upper_bound(instance, x)
    for pattern in enumerate_patterns(2, 1, 1):
        exact = exact_integer_recourse(instance, x, pattern)
        assert exact <= feasible_greedy_upper_bound(instance, x, pattern).value + 1e-12
        assert exact <= no_shipment_upper_bound(instance, pattern) + 1e-12
        assert exact <= affine.value(pattern) + 1e-12


def test_exact_separator_matches_full_enumeration_and_prunes() -> None:
    instance = tiny_instance()
    x = [[2.0]]
    patterns = enumerate_patterns(2, 1, 1)
    exhaustive = {pattern: exact_integer_recourse(instance, x, pattern) for pattern in patterns}
    worst = max(exhaustive, key=exhaustive.get)
    result = exact_separation(
        instance,
        x,
        1,
        lambda pattern: ScenarioEvaluation(exhaustive[pattern], pattern),
        candidate_patterns=(worst,),
    )
    assert result.evaluation.value == max(exhaustive.values())
    assert result.pattern == worst
    assert result.lp_solves < result.total_scenarios
    assert result.lp_solves + result.safely_pruned_scenarios == result.total_scenarios


def test_gamma_two_scenario_accounting_is_complete() -> None:
    instance = tiny_instance()
    x = [[2.0]]
    patterns = enumerate_patterns(2, 1, 2)
    exhaustive = {pattern: exact_integer_recourse(instance, x, pattern) for pattern in patterns}
    worst = max(exhaustive, key=exhaustive.get)
    result = exact_separation(
        instance,
        x,
        2,
        lambda pattern: ScenarioEvaluation(exhaustive[pattern]),
        candidate_patterns=(worst,),
    )
    assert result.evaluation.value == max(exhaustive.values())
    assert result.lp_solves + result.safely_pruned_scenarios == len(patterns)


def test_micro_direct_enumeration_and_sg_choose_same_first_stage() -> None:
    instance = tiny_instance()
    patterns = enumerate_patterns(2, 1, 1)
    candidates = ([[0.0]], [[1.0]], [[2.0]], [[3.0]])
    direct_values = {}
    sg_values = {}
    previous_worst = ()
    for x in candidates:
        exhaustive = {pattern: exact_integer_recourse(instance, x, pattern) for pattern in patterns}
        direct_values[x[0][0]] = 2.0 * x[0][0] + max(exhaustive.values())
        separated = exact_separation(
            instance,
            x,
            1,
            lambda pattern: ScenarioEvaluation(exhaustive[pattern]),
            candidate_patterns=(previous_worst,),
        )
        previous_worst = separated.pattern
        sg_values[x[0][0]] = 2.0 * x[0][0] + separated.evaluation.value
    assert sg_values == direct_values
    assert min(sg_values, key=sg_values.get) == min(direct_values, key=direct_values.get)


def test_invalid_bound_assumptions_fail_closed() -> None:
    instance = tiny_instance()
    instance.demand_deviation[0][0] = -1.0
    with pytest.raises(ValueError, match="nonnegative"):
        feasible_greedy_upper_bound(instance, [[2.0]], ())


def test_sg_module_has_no_forbidden_algorithm_dependency() -> None:
    source = inspect.getsource(
        __import__(
            "robust_inventory_reconfiguration.scenario_generation_single_cut",
            fromlist=["dummy"],
        )
    )
    assert "pure_benders" not in source
    assert "standard_benders" not in source
    assert "product_risk_budget" not in source
    assert "gurobipy" not in source


def test_draft_protocol_is_closed_and_scoped_to_renault() -> None:
    import json

    path = ROOT / "experiments/configs/development/renault_sg_benders_v1_draft.yaml"
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["formal_run_authorized"] is False
    assert config["oracle_diagnostic_authorized"] is False
    assert config["case_ids"] == [
        "210202", "210628", "210129", "210310",
        "210330", "210323", "210428", "210611",
    ]
    assert config["fixed_scientific_parameters"] == {"Gamma": 2, "lambda_R": 0.05}
    assert config["algorithm"]["global_theta_count"] == 1
    assert config["algorithm"]["cuts_per_iteration_maximum"] == 1
    assert config["algorithm"]["product_risk_budget_decomposition"] is False
    assert config["algorithm"]["product_multicut"] is False
    assert config["algorithm"]["compact_global_robust_milp_oracle"] is False
