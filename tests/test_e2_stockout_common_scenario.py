from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.e2_stockout_common_scenario import (
    FrozenPolicy,
    canonical_sha256,
    coordinate_payload,
    coordinate_sha256,
    evaluate_fixed_policy_scenarios,
    frozen_scenario_ids,
    improvement_percent,
    require_optimal_solver_status,
    scenario_manifest_sha256,
    static_source_audit,
    summarize_complete_policy_metrics,
    summarize_partial_policy_metrics,
    validate_checkpoint,
    write_checkpoint,
)
from robust_inventory_reconfiguration.robust_service import (
    evaluate_robust_service_detailed,
)


pytest.importorskip("gurobipy")


def frozen_policy(tiny_instance, tmp_path: Path) -> FrozenPolicy:
    y = [1]
    x = [[5.0, 2.0]]
    zeros = [[0.0, 0.0]]
    source = tmp_path / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    return FrozenPolicy(
        policy_id="TEST_EXISTING",
        case_id="tiny",
        lineage="TEST",
        source_path=source,
        source_run_id="TEST-RUN",
        certification_source_path=source,
        certification_source_sha256="c" * 64,
        instance_sha256="a" * 64,
        source_file_sha256="b" * 64,
        coordinates_sha256=coordinate_sha256(y, x, zeros, zeros),
        solver_status="NOT_APPLICABLE",
        exact_certification="TEST",
        pilot_authorized=True,
        formal_authorized=False,
        y=y,
        x=x,
        a_plus=zeros,
        a_minus=zeros,
    )


def test_product_local_blocks_match_existing_full_scenario_evaluator(
    tiny_instance, tmp_path: Path
) -> None:
    policy = frozen_policy(tiny_instance, tmp_path)
    selected = ["S0000", "S0001", "S0005"]
    evaluated = evaluate_fixed_policy_scenarios(tiny_instance, policy, selected)
    reference = evaluate_robust_service_detailed(tiny_instance, policy.x, 2)
    reference_by_shock = {
        tuple(tuple(item) for item in row.shock_set): row for row in reference.scenarios
    }
    for row in evaluated["scenarios"]:
        expected = reference_by_shock[tuple(tuple(item) for item in row["shock_set"])]
        assert row["total_shortage"] == pytest.approx(expected.total_shortage, abs=1e-7)
        assert row["transportation_cost"] == pytest.approx(expected.transportation_cost, abs=1e-6)
        assert row["shortage_penalty_cost"] == pytest.approx(expected.shortage_cost, abs=1e-6)
        assert row["service_penalty_cost"] == pytest.approx(expected.service_penalty_cost, abs=1e-6)
        assert row["economic_optimum_recourse_cost"] == pytest.approx(expected.recourse_cost, abs=1e-6)


def test_first_stage_coordinates_are_unchanged_and_repeatable(
    tiny_instance, tmp_path: Path
) -> None:
    policy = frozen_policy(tiny_instance, tmp_path)
    before = copy.deepcopy(coordinate_payload(policy.y, policy.x, policy.a_plus, policy.a_minus))
    first = evaluate_fixed_policy_scenarios(tiny_instance, policy, ["S0000", "S0001"])
    second = evaluate_fixed_policy_scenarios(tiny_instance, policy, ["S0000", "S0001"])
    assert canonical_sha256(before) == policy.coordinates_sha256
    assert first["policy_coordinates_before_sha256"] == first["policy_coordinates_after_sha256"]
    for left, right in zip(first["scenarios"], second["scenarios"], strict=True):
        for key in (
            "total_shipment",
            "total_shortage",
            "total_service_violation",
            "transportation_cost",
            "shortage_penalty_cost",
            "service_penalty_cost",
            "recourse_cost",
        ):
            assert left[key] == pytest.approx(right[key], abs=1e-9)


def test_cost_components_come_from_solution_and_reconcile(
    tiny_instance, tmp_path: Path
) -> None:
    policy = frozen_policy(tiny_instance, tmp_path)
    result = evaluate_fixed_policy_scenarios(tiny_instance, policy, ["S0000"])
    row = result["scenarios"][0]
    assert row["recourse_cost"] == pytest.approx(
        row["transportation_cost"]
        + row["shortage_penalty_cost"]
        + row["service_penalty_cost"],
        abs=1e-9,
    )
    assert abs(row["reporting_tie_break_cost_delta"]) <= (
        tiny_instance.num_products * 1e-7 + 1e-9
    )


def test_manifest_is_policy_independent_and_canonical(tiny_instance) -> None:
    assert scenario_manifest_sha256(tiny_instance) == scenario_manifest_sha256(tiny_instance)


def test_unavailable_metrics_are_not_zero_filled() -> None:
    assert improvement_percent(0.0, 0.0, denominator_tolerance=1e-9) is None
    assert improvement_percent(10.0, 8.0, denominator_tolerance=1e-9) == pytest.approx(20.0)


def test_missing_or_invalid_scenarios_are_rejected(tiny_instance, tmp_path: Path) -> None:
    policy = frozen_policy(tiny_instance, tmp_path)
    with pytest.raises(ValueError, match="outside the frozen manifest"):
        evaluate_fixed_policy_scenarios(tiny_instance, policy, ["S9999"])
    with pytest.raises(ValueError, match="duplicate scenario"):
        evaluate_fixed_policy_scenarios(tiny_instance, policy, ["S0000", "S0000"])


