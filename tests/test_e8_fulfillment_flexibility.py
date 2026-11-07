from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys

import pytest

from robust_inventory_reconfiguration.e8_fulfillment_flexibility import (
    MODES,
    ProductBlockResult,
    build_mode_arcs,
    checkpoint_payload,
    compose_scenario_results,
    paired_reporting_rows,
    scenario_manifest,
    summarize_scenarios,
    validate_checkpoint,
    validate_mode_order,
    validate_nested_arcs,
)
from robust_inventory_reconfiguration.instance import InventoryInstance, load_instance


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "experiments/run_e8_fulfillment_flexibility_local.py"
CONFIG_PATH = ROOT / "experiments/configs/formal/e8_ex_post_fulfillment_flexibility_v1.json"


def load_runner():
    spec = importlib.util.spec_from_file_location("e8_runner_for_test", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def arc_instance() -> InventoryInstance:
    return InventoryInstance(
        name="arc",
        depot_ids=["D2", "D1", "D3"],
        region_ids=["R1", "R2"],
        product_ids=["P1"],
        base_demand=[[2.0], [3.0]],
        demand_deviation=[[1.0], [1.0]],
        transport_cost=[[[1.0], [4.0]], [[1.0], [2.0]], [[2.0], [1.0]]],
        shortage_penalty=[[10.0], [10.0]],
        service_level=[0.9],
        service_penalty=[100.0],
        capacity=[10.0, 10.0, 10.0],
        inventory_upper_bound=[[10.0], [10.0], [10.0]],
        fixed_depot_cost=[1.0, 1.0, 1.0],
        inventory_cost=[[1.0], [1.0], [1.0]],
        product_volume=[1.0],
        initial_inventory=None,
        reconfiguration_cost_multiplier=None,
        provenance={"fixture": True},
    )


def block(
    shocked: tuple[int, ...],
    *,
    recourse: float,
    shortage: tuple[float, float],
    service_violation: float,
    source_counts: tuple[int, int],
) -> ProductBlockResult:
    total_shortage = sum(shortage)
    return ProductBlockResult(
        product_index=0,
        shocked_regions=shocked,
        recourse_cost=recourse,
        transportation_cost=recourse - 10.0 * total_shortage - service_violation,
        shortage_penalty_cost=10.0 * total_shortage,
        service_violation_penalty_cost=service_violation,
        shortage_by_region=shortage,
        service_violation_quantity=service_violation / 100.0,
        shipment_by_region=(2.0, 2.0),
        source_count_by_region=source_counts,
        used_depot_ids_by_region=(
            tuple(f"D{i}" for i in range(source_counts[0])),
            tuple(f"D{i}" for i in range(source_counts[1])),
        ),
    )


def test_arc_ranking_nesting_zero_inventory_and_insufficient_k() -> None:
    instance = arc_instance()
    y = [1, 1, 1]
    x = [[5.0], [4.0], [0.0]]
    arcs = {mode: build_mode_arcs(instance, y, x, mode) for mode in MODES}
    validate_nested_arcs(arcs["k1"], arcs["k2"], arcs["full"])
    assert arcs["k1"][(0, 0)] == (1,)  # equal cost, depot ID D1 wins
    assert arcs["k2"][(0, 0)] == (1, 0)
    assert arcs["full"][(0, 0)] == (1, 0)
    assert 2 not in arcs["full"][(0, 0)]  # zero inventory is ineligible
    one_source = {mode: build_mode_arcs(instance, y, [[5.0], [0.0], [0.0]], mode) for mode in MODES}
    assert one_source["k2"][(1, 0)] == one_source["full"][(1, 0)] == (0,)


def test_disabled_depot_with_material_inventory_is_rejected() -> None:
    with pytest.raises(ValueError, match="disabled depot"):
        build_mode_arcs(arc_instance(), [1, 0, 1], [[5.0], [4.0], [0.0]], "full")


def test_scenario_composition_separates_worst_metrics() -> None:
    rows = compose_scenario_results(
        arc_instance(),
        1,
        [
            block((), recourse=10.0, shortage=(0.0, 0.0), service_violation=0.0, source_counts=(1, 1)),
            block((0,), recourse=30.0, shortage=(0.5, 0.0), service_violation=1.0, source_counts=(2, 1)),
            block((1,), recourse=20.0, shortage=(0.0, 2.0), service_violation=3.0, source_counts=(1, 2)),
        ],
    )
    summary = summarize_scenarios(rows)
    assert [row["scenario_id"] for row in rows] == ["S0000", "S0001", "S0002"]
    assert summary["nominal"]["scenario_id"] == "S0000"
    assert summary["worst_economic_cost"]["representative_scenario_id"] == "S0001"
    assert summary["maximum_total_shortage"]["representative_scenario_id"] == "S0002"
    assert summary["maximum_service_violation"]["representative_scenario_id"] == "S0002"
    assert rows[1]["actual_multi_source_region_product_count"] == 1
    assert math.isclose(rows[1]["cost_component_residual"], 0.0, abs_tol=1e-12)


def test_checkpoint_identity_and_corruption_guards() -> None:
    blocks = [
        block((), recourse=10.0, shortage=(0.0, 0.0), service_violation=0.0, source_counts=(1, 1))
    ]
    identity = {"case": "X", "mode": "k1"}
    value = checkpoint_payload(identity, 0, blocks, {"primary_status": 2})
    restored = validate_checkpoint(value, identity, 0, 1)
    assert restored == blocks
    damaged = dict(value)
    damaged["solver_status"] = "FAILED"
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_checkpoint(damaged, identity, 0, 1)
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_checkpoint(value, {"case": "Y", "mode": "k1"}, 0, 1)


def test_mode_order_is_enforced() -> None:
    summaries = {
        "k1": {"worst_economic_cost": {"value": 12.0}},
        "k2": {"worst_economic_cost": {"value": 11.0}},
        "full": {"worst_economic_cost": {"value": 10.0}},
    }
    validate_mode_order(summaries, 1e-8)
    summaries["full"]["worst_economic_cost"]["value"] = 13.0
    with pytest.raises(ValueError, match="monotonicity"):
        validate_mode_order(summaries, 1e-8)


def reporting_fixture(cost: float) -> list[dict[str, object]]:
    return [
        {
            "scenario_id": f"S{index:04d}",
            "shock_set": [] if index == 0 else [["R1", "P1"]],
            "recourse_cost": cost + (1.0 if index == 1 else 0.0),
            "transportation_cost": cost + (1.0 if index == 1 else 0.0),
            "shortage_penalty_cost": 0.0,
            "service_violation_penalty_cost": 0.0,
            "total_shortage": 0.0,
            "demand_weighted_fill_rate": 1.0,
            "worst_region_fill_rate": 1.0,
            "service_violation_quantity": 0.0,
        }
        for index in range(4657)
    ]


def test_paired_reporting_requires_complete_identical_scenarios() -> None:
    rows = {
        "k1": reporting_fixture(12.0),
        "k2": reporting_fixture(11.0),
        "full": reporting_fixture(10.0),
    }
    summaries = {mode: summarize_scenarios(value) for mode, value in rows.items()}
    output = paired_reporting_rows(rows, summaries, 1e-8)
    assert len(output) == 6
    assert {row["evaluation_basis"] for row in output} == {
        "nominal_demand",
        "full_mode_worst_economic_cost",
    }
    incomplete = {mode: value[:] for mode, value in rows.items()}
    incomplete["k1"] = incomplete["k1"][:-1]
    with pytest.raises(ValueError, match="complete frozen scenario set"):
        paired_reporting_rows(incomplete, summaries, 1e-8)
    mismatched = {mode: [dict(row) for row in value] for mode, value in rows.items()}
    mismatched["k2"][1]["shock_set"] = [["R2", "P1"]]
    with pytest.raises(ValueError, match="identical scenarios"):
        paired_reporting_rows(mismatched, summaries, 1e-8)


def test_frozen_renault_scenario_manifests_have_4657_ids() -> None:
    hashes = set()
    for case_id in ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611"):
        instance = load_instance(ROOT / f"data/formal_instances_v2/{case_id}.json")
        manifest = scenario_manifest(instance, 2)
        assert manifest["component_count"] == 96
        assert manifest["scenario_count"] == 4657
        hashes.add(manifest["entries_sha256"])
    assert len(hashes) == 1


def test_protocol_is_unauthorized_and_dry_run_makes_no_solver_call(monkeypatch) -> None:
    runner = load_runner()
    config = runner.read_json(CONFIG_PATH)
    assert config["authorization"]["formal_run_authorized"] is False
    assert config["authorization"]["pilot_run_authorized"] is False
    monkeypatch.setattr(
        runner,
        "solve_product_blocks",
        lambda *args, **kwargs: pytest.fail("dry-run reached Gurobi solve path"),
    )
    report = runner.dry_run(preflight=True)
    assert report["optimization_calls"] == 0
    with pytest.raises(PermissionError, match="NOT_AUTHORIZED"):
        runner.validate_execution_gate("210202", "k1", pilot=False)
    with pytest.raises(PermissionError, match="NOT_AUTHORIZED"):
        runner.validate_execution_gate("210202", "k1", pilot=True)


def test_runner_has_no_first_stage_optimization_path() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    forbidden = (
        "solve_prb_benders",
        "solve_exact_reconfiguration",
        "build_exact_reconfiguration_model",
        "solve_accelerated_prb_benders",
    )
    assert not any(name in source for name in forbidden)
