from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from math import isfinite
from statistics import median

from .instance import InventoryInstance


@dataclass(frozen=True)
class SourceInventoryRow:
    depot_id: str
    product_id: str
    initial_inventory: float


@dataclass(frozen=True)
class AuditResult:
    case: str
    mapping_pass: bool
    classification: str
    missing_count: int
    nan_count: int
    inf_count: int
    negative_count: int
    duplicate_depot_ids: list[str]
    duplicate_product_ids: list[str]
    duplicate_pairs: list[list[str]]
    unmapped_source_entries: int
    missing_target_entries: int
    capacity_compatible_count: int | None
    capacity_violation_count: int | None
    max_capacity_ratio: float | None
    median_capacity_ratio: float | None
    p90_capacity_ratio: float | None
    violating_depots: list[str]
    ub_compatible_pair_count: int | None
    ub_violation_count: int | None
    max_ub_ratio: float | None
    median_ub_ratio: float | None
    violating_pairs: list[list[str]]
    ub_zero_positive_inventory: list[list[str]]
    zero_stock_depots: list[str]
    total_initial_inventory: float | None
    product_inventory_coverage: dict[str, float | None]
    system_inventory_coverage: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def audit_initial_inventory(
    instance: InventoryInstance,
    source_rows: list[SourceInventoryRow] | None,
) -> AuditResult:
    if source_rows is None:
        target_count = instance.num_depots * instance.num_products
        return AuditResult(
            case=instance.name,
            mapping_pass=False,
            classification="SOURCE_MAPPING_FAILURE",
            missing_count=target_count,
            nan_count=0,
            inf_count=0,
            negative_count=0,
            duplicate_depot_ids=[],
            duplicate_product_ids=[],
            duplicate_pairs=[],
            unmapped_source_entries=0,
            missing_target_entries=target_count,
            capacity_compatible_count=None,
            capacity_violation_count=None,
            max_capacity_ratio=None,
            median_capacity_ratio=None,
            p90_capacity_ratio=None,
            violating_depots=[],
            ub_compatible_pair_count=None,
            ub_violation_count=None,
            max_ub_ratio=None,
            median_ub_ratio=None,
            violating_pairs=[],
            ub_zero_positive_inventory=[],
            zero_stock_depots=[],
            total_initial_inventory=None,
            product_inventory_coverage={},
            system_inventory_coverage=None,
        )

    depot_counts = Counter(row.depot_id for row in source_rows)
    product_counts = Counter(row.product_id for row in source_rows)
    pair_counts = Counter((row.depot_id, row.product_id) for row in source_rows)
    duplicate_pairs = sorted([list(pair) for pair, count in pair_counts.items() if count > 1])
    target_pairs = {(depot, product) for depot in instance.depot_ids for product in instance.product_ids}
    source_pairs = set(pair_counts)
    unmapped = source_pairs - target_pairs
    missing = target_pairs - source_pairs
    finite_rows = [row for row in source_rows if isfinite(row.initial_inventory)]
    nan_count = sum(row.initial_inventory != row.initial_inventory for row in source_rows)
    inf_count = sum(not isfinite(row.initial_inventory) and row.initial_inventory == row.initial_inventory for row in source_rows)
    negative_count = sum(row.initial_inventory < 0 for row in finite_rows)
    mapping_pass = (
        not duplicate_pairs
        and not unmapped
        and not missing
        and not nan_count
        and not inf_count
        and not negative_count
    )
    if not mapping_pass:
        return AuditResult(
            case=instance.name,
            mapping_pass=False,
            classification="SOURCE_MAPPING_FAILURE",
            missing_count=len(missing),
            nan_count=nan_count,
            inf_count=inf_count,
            negative_count=negative_count,
            duplicate_depot_ids=sorted([key for key, count in depot_counts.items() if count > instance.num_products]),
            duplicate_product_ids=sorted([key for key, count in product_counts.items() if count > instance.num_depots]),
            duplicate_pairs=duplicate_pairs,
            unmapped_source_entries=len(unmapped),
            missing_target_entries=len(missing),
            capacity_compatible_count=None,
            capacity_violation_count=None,
            max_capacity_ratio=None,
            median_capacity_ratio=None,
            p90_capacity_ratio=None,
            violating_depots=[],
            ub_compatible_pair_count=None,
            ub_violation_count=None,
            max_ub_ratio=None,
            median_ub_ratio=None,
            violating_pairs=[],
            ub_zero_positive_inventory=[],
            zero_stock_depots=[],
            total_initial_inventory=None,
            product_inventory_coverage={},
            system_inventory_coverage=None,
        )

    values = {(row.depot_id, row.product_id): row.initial_inventory for row in source_rows}
    capacity_ratios = []
    violating_depots = []
    zero_stock_depots = []
    for i, depot in enumerate(instance.depot_ids):
        stock = [values[depot, product] for product in instance.product_ids]
        load = sum(instance.product_volume[j] * stock[j] for j in range(instance.num_products))
        ratio = _ratio(load, instance.capacity[i])
        capacity_ratios.append(ratio)
        if ratio > 1.0:
            violating_depots.append(depot)
        if sum(stock) == 0.0:
            zero_stock_depots.append(depot)

    ub_ratios = []
    violating_pairs = []
    zero_ub_positive = []
    for i, depot in enumerate(instance.depot_ids):
        for j, product in enumerate(instance.product_ids):
            value = values[depot, product]
            ub = instance.inventory_upper_bound[i][j]
            ratio = _ratio(value, ub)
            ub_ratios.append(ratio)
            if ratio > 1.0:
                violating_pairs.append([depot, product])
            if ub == 0.0 and value > 0.0:
                zero_ub_positive.append([depot, product])

    product_coverage: dict[str, float | None] = {}
    product_totals = []
    demand_totals = []
    for j, product in enumerate(instance.product_ids):
        stock = sum(values[depot, product] for depot in instance.depot_ids)
        demand = sum(instance.base_demand[r][j] for r in range(instance.num_regions))
        product_totals.append(stock)
        demand_totals.append(demand)
        product_coverage[product] = None if demand == 0.0 else stock / demand
    capacity_failure = bool(violating_depots)
    ub_failure = bool(violating_pairs)
    classification = (
        "BOTH_INCOMPATIBLE" if capacity_failure and ub_failure else
        "CAPACITY_INCOMPATIBLE" if capacity_failure else
        "UB_INCOMPATIBLE" if ub_failure else
        "DIRECTLY_COMPATIBLE"
    )
    return AuditResult(
        case=instance.name,
        mapping_pass=True,
        classification=classification,
        missing_count=0,
        nan_count=nan_count,
        inf_count=inf_count,
        negative_count=negative_count,
        duplicate_depot_ids=[],
        duplicate_product_ids=[],
        duplicate_pairs=[],
        unmapped_source_entries=0,
        missing_target_entries=0,
        capacity_compatible_count=instance.num_depots - len(violating_depots),
        capacity_violation_count=len(violating_depots),
        max_capacity_ratio=max(capacity_ratios),
        median_capacity_ratio=median(capacity_ratios),
        p90_capacity_ratio=_nearest_rank(capacity_ratios, 0.9),
        violating_depots=violating_depots,
        ub_compatible_pair_count=len(ub_ratios) - len(violating_pairs),
        ub_violation_count=len(violating_pairs),
        max_ub_ratio=max(ub_ratios),
        median_ub_ratio=median(ub_ratios),
        violating_pairs=violating_pairs,
        ub_zero_positive_inventory=zero_ub_positive,
        zero_stock_depots=zero_stock_depots,
        total_initial_inventory=sum(product_totals),
        product_inventory_coverage=product_coverage,
        system_inventory_coverage=(
            None if sum(demand_totals) == 0.0 else sum(product_totals) / sum(demand_totals)
        ),
    )


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return 0.0 if numerator == 0.0 else float("inf")
    return numerator / denominator


def _nearest_rank(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, int(len(ordered) * quantile + 0.999999999) - 1)
    return ordered[index]
