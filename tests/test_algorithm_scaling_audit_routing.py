from pathlib import Path

import pytest

from scripts.audit_algorithm_scaling_convergence_cost import (
    CONFIG,
    ROOT,
    resolve_audit_routes,
)


V2_CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost_v2_repaired_guard.yaml"


def test_explicit_v2_routing_uses_v2_config_and_output_root() -> None:
    expected_output = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
    config_path, output_root, config = resolve_audit_routes(
        V2_CONFIG,
        expected_output,
    )

    assert config_path == V2_CONFIG.resolve()
    assert output_root == expected_output.resolve()
    assert config["experiment_id"] == "ALGORITHM_SCALING_CONVERGENCE_COST_V2_REPAIRED_GUARD"


def test_default_routing_remains_v1() -> None:
    config_path, output_root, config = resolve_audit_routes()

    assert config_path == CONFIG.resolve()
    assert output_root == (
        ROOT / "experiments/results/algorithm_scaling_convergence_cost_v1"
    ).resolve()
    assert config["experiment_id"] == "ALGORITHM_SCALING_CONVERGENCE_COST_V1"


def test_mismatched_config_and_output_root_fail_closed() -> None:
    v1_output = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v1"

    with pytest.raises(RuntimeError, match="CONFIG_OUTPUT_ROOT_IDENTITY_MISMATCH"):
        resolve_audit_routes(V2_CONFIG, v1_output)
