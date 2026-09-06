from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import isfinite
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InventoryInstance:
    """Identity-aware input contract for the reconfiguration model."""

    name: str
    depot_ids: list[str]
    region_ids: list[str]
    product_ids: list[str]
    base_demand: list[list[float]]
    demand_deviation: list[list[float]]
    transport_cost: list[list[list[float]]]
    shortage_penalty: list[list[float]]
    service_level: list[float]
    service_penalty: list[float]
    capacity: list[float]
    inventory_upper_bound: list[list[float]]
    fixed_depot_cost: list[float]
    inventory_cost: list[list[float]]
    product_volume: list[float]
    initial_inventory: list[list[float]] | None
    reconfiguration_cost_multiplier: float | None
    provenance: dict[str, Any]

    def __post_init__(self) -> None:
        self.validate()

    @property
    def num_depots(self) -> int:
        return len(self.depot_ids)

    @property
    def num_regions(self) -> int:
        return len(self.region_ids)

    @property
    def num_products(self) -> int:
        return len(self.product_ids)

    def validate(self) -> None:
        _require_unique("depot_ids", self.depot_ids)
        _require_unique("region_ids", self.region_ids)
        _require_unique("product_ids", self.product_ids)
        i, r, j = self.num_depots, self.num_regions, self.num_products
        _require_matrix("base_demand", self.base_demand, r, j)
        _require_matrix("demand_deviation", self.demand_deviation, r, j)
        _require_tensor("transport_cost", self.transport_cost, i, r, j)
        _require_matrix("shortage_penalty", self.shortage_penalty, r, j)
        _require_vector("service_level", self.service_level, j)
        _require_vector("service_penalty", self.service_penalty, j)
        _require_vector("capacity", self.capacity, i)
        _require_matrix("inventory_upper_bound", self.inventory_upper_bound, i, j)
        _require_vector("fixed_depot_cost", self.fixed_depot_cost, i)
        _require_matrix("inventory_cost", self.inventory_cost, i, j)
        _require_vector("product_volume", self.product_volume, j)
        if self.initial_inventory is not None:
            _require_matrix("initial_inventory", self.initial_inventory, i, j)
        if self.reconfiguration_cost_multiplier is not None:
            raise ValueError("reconfiguration_cost_multiplier must remain unset in this phase")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InventoryInstance":
        return cls(**data)


def load_instance(path: str | Path) -> InventoryInstance:
    return InventoryInstance.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_instance(instance: InventoryInstance, path: str | Path) -> None:
    Path(path).write_text(json.dumps(instance.to_dict(), indent=2) + "\n", encoding="utf-8")


def _require_unique(name: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} contains duplicates")


def _require_vector(name: str, values: list[float], length: int) -> None:
    if len(values) != length:
        raise ValueError(f"{name} must have length {length}")
    if any(not isfinite(float(value)) for value in values):
        raise ValueError(f"{name} contains a non-finite value")


def _require_matrix(name: str, values: list[list[float]], rows: int, columns: int) -> None:
    if len(values) != rows or any(len(row) != columns for row in values):
        raise ValueError(f"{name} must have shape {rows}x{columns}")
    if any(not isfinite(float(value)) for row in values for value in row):
        raise ValueError(f"{name} contains a non-finite value")


def _require_tensor(
    name: str,
    values: list[list[list[float]]],
    first: int,
    second: int,
    third: int,
) -> None:
    if len(values) != first or any(len(plane) != second for plane in values):
        raise ValueError(f"{name} must have shape {first}x{second}x{third}")
    if any(len(row) != third for plane in values for row in plane):
        raise ValueError(f"{name} must have shape {first}x{second}x{third}")
    if any(not isfinite(float(value)) for plane in values for row in plane for value in row):
        raise ValueError(f"{name} contains a non-finite value")
