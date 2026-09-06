from __future__ import annotations

import json

import pytest

from robust_inventory_reconfiguration.instance import InventoryInstance, load_instance, save_instance


def test_instance_schema_roundtrip(tmp_path, tiny_instance) -> None:
    path = tmp_path / "instance.json"
    save_instance(tiny_instance, path)
    assert load_instance(path) == tiny_instance
    assert json.loads(path.read_text())["reconfiguration_cost_multiplier"] is None


def test_instance_rejects_duplicate_identity(tiny_instance) -> None:
    data = tiny_instance.to_dict()
    data["product_ids"] = ["P1", "P1"]
    with pytest.raises(ValueError, match="duplicates"):
        InventoryInstance.from_dict(data)


def test_multiplier_remains_unset(tiny_instance) -> None:
    data = tiny_instance.to_dict()
    data["reconfiguration_cost_multiplier"] = 1.0
    with pytest.raises(ValueError, match="must remain unset"):
        InventoryInstance.from_dict(data)
