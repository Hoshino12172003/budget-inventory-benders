from __future__ import annotations

from experiments import run_renault_extensive_form_benders as runner


def test_protocol_is_closed_and_scoped_to_eight_renault_cases() -> None:
    config = runner.load_config()
    assert config["formal_run_authorized"] is False
    assert tuple(config["case_ids"]) == runner.EXPECTED_CASES
    assert tuple(config["authorized_condition_ids"]) == runner.EXPECTED_CONDITIONS
    assert config["fixed_scientific_parameters"] == {"Gamma": 2, "lambda_R": 0.05}


def test_algorithm_contract_is_single_cut_monolithic_recourse() -> None:
    algorithm = runner.load_config()["algorithm"]
    assert algorithm["global_theta_count"] == 1
    assert algorithm["cuts_per_iteration_maximum"] == 1
    assert algorithm["monolithic_direct_recourse_lp"] is True
    assert algorithm["optimizer_calls_per_oracle"] == 1
    assert algorithm["scenario_pruning"] is False
    assert algorithm["product_subproblem_decomposition"] is False
    assert algorithm["product_multicut"] is False
    assert algorithm["compact_global_robust_milp_oracle"] is False


def test_all_frozen_identities_pass() -> None:
    config = runner.load_config()
    rows = [runner.condition_identity(config, case) for case in runner.EXPECTED_CASES]
    assert all(row["status"] == "PASS" for row in rows)
    assert all(row["global_scenario_count"] == 4657 for row in rows)


def test_resource_contract_is_frozen() -> None:
    resource = runner.load_config()["resource_policy"]
    assert resource["condition_time_limit_seconds"] == 300
    assert resource["maximum_process_tree_memory_gib"] == 4
    assert resource["minimum_available_memory_gib"] == 8
    assert resource["minimum_system_available_memory_gib"] == 3
    assert resource["minimum_free_disk_gib"] == 20
    assert resource["memory_monitor_interval_seconds"] == 0.25
    assert resource["parallel_workers"] == 1
    assert resource["retry_policy"] == "no_automatic_retry"
