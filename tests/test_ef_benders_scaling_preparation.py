from pathlib import Path

import psutil
import pytest

from experiments import run_basic_benders_scaling as monitor
from experiments.run_ef_benders_scaling import DEFAULT_CONFIG, dry_run, load_config, validate_execution_gate
from scripts.audit_ef_benders_scaling_l10_preparation import theoretical_size


def test_theoretical_l10_sizes_match_frozen_direct_dimensions():
    size = theoretical_size()
    assert size["product_local_scenario_blocks"] == 3612
    assert size["ef_oracle"] == {"variables": 2257537, "constraints": 184303, "nonzeros": 6773683}
    assert size["direct_extensive_form"] == {"variables": 2258462, "constraints": 184929, "nonzeros": 6866733}


def test_dry_run_is_single_condition_and_zero_optimization():
    audit = dry_run(DEFAULT_CONFIG)
    assert audit["condition"]["condition_id"] == "EF_L10_S20260921"
    assert audit["formal_run_authorized"] is False
    assert audit["optimization_calls"] == 0
    assert all(audit["paired_instance_identity"].values())
    assert audit["next_attempt"] == "attempt-001"
    assert audit["readiness_decision"] == "READY_FOR_AUTHORIZATION"
    assert audit["resource_gate"]["process_tree_cap_gib"] == 7
    assert audit["resource_gate"]["startup_required_gib"] == 11
    assert audit["resource_gate"]["system_available_floor_gib"] == 3


def test_execution_is_fail_closed_by_resource_design():
    try:
        validate_execution_gate(DEFAULT_CONFIG)
    except RuntimeError as error:
        assert "NOT_AUTHORIZED" in str(error)
    else:
        raise AssertionError("execution gate unexpectedly opened")


def test_windows_process_disappearance_race_is_safe(monkeypatch):
    monkeypatch.setattr(monitor.psutil, "Process", lambda _pid: (_ for _ in ()).throw(psutil.NoSuchProcess(42)))
    assert monitor._process_tree_rss(42) == 0


def test_monitor_contract_covers_both_memory_stops_and_worker_exit():
    source = (Path(__file__).parents[1] / "experiments/run_basic_benders_scaling.py").read_text(encoding="utf-8")
    assert 'stop_reason = "RESOURCE_PROCESS_CAP"' in source
    assert 'stop_reason = "RESOURCE_SYSTEM_CAP"' in source
    assert '"worker_return_code": return_code' in source
    assert 'if return_code == 0 and stop_reason is None' in source


def test_config_preserves_single_cut_algorithm_boundary():
    config = load_config(Path(DEFAULT_CONFIG))
    algorithm = config["algorithm"]
    assert algorithm["global_theta_count"] == 1
    assert algorithm["cuts_per_iteration_maximum"] == 1
    assert algorithm["product_multicut"] is False
    assert algorithm["scenario_pruning"] is False
    assert algorithm["compact_global_robust_milp_oracle"] is False
