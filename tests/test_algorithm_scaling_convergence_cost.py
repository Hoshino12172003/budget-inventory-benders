from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from robust_inventory_reconfiguration.algorithm_scaling import (
    METHODS,
    SEEDS,
    SIZES,
    dry_run_plan,
    enumerate_conditions,
    load_config,
    normalized_trajectory,
    require_formal_authorization,
    resource_dimension_check,
    resource_preflight_passes,
    resource_thresholds,
    validate_config,
    validate_scientific_parameters,
)
from robust_inventory_reconfiguration.algorithm_scaling_reporting import (
    RESULT_FIELDS,
    TRAJECTORY_FIELDS,
    validate_pairwise_fairness,
    write_reports,
)
from robust_inventory_reconfiguration.e1c_scaling import build_renault_calibrated_instance
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import PRBIteration
from robust_inventory_reconfiguration.pure_benders import PureBendersIteration
from robust_inventory_reconfiguration.standard_benders import StandardBendersIteration


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost.yaml"
V2_CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost_v2_repaired_guard.yaml"


def config() -> dict:
    value = load_config(CONFIG)
    validate_config(value)
    return value


def test_exact_frozen_grid_has_90_unique_conditions() -> None:
    conditions = enumerate_conditions()
    assert len(SIZES) == 3
    assert len(SEEDS) == 10
    assert METHODS == ("pure_benders", "aggregate_benders_structured_oracle", "prb_benders")
    assert len(conditions) == len({condition.condition_id for condition in conditions}) == 90
    assert len({condition.instance_id for condition in conditions}) == 30
    assert conditions == enumerate_conditions()
    assert conditions[0].condition_id == "ASC_L10_S20260921_PURE_BENDERS"


def test_dry_run_has_no_management_dimensions_or_direct_runs() -> None:
    plan = dry_run_plan(config())
    assert plan["optimization_calls"] == 0
    assert plan["instances"] == 30
    assert plan["physical_runs"] == 90
    assert plan["direct_runs"] == 0
    assert plan["shared_instance_preparations"] == 30
    assert plan["runs_by_method"] == {method: 30 for method in METHODS}
    assert plan["runs_by_size"] == {size.scale: 30 for size in SIZES}
    assert plan["management_sensitivity_dimensions"] == []
    assert plan["scientific_parameters"]["Gamma"] == 2
    assert plan["scientific_parameters"]["beta"] == 1.0
    assert plan["scientific_parameters"]["lambda_R"] == 0.05
    assert plan["scientific_parameters"]["SL"] == 0.90
    assert plan["scientific_parameters"]["phi_multiplier"] == 1.85


def test_formal_execution_authorization_is_explicit_and_revocable() -> None:
    value = config()
    assert value["formal_run_authorized"] is True
    assert value["authorization_transition"] == [False, True]
    require_formal_authorization(value)
    unauthorized = config()
    unauthorized["formal_run_authorized"] = False
    unauthorized["authorization_transition"] = [False]
    with pytest.raises(PermissionError, match="ALGORITHM_SCALING_FORMAL_RUN_NOT_AUTHORIZED"):
        require_formal_authorization(unauthorized)


def test_size_dependent_resource_thresholds_and_12_gib_decision() -> None:
    value = config()
    assert resource_thresholds(value, "L10") == {
        "minimum_available_memory_gib": 7.0,
        "maximum_process_tree_memory_gib": 4.0,
        "minimum_system_available_memory_gib": 3.0,
    }
    assert resource_thresholds(value, "XL10")["minimum_available_memory_gib"] == 10.0
    assert resource_thresholds(value, "XXL10")["minimum_available_memory_gib"] == 16.0
    assert resource_preflight_passes(value, "L10", [12.0, 12.0, 12.0])
    assert resource_preflight_passes(value, "XL10", [12.0, 12.0, 12.0])
    assert not resource_preflight_passes(value, "XXL10", [12.0, 12.0, 12.0])
    assert "minimum_available_memory_gib" not in value["resource_policy"]
    assert "maximum_process_tree_memory_gib" not in value["resource_policy"]


