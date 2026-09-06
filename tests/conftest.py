from __future__ import annotations

import pytest

from robust_inventory_reconfiguration.instance import InventoryInstance


@pytest.fixture
def tiny_instance() -> InventoryInstance:
    return InventoryInstance(
        name="tiny",
        depot_ids=["D1"],
        region_ids=["R1", "R2"],
        product_ids=["P1", "P2"],
        base_demand=[[4.0, 3.0], [2.0, 1.0]],
        demand_deviation=[[1.0, 2.0], [3.0, 4.0]],
        transport_cost=[[[1.0, 2.0], [3.0, 4.0]]],
        shortage_penalty=[[10.0, 20.0], [30.0, 40.0]],
        service_level=[0.5, 0.5],
        service_penalty=[100.0, 200.0],
        capacity=[20.0],
        inventory_upper_bound=[[10.0, 10.0]],
        fixed_depot_cost=[5.0],
        inventory_cost=[[1.0, 1.0]],
        product_volume=[1.0, 2.0],
        initial_inventory=None,
        reconfiguration_cost_multiplier=None,
        provenance={"fixture": True},
    )
