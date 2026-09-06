from pathlib import Path

import pytest

from robust_inventory_reconfiguration.instance import load_instance


@pytest.mark.parametrize("case", ["210202", "210628"])
def test_formal_instance_identity_and_phase_guards(case: str) -> None:
    instance = load_instance(Path("data/formal_instances") / f"{case}.json")
    assert (instance.num_depots, instance.num_regions, instance.num_products) == (15, 12, 8)
    assert instance.initial_inventory is None
    assert instance.reconfiguration_cost_multiplier is None
    assert instance.provenance["parameter_changes"] == "none"