def test_post_run_audit_entrypoint_is_present_without_running_results() -> None:
    source = (ROOT / "scripts/audit_algorithm_scaling_convergence_cost.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--post-run"' in source
    assert "validate_pairwise_fairness" in source
    assert "POST_RUN_AUDIT_PASS" in source


def test_longest_formal_condition_result_path_is_windows_safe() -> None:
    from experiments.run_algorithm_scaling_convergence_cost import (
        _result_temporary_root,
        _run_root,
    )

    value = load_config(V2_CONFIG)
    condition_id = "ASC_L10_S20260921_AGGREGATE_BENDERS_STRUCTURED_ORACLE"
    output_root = (ROOT / value["output_directory"]).resolve()
    target = _run_root(output_root, condition_id)
    old_temporary = target.parent / f".{condition_id}.{'f' * 32}.tmp"
    new_temporary = _result_temporary_root(target)
    old_longest_path = old_temporary / "iteration_trajectory.json"
    new_longest_path = new_temporary / "iteration_trajectory.json"

    assert target.name == condition_id
    assert new_temporary.name.startswith(".tmp-")
    assert len(new_temporary.name) == len(".tmp-") + 32
    assert condition_id not in new_temporary.name
    assert len(str(old_longest_path)) - len(str(new_longest_path)) == 54
    assert len(str(new_longest_path)) < 240


def test_generated_instance_propagates_frozen_service_parameters_without_solving() -> None:
    sources = [load_instance(ROOT / f"data/formal_instances_v2/{case}.json") for case in config()["instance_family"]["source_case_ids"]]
    instance = build_renault_calibrated_instance(sources, SIZES[0], SEEDS[0])
    assert validate_scientific_parameters(instance) == {
        "SL": True,
        "phi": True,
        "soft_service_data": True,
        "pass": True,
    }
    assert all(resource_dimension_check(config(), size)["pass"] for size in SIZES)


def test_iteration_instrumentation_preserves_existing_fields_and_adds_timing() -> None:
    pure = PureBendersIteration(1, 1.0, 2.0, 1.0, 0.5, 0.1, True)
    aggregate = StandardBendersIteration(1, 1.0, 2.0, 1.0, 0.5, 1.0, 1.0, 0.0, 0.1, True)
    prb = PRBIteration(1, 1.0, 2.0, 0.5, 1.0, 1.0, 0.0, 3, 2, 2)
    for value in (pure, aggregate, prb):
        row = asdict(value)
        assert row["master_time_seconds"] == 0.0
        assert row["oracle_time_seconds"] == 0.0
        assert row["certification_time_seconds"] == 0.0
        assert row["cumulative_time_seconds"] == 0.0


def test_normalized_lb_trajectory_uses_final_lower_bound() -> None:
    rows = normalized_trajectory([
        {"iteration": 1, "lower_bound": 50.0, "upper_bound": 120.0, "relative_gap": 0.5, "cut_added": True},
        {"iteration": 2, "lower_bound": 100.0, "upper_bound": 100.0, "relative_gap": 0.0, "cut_added": False},
    ], 100.0)
    assert rows[0]["normalized_LB"] == 0.5
    assert rows[1]["normalized_LB"] == 1.0
    assert rows[0]["cuts_added"] == 1


def _synthetic_results() -> list[dict]:
    rows = []
    for condition in enumerate_conditions():
        result = {field: None for field in RESULT_FIELDS}
        method_index = METHODS.index(condition.method)
        result.update({
            "experiment_id": "TEST",
            "condition_id": condition.condition_id,
            "method": condition.method,
            "size": condition.size,
            "seed": condition.seed,
            "instance_id": condition.instance_id,
            "instance_hash": f"hash-{condition.size}-{condition.seed}",
            "config_hash": "config",
            "code_commit": "commit",
            "model_identity": "model",
            "solver_profile": "profile",
            "Gamma": 2,
            "beta": 1.0,
            "lambda_R": 0.05,
            "SL": 0.90,
            "phi_multiplier": 1.85,
            "solver_status": "OPTIMAL",
            "exact_certification": True,
            "final_objective": 100.0,
            "final_lower_bound": 100.0,
            "final_upper_bound": 100.0,
            "relative_gap": 0.0,
            "iterations": (10, 8, 5)[method_index],
            "iterations_to_99pct_final_LB": 2,
            "iterations_to_99_5pct_final_LB": 2,
            "iterations_to_99_9pct_final_LB": 3,
            "iterations_to_99_99pct_final_LB": 4,
            "cuts": (9, 7, 30)[method_index],
            "feasibility_cuts": 0,
            "optimality_cuts": (9, 7, 30)[method_index],
            "total_core_solve_time": (1.0, 8.0, 6.0)[method_index],
            "master_time": (0.4, 0.3, 0.2)[method_index],
            "oracle_time": (0.3, 5.0, 4.0)[method_index],
            "certification_time": 0.2,
            "initialization_other_overhead": 0.1,
            "master_share": (0.4, 0.0375, 0.033333333)[method_index],
            "oracle_share": (0.3, 0.625, 0.666666667)[method_index],
            "peak_process_tree_memory_gib": 1.0,
            "result_reused": False,
        })
        rows.append(result)
    return rows


def test_reporting_writes_required_tables_and_enforces_objective_identity(tmp_path: Path) -> None:
    results = _synthetic_results()
    trajectories = []
    for result in results:
        row = {field: 0 for field in TRAJECTORY_FIELDS}
        row.update({
            "experiment_id": result["experiment_id"],
            "condition_id": result["condition_id"],
            "method": result["method"],
            "size": result["size"],
            "seed": result["seed"],
            "instance_id": result["instance_id"],
            "iteration": 1,
            "LB": 100.0,
            "UB": 100.0,
            "gap": 0.0,
            "normalized_LB": 1.0,
        })
        trajectories.append(row)
    characteristics = []
    for size in SIZES:
        for seed in SEEDS:
            characteristics.append({
                "instance_id": f"ASC_INSTANCE_{size.scale}_S{seed}",
                "instance_hash": f"hash-{size.scale}-{seed}",
                "size": size.scale,
                "seed": seed,
            })
    classification = write_reports(results, trajectories, characteristics, tmp_path, objective_tolerance=1e-4)
    assert classification == "PRB_FEWER_ITERATIONS_BUT_HIGHER_ORACLE_COST"
    assert set(config()["required_outputs"]).issubset({path.name for path in tmp_path.iterdir()})
    changed = [dict(row) for row in results]
    changed[0]["final_objective"] = 100.01
    with pytest.raises(ValueError, match="pairwise objective mismatch"):
        validate_pairwise_fairness(changed, 1e-4)


def test_reporting_accepts_only_explicitly_documented_non_certified_condition(
    tmp_path: Path,
) -> None:
    results = _synthetic_results()
    failure_id = "ASC_XXL10_S20260925_PURE_BENDERS"
    results = [row for row in results if row["condition_id"] != failure_id]
    trajectories = []
    for result in results:
        row = {field: 0 for field in TRAJECTORY_FIELDS}
        row.update({
            "experiment_id": result["experiment_id"],
            "condition_id": result["condition_id"],
            "method": result["method"],
            "size": result["size"],
            "seed": result["seed"],
            "instance_id": result["instance_id"],
        })
        trajectories.append(row)
    characteristics = [
        {
            "instance_id": f"ASC_INSTANCE_{size.scale}_S{seed}",
            "instance_hash": f"hash-{size.scale}-{seed}",
            "size": size.scale,
            "seed": seed,
        }
        for size in SIZES
        for seed in SEEDS
    ]
    documented = [{"condition_id": failure_id}]

    classification = write_reports(
        results,
        trajectories,
        characteristics,
        tmp_path,
        objective_tolerance=1e-4,
        documented_non_certified=documented,
    )

    assert classification == "PRB_FEWER_ITERATIONS_BUT_HIGHER_ORACLE_COST"
    assert "exact-certified: 89" in (tmp_path / "algorithm_scaling_summary.md").read_text()
    assert len((tmp_path / "algorithm_scaling_pairwise.csv").read_text().splitlines()) == 89

    with pytest.raises(ValueError, match="certified or explicitly documented"):
        write_reports(
            results,
            trajectories,
            characteristics,
            tmp_path,
            objective_tolerance=1e-4,
        )
    with pytest.raises(ValueError, match="certified or explicitly documented"):
        write_reports(
            results,
            trajectories,
            characteristics,
            tmp_path,
            objective_tolerance=1e-4,
            documented_non_certified=[{"condition_id": "ASC_L10_S20260921_PURE_BENDERS"}],
        )
