from __future__ import annotations

from robust_inventory_reconfiguration.x0_audit import SourceInventoryRow, audit_initial_inventory


def _rows(values) -> list[SourceInventoryRow]:
    return [
        SourceInventoryRow(depot, product, values[product])
        for depot in ["D1"]
        for product in ["P1", "P2"]
    ]


def test_x0_mapping_identity_checks(tiny_instance) -> None:
    rows = _rows({"P1": 3.0, "P2": 2.0})
    result = audit_initial_inventory(tiny_instance, list(reversed(rows)))
    assert result.mapping_pass is True
    assert result.total_initial_inventory == 5.0


def test_x0_mapping_failure_stops_metrics(tiny_instance) -> None:
    result = audit_initial_inventory(tiny_instance, None)
    assert result.classification == "SOURCE_MAPPING_FAILURE"
    assert result.missing_target_entries == 2
    assert result.capacity_violation_count is None


def test_audit_metric_calculations(tiny_instance) -> None:
    result = audit_initial_inventory(tiny_instance, _rows({"P1": 8.0, "P2": 7.0}))
    assert result.capacity_violation_count == 1
    assert result.max_capacity_ratio == 1.1
    assert result.ub_violation_count == 0
    assert result.product_inventory_coverage == {"P1": 8.0 / 6.0, "P2": 7.0 / 4.0}
    assert result.system_inventory_coverage == 1.5


def test_negative_inventory_fails_mapping(tiny_instance) -> None:
    result = audit_initial_inventory(tiny_instance, _rows({"P1": -1.0, "P2": 2.0}))
    assert result.mapping_pass is False
    assert result.negative_count == 1
    assert result.classification == "SOURCE_MAPPING_FAILURE"