@pytest.mark.parametrize("status", [None, 3, 9, 11])
def test_unsolved_infeasible_timeout_and_interrupted_statuses_raise(status) -> None:
    with pytest.raises(RuntimeError, match="failed or was incomplete"):
        require_optimal_solver_status(status, optimal_status=2, phase="test phase")


def metric_row(identifier: str) -> dict:
    index = int(identifier[1:])
    return {
        "scenario_id": identifier,
        "solver_status": "OPTIMAL",
        "total_shortage": 7.0 if index == 1 else 5.0,
        "total_service_violation": 2.0 if index == 2 else 1.0,
        "shortage_penalty_cost": 11.0 if index == 3 else 10.0,
        "service_penalty_cost": 3.0,
        "transportation_cost": 20.0 if index == 4 else 4.0,
        "recourse_cost": 33.0 if index == 4 else 17.0,
        "economic_optimum_recourse_cost": 33.0 if index == 4 else 17.0,
    }


def complete_metric_rows() -> list[dict]:
    return [metric_row(identifier) for identifier in frozen_scenario_ids(4657)]


def test_pilot_subset_cannot_pass_complete_set_validation() -> None:
    rows = [metric_row(identifier) for identifier in ("S0000", "S0001", "S0097")]
    partial = summarize_partial_policy_metrics(rows)
    assert partial["coverage_status"] == "PARTIAL_SCENARIO_DIAGNOSTIC"
    assert "worst_over_observed_subset" in partial
    assert "worst_over_frozen_set" not in partial
    with pytest.raises(ValueError, match="incomplete frozen scenario set"):
        summarize_complete_policy_metrics(rows, frozen_scenario_ids(4657))


def test_complete_summary_rejects_one_missing_scenario() -> None:
    with pytest.raises(ValueError, match="missing=.*S4656"):
        summarize_complete_policy_metrics(
            complete_metric_rows()[:-1], frozen_scenario_ids(4657)
        )


def test_complete_summary_rejects_duplicate_and_missing_id() -> None:
    rows = complete_metric_rows()
    rows[-1] = metric_row("S0000")
    with pytest.raises(ValueError, match="duplicates=.*S0000.*missing=.*S4656"):
        summarize_complete_policy_metrics(rows, frozen_scenario_ids(4657))


def test_complete_summary_rejects_unknown_id() -> None:
    rows = complete_metric_rows()
    rows[-1] = metric_row("S9999")
    with pytest.raises(ValueError, match="unknown=.*S9999"):
        summarize_complete_policy_metrics(rows, frozen_scenario_ids(4657))


def test_complete_summary_rejects_incomplete_solver_result() -> None:
    rows = complete_metric_rows()
    rows[1]["solver_status"] = "TIME_LIMIT"
    with pytest.raises(ValueError, match="incomplete solver result"):
        summarize_complete_policy_metrics(rows, frozen_scenario_ids(4657))


def test_all_4657_exact_ids_pass_complete_validation() -> None:
    summary = summarize_complete_policy_metrics(
        complete_metric_rows(), frozen_scenario_ids(4657)
    )
    assert summary["coverage_status"] == "COMPLETE_FROZEN_SCENARIO_SET"
    assert summary["scenario_count"] == 4657


def test_complete_metric_summary_keeps_worst_concepts_separate() -> None:
    summary = summarize_complete_policy_metrics(
        complete_metric_rows(), frozen_scenario_ids(4657)
    )
    worst = summary["worst_over_frozen_set"]
    assert worst["total_shortage"]["representative_scenario_id"] == "S0001"
    assert worst["total_service_violation"]["representative_scenario_id"] == "S0002"
    assert worst["shortage_penalty_cost"]["representative_scenario_id"] == "S0003"
    assert worst["economic_optimum_recourse_cost"]["representative_scenario_id"] == "S0004"


def test_corrupt_or_mismatched_checkpoint_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = {
        "classification": "PILOT_NON_PUBLISHABLE",
        "instance_sha256": "a",
        "policy_sha256": "b",
        "scenario_manifest_sha256": "c",
        "code_sha256": "d",
        "config_sha256": "e",
    }
    write_checkpoint(path, checkpoint)
    assert validate_checkpoint(
        path,
        instance_sha256="a",
        policy_sha256="b",
        scenario_manifest_sha256_value="c",
        code_sha256="d",
        config_sha256="e",
    ) == checkpoint
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_checkpoint(
            path,
            instance_sha256="wrong",
            policy_sha256="b",
            scenario_manifest_sha256_value="c",
            code_sha256="d",
            config_sha256="e",
        )
    path.write_text(json.dumps({"tampered": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="content hash mismatch"):
        validate_checkpoint(
            path,
            instance_sha256="a",
            policy_sha256="b",
            scenario_manifest_sha256_value="c",
            code_sha256="d",
            config_sha256="e",
        )


def test_evaluator_source_has_no_first_stage_solver_calls() -> None:
    import robust_inventory_reconfiguration.e2_stockout_common_scenario as module

    audit = static_source_audit(Path(module.__file__))
    assert audit["pass"] is True
    assert audit["forbidden_first_stage_call_hits"] == []
