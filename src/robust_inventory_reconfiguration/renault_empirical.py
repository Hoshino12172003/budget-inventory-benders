from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterator
import zipfile

from .instance import InventoryInstance


DATASET_ID = "RENAULT_EMPIRICAL_8CASE_V1"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
PRODUCTS = (
    "BAC---1041", "BAC-O-4312", "BAC-O-4325", "BAC-O-6423",
    "BAC-O-6433", "CON-S-0130", "SLI---0770", "SLI---1200",
)
EXPECTED_DEPOTS = {
    "210202": 15, "210628": 15, "210129": 15, "210310": 16,
    "210330": 11, "210323": 13, "210428": 18, "210611": 19,
}
PROCESSED_PREFIX = "renault_data_pipeline/data/renault_processed"
MAPPING_SHA256 = "0bcdd7bb99926ed780c56764c531b76971dbb0bf24e77198766a754d9dde95ff"


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def iter_csv(archive: zipfile.ZipFile, member: str) -> Iterator[dict[str, str]]:
    stream = io.TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="")
    try:
        yield from csv.DictReader(stream)
    finally:
        stream.close()


def read_csv(archive: zipfile.ZipFile, member: str) -> list[dict[str, str]]:
    return list(iter_csv(archive, member))


def quantile_linear(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def mapping_core(mapping: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema", "rule", "selected_cases", "common_customer_identity_count",
        "iterations", "centers", "assignments_by_case",
    )
    return {key: mapping[key] for key in keys}


def verify_mapping(mapping: dict[str, Any]) -> None:
    calculated = sha256_bytes(canonical_bytes(mapping_core(mapping)))
    if calculated != MAPPING_SHA256 or mapping.get("mapping_sha256") != MAPPING_SHA256:
        raise ValueError("paper-final region mapping hash changed")
    if tuple(mapping["selected_cases"]) != CASES:
        raise ValueError("paper-final case order changed")
    if mapping["common_customer_identity_count"] != 298 or len(mapping["centers"]) != 12:
        raise ValueError("paper-final geographic mapping dimensions changed")


def _member(case: str, name: str) -> str:
    return f"{PROCESSED_PREFIX}/{case}/{name}"


def _distance_rows(
    archive: zipfile.ZipFile, case: str, depot_ids: list[str], customer_ids: set[str]
) -> dict[str, dict[str, float]]:
    rows: dict[str, dict[str, float]] = {}
    stream = io.TextIOWrapper(archive.open(_member(case, "distances.csv")), encoding="utf-8-sig", newline="")
    try:
        reader = csv.reader(stream)
        header = next(reader)
        positions = [(index, value) for index, value in enumerate(header) if value in customer_ids]
        for row in reader:
            if row[0] in depot_ids:
                rows[row[0]] = {customer: float(row[index]) for index, customer in positions}
    finally:
        stream.close()
    if set(rows) != set(depot_ids):
        raise ValueError(f"distance rows are incomplete for {case}")
    return rows


def build_case(
    archive: zipfile.ZipFile,
    archive_sha256: str,
    mapping: dict[str, Any],
    case: str,
    builder_commit: str,
) -> tuple[InventoryInstance, dict[str, Any]]:
    if case not in CASES:
        raise ValueError(f"unsupported case: {case}")
    assignments = {key: int(value) for key, value in mapping["assignments_by_case"][case].items()}
    depots = read_csv(archive, _member(case, "depots.csv"))
    depot_ids = sorted(row["depot_code"] for row in depots)
    if len(depot_ids) != EXPECTED_DEPOTS[case] or len(set(depot_ids)) != len(depot_ids):
        raise ValueError(f"depot identities changed for {case}")
    customers = read_csv(archive, _member(case, "customers.csv"))
    customer_ids = {row["customer_code"] for row in customers}
    if set(assignments) != customer_ids:
        raise ValueError(f"mapping coverage changed for {case}")

    commodity_rows = read_csv(archive, _member(case, "commodities.csv"))
    volume_by_product = {row["commodity_code"]: float(row["length"]) for row in commodity_rows}
    if not set(PRODUCTS).issubset(volume_by_product):
        raise ValueError(f"frozen products are incomplete for {case}")
    volumes = [volume_by_product[product] for product in PRODUCTS]

    audit = json.loads(archive.read(_member(case, "audit.json")))
    constants = audit["constants"]
    km_cost = float(constants["km_cost"])
    vehicle_capacity = float(constants["vehicle_capacity"])
    if vehicle_capacity <= 0:
        raise ValueError("vehicle capacity must be positive")

    daily: dict[tuple[str, int, str], float] = {}
    customer_demand: dict[tuple[str, str], float] = {}
    days: set[str] = set()
    positive_raw_pairs: set[tuple[str, str]] = set()
    demand_records = 0
    for row in iter_csv(archive, _member(case, "demand_daily.csv")):
        demand_records += 1
        value = float(row["demand"])
        if value > 0:
            positive_raw_pairs.add((row["customer_code"], row["commodity_code"]))
        day = row["day"]
        days.add(day)
        product = row["commodity_code"]
        if product not in PRODUCTS or datetime.strptime(day, "%d/%m/%Y").weekday() >= 5:
            continue
        region = assignments[row["customer_code"]]
        daily[(day, region, product)] = daily.get((day, region, product), 0.0) + value
        key = (row["customer_code"], product)
        customer_demand[key] = customer_demand.get(key, 0.0) + value
    weekdays = sorted(day for day in days if datetime.strptime(day, "%d/%m/%Y").weekday() < 5)
    if not weekdays:
        raise ValueError(f"no weekdays found for {case}")

    base_demand: list[list[float]] = []
    demand_deviation: list[list[float]] = []
    for region in range(1, 13):
        base_row, deviation_row = [], []
        for product in PRODUCTS:
            values = [daily.get((day, region, product), 0.0) for day in weekdays]
            mean = sum(values) / len(values)
            base_row.append(mean)
            deviation_row.append(max(quantile_linear(values, 0.90) - mean, 0.0))
        base_demand.append(base_row)
        demand_deviation.append(deviation_row)

    customer_cost_rows = read_csv(archive, _member(case, "customer_commodity.csv"))
    shortage_cost = {
        (row["customer_code"], row["commodity_code"]): float(row["shortage_cost"])
        for row in customer_cost_rows if row["commodity_code"] in PRODUCTS
    }
    shortage_penalty: list[list[float]] = []
    for region in range(1, 13):
        region_customers = sorted(customer for customer in customer_ids if assignments[customer] == region)
        row_values = []
        for product in PRODUCTS:
            weights = [customer_demand.get((customer, product), 0.0) for customer in region_customers]
            costs = [shortage_cost[(customer, product)] for customer in region_customers]
            total_weight = sum(weights)
            row_values.append(
                sum(cost * weight for cost, weight in zip(costs, weights)) / total_weight
                if total_weight > 0 else statistics.median(costs)
            )
        shortage_penalty.append(row_values)

    distances = _distance_rows(archive, case, depot_ids, customer_ids)
    transport_cost: list[list[list[float]]] = []
    for depot in depot_ids:
        depot_planes = []
        for region in range(1, 13):
            region_customers = sorted(customer for customer in customer_ids if assignments[customer] == region)
            product_costs = []
            for product, volume in zip(PRODUCTS, volumes):
                weights = [customer_demand.get((customer, product), 0.0) for customer in region_customers]
                total_weight = sum(weights)
                representative_distance = (
                    sum(distances[depot][customer] * weight for customer, weight in zip(region_customers, weights)) / total_weight
                    if total_weight > 0 else statistics.fmean(distances[depot][customer] for customer in region_customers)
                )
                product_costs.append(km_cost * representative_distance * volume / vehicle_capacity)
            depot_planes.append(product_costs)
        transport_cost.append(depot_planes)

    depot_cost_rows = read_csv(archive, _member(case, "depot_commodity.csv"))
    inventory_cost_map: dict[tuple[str, str], float] = {}
    for row in depot_cost_rows:
        if row["commodity_code"] in PRODUCTS:
            key = (row["depot_code"], row["commodity_code"])
            if key in inventory_cost_map:
                raise ValueError(f"duplicate depot-product cost identity in {case}: {key}")
            inventory_cost_map[key] = float(row["excess_inventory_cost"])
    maximum_stock: dict[tuple[str, str], float] = {}
    observed_stock_values: dict[tuple[str, str], set[float]] = {}
    for row in iter_csv(archive, _member(case, "depot_daily.csv")):
        if row["commodity_code"] in PRODUCTS:
            key = (row["depot_code"], row["commodity_code"])
            observed_stock_values.setdefault(key, set()).add(float(row["maximum_stock"]))
    for key, values in observed_stock_values.items():
        if len(values) != 1:
            raise ValueError(f"maximum_stock is not time-invariant for {case}: {key}")
        maximum_stock[key] = next(iter(values))
    expected_pairs = {(depot, product) for depot in depot_ids for product in PRODUCTS}
    if set(inventory_cost_map) != expected_pairs or set(maximum_stock) != expected_pairs:
        raise ValueError(f"depot-product inputs are incomplete for {case}")
    inventory_cost = [[inventory_cost_map[(depot, product)] for product in PRODUCTS] for depot in depot_ids]
    capacity = [sum(volume_by_product[product] * maximum_stock[(depot, product)] for product in PRODUCTS) for depot in depot_ids]
    total_product_demand = [sum(base_demand[region][j] for region in range(12)) for j in range(8)]
    inventory_upper_bound = [
        [min(capacity[i] / volumes[j], 1.35 * total_product_demand[j]) for j in range(8)]
        for i in range(len(depot_ids))
    ]
    fixed_depot_cost = [
        0.012 * sum(inventory_cost_map[(depot, product)] * maximum_stock[(depot, product)] for product in PRODUCTS)
        for depot in depot_ids
    ]
    service_penalty = [1.85 * max(shortage_penalty[region][j] for region in range(12)) for j in range(8)]
    source_files = audit["files"]
    provenance = {
        "dataset_id": DATASET_ID,
        "case": case,
        "raw_source_identity": f"external://renault-raw/instances/{case}/",
        "normalized_source_identity": f"external://renault-processed/{case}/",
        "archive_sha256": archive_sha256,
        "source_file_sha256": {name: source_files[name]["sha256"] for name in sorted(source_files)},
        "mapping_sha256": MAPPING_SHA256,
        "builder_commit": builder_commit,
        "product_ids_frozen": list(PRODUCTS),
        "transformations": {
            "dbar": "weekday historical daily mean by region-product",
            "dhat": "max(linear Q0.90 of weekday regional daily demand - dbar, 0)",
            "inventory_cost": "Renault depot-product excess_inventory_cost",
            "capacity": "sum_j product_volume[j] * maximum_stock[i,j]",
            "inventory_upper_bound": "min(capacity[i]/volume[j], 1.35*sum_r dbar[r,j])",
            "fixed_depot_cost": "0.012*sum_j inventory_cost[i,j]*maximum_stock[i,j]",
            "shortage_penalty": "weekday-demand-weighted customer shortage cost; zero-demand regional median",
            "transport_cost": "km_cost*weekday-demand-weighted region distance*product_volume/vehicle_capacity",
            "service_level": 0.90,
            "service_penalty": "1.85*max_r shortage_penalty[r,j]",
        },
        "x0_semantics": "data-driven nominal incumbent inventory plan; populated after Gamma=0 construction",
        "raw_initial_inventory_used_as_x0": False,
    }
    instance = InventoryInstance(
        name=f"{DATASET_ID}_{case}", depot_ids=depot_ids,
        region_ids=[str(region) for region in range(1, 13)], product_ids=list(PRODUCTS),
        base_demand=base_demand, demand_deviation=demand_deviation,
        transport_cost=transport_cost, shortage_penalty=shortage_penalty,
        service_level=[0.90] * 8, service_penalty=service_penalty,
        capacity=capacity, inventory_upper_bound=inventory_upper_bound,
        fixed_depot_cost=fixed_depot_cost, inventory_cost=inventory_cost,
        product_volume=volumes, initial_inventory=None,
        reconfiguration_cost_multiplier=None, provenance=provenance,
    )
    characteristics = {
        "case": case, "raw_customers": len(customer_ids), "raw_depots": len(depot_ids),
        "formal_I": len(depot_ids), "R": 12, "J": 8, "planning_days": len(days),
        "weekday_planning_days": len(weekdays), "demand_records": demand_records,
        "demand_density": len(positive_raw_pairs) / (len(customer_ids) * len(commodity_rows)),
        "total_nominal_demand": sum(total_product_demand),
        "total_deviation": sum(map(sum, demand_deviation)), "uncertainty_items": 96,
    }
    return instance, characteristics
