from robust_inventory_reconfiguration.product_risk_budget_benders import (
    PRODUCTWISE_BENDERS_COMPATIBLE,
)


def test_productwise_benders_compatibility_marker() -> None:
    assert PRODUCTWISE_BENDERS_COMPATIBLE is True
