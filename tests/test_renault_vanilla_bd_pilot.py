from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/run_renault_vanilla_bd_pilot.py"
SPEC = importlib.util.spec_from_file_location("renault_vanilla_bd_pilot", SCRIPT)
assert SPEC and SPEC.loader
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def test_frozen_210202_loader_identity_and_parameters() -> None:
    loaded = pilot.load_frozen_renault_case("210202")
    assert loaded["identity"]["instance_hash"] == (
        "3827d86c5ec4e290ba7d091648dbe4e1501648bfda54ca485385889e9143ecee"
    )
    assert loaded["budget"] == 106510.9559990062
    assert loaded["gamma"] == 2
    assert loaded["lambda_r"] == 0.05
    assert loaded["instance"].initial_inventory == loaded["x0"]


def test_210202_global_scenario_cap_is_respected() -> None:
    loaded = pilot.load_frozen_renault_case("210202")
    instance = loaded["instance"]
    count = sum(
        __import__("math").comb(instance.num_regions * instance.num_products, size)
        for size in range(loaded["gamma"] + 1)
    )
    assert count == 4657
    assert count <= pilot.MAX_SCENARIOS


def test_pilot_is_single_case_and_separately_resource_bounded() -> None:
    assert pilot.CASE_ID == "210202"
    assert pilot.TIME_LIMIT_SECONDS == 300.0
    assert pilot.MAX_SCENARIOS == 5000
    assert pilot.PROCESS_MEMORY_GIB == 4.0
    assert pilot.MONITOR_INTERVAL_SECONDS == 0.25


def test_vanilla_oracle_has_no_product_risk_composition_dependency() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    class_source = source.split("class GlobalEnumeratedLPOracle", 1)[1].split(
        "def _tiny_inputs", 1
    )[0]
    assert "compose_risk_budget" not in class_source
    assert "ProductRiskSubproblem" not in class_source
    assert "GlobalRobustAdversarialSubproblem(" not in class_source
