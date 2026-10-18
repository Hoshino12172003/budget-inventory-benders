from __future__ import annotations

import csv
from pathlib import Path

import pytest

from experiments import run_basic_benders_scaling as runner
from scripts.audit_basic_benders_scaling_preparation import CONFIG, basic_workload, build_audit
from scripts.plot_algorithm_gap_trajectories import load_rows


ROOT = Path(__file__).resolve().parents[1]


def test_global_scenario_counts_and_reusable_lp_sizes() -> None:
    assert basic_workload(25, 24, 12, 2)["global_scenarios_per_oracle_call"] == 41617
    assert basic_workload(30, 30, 14, 2)["global_scenarios_per_oracle_call"] == 88411
    assert basic_workload(36, 36, 16, 2)["global_scenarios_per_oracle_call"] == 166177
    assert basic_workload(25, 24, 12, 2)["reusable_recourse_lp_variables"] == 7500
    assert basic_workload(36, 36, 16, 2)["reusable_recourse_lp_constraints"] == 1168


def test_protocol_is_closed_and_scoped_to_one_l10_pilot() -> None:
    config = runner.load_config(CONFIG)
    assert config["formal_run_authorized"] is False
    assert runner.candidate(config) == {
        "condition_id": "BASIC_L10_S20260921", "size": "L10", "seed": 20260921
    }
    assert config["algorithm"]["maximum_global_scenarios"] == 166177
    assert config["solver_tolerances"] == {
        "relative_gap": 1e-6, "cut_violation": 1e-7, "objective_certification": 1e-4
    }
    policy = config["resource_policy"]
    assert policy["maximum_process_tree_memory_gib_by_size"]["L10"] == 4
    assert policy["minimum_available_memory_gib_by_size"]["L10"] == 7
    assert policy["minimum_system_available_memory_gib"] == 3
    assert policy["condition_time_limit_seconds"] == 900
    assert policy["memory_monitor_interval_seconds"] == 0.25
    assert policy["retry_policy"] == "no_automatic_retry"


def test_execution_gate_fails_before_any_optimization(monkeypatch) -> None:
    monkeypatch.setattr(runner, "dry_run", lambda *_: pytest.fail("dry-run must not follow a closed authorization gate"))
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        runner.validate_execution_gate(CONFIG)


def test_static_audit_covers_all_inputs_and_known_failures() -> None:
    audit = build_audit()
    assert audit["optimization_calls"] == 0
    assert len(audit["frozen_inputs"]) == 30
    assert all(row["identity_status"] == "PASS" for row in audit["frozen_inputs"])
    assert audit["renault_basic_evidence"]["basic_exact_cases"] == 8
    assert audit["frozen_l10_xl10_direct_evidence"]["sha256_records"] == 179
    assert audit["scaling_v2"]["status"]["certified_conditions"] == 89
    assert audit["scaling_v2_archive_integrity"]["canonical_certified_archives"] == 89
    assert audit["convergence_trajectory"]["basic_scaling_conditions"] == 0
    assert len(audit["known_exclusions"]) == 3
    assert audit["xxl10_direct"]["checks"]["authorization_closed"] is True


def test_result_matrix_template_is_header_only_and_complete() -> None:
    path = ROOT / "artifacts/basic_benders_scaling_result_matrix_template.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
        fields = set(stream.seek(0) or csv.DictReader(stream).fieldnames or [])
    assert rows == []
    assert {"instance_id", "method", "exact_certification", "LB", "UB", "final_gap", "iteration", "trajectory_cumulative_time"} <= fields


def test_gap_plot_loader_requires_persisted_selected_rows() -> None:
    path = ROOT / ".pytest-basic-gap-trajectory.csv"
    try:
        path.write_text(
            "condition_id,method,iteration,gap,cumulative_time_seconds\nC1,Basic-BD,1,0.1,2.0\n",
            encoding="utf-8",
        )
        assert load_rows(path, {"C1"})[0]["gap"] == 0.1
        with pytest.raises(ValueError, match="no persisted trajectory"):
            load_rows(path, {"missing"})
    finally:
        path.unlink(missing_ok=True)
