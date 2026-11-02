from __future__ import annotations

import pytest

from robust_inventory_reconfiguration.e2_stockout_common_scenario import (
    validate_economic_stage_fallback,
)


def valid():
    return dict(
        shipment=[[3.0, 1.0], [0.0, 2.0]],
        shortages=[0.0, 0.0],
        excess=0.0,
        demand=[3.0, 3.0],
        stock=[4.0, 2.0],
        service_level=0.9,
        tolerance=1e-8,
    )


def test_feasible_economic_fallback():
    assert validate_economic_stage_fallback(**valid()) == pytest.approx(0.0)


@pytest.mark.parametrize("changes", [
    {"shortages": [-1e-4, 0.0]},
    {"shipment": [[2.0, 1.0], [0.0, 2.0]]},
    {"shipment": [[3.0, 2.0], [0.0, 2.0]]},
    {"shortages": [1.0, 0.0]},
    {"excess": -0.01},
    {"shipment": [[float("nan"), 1.0], [0.0, 2.0]]},
])
def test_reject_infeasible_or_nonfinite(changes):
    kwargs = valid() | changes
    with pytest.raises((RuntimeError, ValueError)):
        validate_economic_stage_fallback(**kwargs)


def test_reject_dimensions():
    kwargs = valid() | {"stock": [4.0]}
    with pytest.raises(ValueError):
        validate_economic_stage_fallback(**kwargs)
