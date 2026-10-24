from __future__ import annotations

from dataclasses import dataclass
from math import comb
import random
from statistics import fmean, median
from typing import Iterable

from .instance import InventoryInstance


@dataclass(frozen=True)
class ScalingDimensions:
    scale: str
    depots: int
    regions: int
    products: int


def summarize(values: Iterable[float]) -> dict[str, float | int]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("cannot summarize an empty calibration sample")

    def quantile(probability: float) -> float:
        position = probability * (len(ordered) - 1)
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    return {
        "count": len(ordered),
        "min": ordered[0],
        "p10": quantile(0.10),
        "p25": quantile(0.25),
        "median": median(ordered),
        "mean": fmean(ordered),
        "p75": quantile(0.75),
        "p90": quantile(0.90),
        "max": ordered[-1],
    }


def extract_renault_calibration(
    instances: list[InventoryInstance],
) -> dict[str, object]:
    if not instances:
        raise ValueError("at least one Renault instance is required")
    demand: list[float] = []
    deviation_ratio: list[float] = []
    capacity_ratio: list[float] = []
    ub_ratio: list[float] = []
    normalized_transport: list[float] = []
    fixed_cost_scale: list[float] = []
    holding_cost: list[float] = []
    shortage_penalty: list[float] = []
    service_penalty: list[float] = []
    product_volume: list[float] = []
    for instance in instances:
        product_demand = [
            sum(instance.base_demand[r][j] for r in range(instance.num_regions))
            for j in range(instance.num_products)
        ]
        total_demand = sum(product_demand)
        total_volume_demand = sum(
            product_demand[j] * instance.product_volume[j]
            for j in range(instance.num_products)
        )
        demand.extend(value for row in instance.base_demand for value in row)
        deviation_ratio.extend(
            instance.demand_deviation[r][j] / instance.base_demand[r][j]
            for r in range(instance.num_regions)
            for j in range(instance.num_products)
            if instance.base_demand[r][j] > 0
        )
        capacity_ratio.extend(value / total_volume_demand for value in instance.capacity)
        fixed_cost_scale.extend(value / total_demand for value in instance.fixed_depot_cost)
        for i in range(instance.num_depots):
            for j in range(instance.num_products):
                if product_demand[j] > 0:
                    ub_ratio.append(instance.inventory_upper_bound[i][j] / product_demand[j])
                holding_cost.append(instance.inventory_cost[i][j])
                for r in range(instance.num_regions):
                    normalized_transport.append(
                        instance.transport_cost[i][r][j] / instance.product_volume[j]
                    )
        shortage_penalty.extend(value for row in instance.shortage_penalty for value in row)
        service_penalty.extend(instance.service_penalty)
        product_volume.extend(instance.product_volume)
    return {
        "source_case_count": len(instances),
        "nominal_demand": summarize(demand),
        "deviation_to_nominal_ratio_positive_demand": summarize(deviation_ratio),
        "depot_capacity_to_system_volume_demand": summarize(capacity_ratio),
        "inventory_ub_to_product_nominal_demand": summarize(ub_ratio),
        "transport_cost_per_product_volume": summarize(normalized_transport),
        "fixed_cost_per_system_nominal_demand": summarize(fixed_cost_scale),
        "holding_cost": summarize(holding_cost),
        "shortage_penalty": summarize(shortage_penalty),
        "service_penalty": summarize(service_penalty),
        "product_volume": summarize(product_volume),
        "reconfiguration_friction": 0.05,
        "B_ref_rule": "first_stage_expenditure_of_Gamma0_unconstrained_budget_nominal_incumbent",
        "Gamma_rule": "fixed_2",
    }


def scaling_size(dimensions: ScalingDimensions, gamma: int = 2) -> dict[str, int]:
    i, r, j = dimensions.depots, dimensions.regions, dimensions.products
    patterns = sum(comb(r, g) for g in range(gamma + 1))
    blocks = j * patterns
    first_stage_variables = i + 3 * i * j
    pure_binary = r * j
    pure_continuous = i * j + 3 * r * j + j
    direct_variables = (
        first_stage_variables
        + j * (gamma + 1)
        + 1
        + blocks * (i * r + r + 1)
    )
    direct_constraints = (
        i + 2 * i * j + 1
        + blocks * (r + i + 2)
        + comb(j + gamma, gamma)
    )
    return {
        "first_stage_variables": first_stage_variables,
        "pure_binary_variables": pure_binary,
        "pure_continuous_variables": pure_continuous,
        "pure_total_variables": pure_binary + pure_continuous,
        "pure_constraints": i * r * j + 7 * r * j + 1,
        "prb_product_risk_blocks": blocks,
        "prb_master_surrogates": j * (gamma + 1) + 1,
        "prb_product_cut_dimension": i,
        "aggregate_cut_dimension": i * j,
        "direct_variables": direct_variables,
        "direct_constraints": direct_constraints,
    }


def build_renault_calibrated_instance(
    source_instances: list[InventoryInstance],
    dimensions: ScalingDimensions,
    seed: int,
) -> InventoryInstance:
    """Empirical bootstrap generator; it performs no optimization."""
    if not source_instances:
        raise ValueError("source_instances must not be empty")
    rng = random.Random(seed)
    product_count = source_instances[0].num_products
    if any(instance.num_products != product_count for instance in source_instances):
        raise ValueError("source instances must share the frozen product schema")
    product_schema = (
        source_instances[0].product_ids,
        source_instances[0].product_volume,
        source_instances[0].service_level,
        source_instances[0].service_penalty,
    )
    if any(
        (
            instance.product_ids,
            instance.product_volume,
            instance.service_level,
            instance.service_penalty,
        )
        != product_schema
        for instance in source_instances
    ):
        raise ValueError("source instances must share the frozen product attributes")
    if len({instance.num_regions for instance in source_instances}) != 1:
        raise ValueError("source instances must share the frozen region count")

    product_donors: list[int] = []
    while len(product_donors) < dimensions.products:
        cycle = list(range(product_count))
        rng.shuffle(cycle)
        product_donors.extend(cycle)
    product_donors = product_donors[:dimensions.products]
    demand_pool = [
        (case, region)
        for case, instance in enumerate(source_instances)
        for region in range(instance.num_regions)
    ]
    depot_pool = [
        (case, depot)
        for case, instance in enumerate(source_instances)
        for depot in range(instance.num_depots)
    ]
    rng.shuffle(demand_pool)
    rng.shuffle(depot_pool)
    if dimensions.regions > len(demand_pool) or dimensions.depots > len(depot_pool):
        raise ValueError("requested scale exceeds the empirical donor pools")
    demand_donors = demand_pool[:dimensions.regions]
    depot_donors = depot_pool[:dimensions.depots]

    base_demand: list[list[float]] = []
    demand_deviation: list[list[float]] = []
    shortage_penalty: list[list[float]] = []
    for donor_case, donor_region in demand_donors:
        donor = source_instances[donor_case]
        base_demand.append([donor.base_demand[donor_region][p] for p in product_donors])
        demand_deviation.append([donor.demand_deviation[donor_region][p] for p in product_donors])
        shortage_penalty.append([donor.shortage_penalty[donor_region][p] for p in product_donors])

    product_volume = [source_instances[0].product_volume[p] for p in product_donors]
    service_level = [source_instances[0].service_level[p] for p in product_donors]
    service_penalty = [source_instances[0].service_penalty[p] for p in product_donors]
    generated_product_demand = [
        sum(base_demand[r][j] for r in range(dimensions.regions))
        for j in range(dimensions.products)
    ]
    generated_total_demand = sum(generated_product_demand)
    generated_volume_demand = sum(
        generated_product_demand[j] * product_volume[j]
        for j in range(dimensions.products)
    )

    capacity: list[float] = []
    fixed_cost: list[float] = []
    inventory_cost: list[list[float]] = []
    inventory_ub: list[list[float]] = []
    transport_cost: list[list[list[float]]] = []
    for donor_case, donor_depot in depot_donors:
        donor = source_instances[donor_case]
        donor_product_demand = [
            sum(donor.base_demand[r][p] for r in range(donor.num_regions))
            for p in range(donor.num_products)
        ]
        donor_total_demand = sum(donor_product_demand)
        donor_volume_demand = sum(
            donor_product_demand[p] * donor.product_volume[p]
            for p in range(donor.num_products)
        )
        capacity.append(donor.capacity[donor_depot] / donor_volume_demand * generated_volume_demand)
        fixed_cost.append(donor.fixed_depot_cost[donor_depot] / donor_total_demand * generated_total_demand)
        inventory_cost.append([donor.inventory_cost[donor_depot][p] for p in product_donors])
        inventory_ub.append([
            donor.inventory_upper_bound[donor_depot][p] / donor_product_demand[p]
            * generated_product_demand[j]
            for j, p in enumerate(product_donors)
        ])
        depot_transport: list[list[float]] = []
        for donor_region_case, donor_region in demand_donors:
            transport_donor = source_instances[donor_region_case]
            compatible_depot = donor_depot % transport_donor.num_depots
            depot_transport.append([
                transport_donor.transport_cost[compatible_depot][donor_region][p]
                / transport_donor.product_volume[p] * product_volume[j]
                for j, p in enumerate(product_donors)
            ])
        transport_cost.append(depot_transport)

    return InventoryInstance(
        name=f"e1c_{dimensions.scale}_seed_{seed}",
        depot_ids=[f"E1C_D{i:03d}" for i in range(dimensions.depots)],
        region_ids=[f"E1C_R{r:03d}" for r in range(dimensions.regions)],
        product_ids=[f"E1C_P{j:03d}_FROM_{source_instances[0].product_ids[p]}" for j, p in enumerate(product_donors)],
        base_demand=base_demand,
        demand_deviation=demand_deviation,
        transport_cost=transport_cost,
        shortage_penalty=shortage_penalty,
        service_level=service_level,
        service_penalty=service_penalty,
        capacity=capacity,
        inventory_upper_bound=inventory_ub,
        fixed_depot_cost=fixed_cost,
        inventory_cost=inventory_cost,
        product_volume=product_volume,
        initial_inventory=None,
        reconfiguration_cost_multiplier=None,
        provenance={
            "dataset": "RENAULT_EMPIRICAL_8CASE_V1",
            "construction": "deterministic_empirical_bootstrap_v1",
            "seed": seed,
            "scale": dimensions.scale,
            "product_donors": product_donors,
            "demand_donors": demand_donors,
            "depot_donors": depot_donors,
            "x0_status": "REQUIRES_FROZEN_GAMMA0_NOMINAL_BASELINE_PREPARATION",
        },
    )


def validate_generated_instance(
    instance: InventoryInstance,
    dimensions: ScalingDimensions,
    seed: int,
) -> dict[str, bool]:
    """Static validation only; this function never constructs or solves a model."""
    provenance = instance.provenance
    checks = {
        "dimensions": (
            instance.num_depots,
            instance.num_regions,
            instance.num_products,
        ) == (dimensions.depots, dimensions.regions, dimensions.products),
        "dataset_identity": provenance.get("dataset") == "RENAULT_EMPIRICAL_8CASE_V1",
        "generator_identity": provenance.get("construction") == "deterministic_empirical_bootstrap_v1",
        "seed_identity": provenance.get("seed") == seed,
        "scale_identity": provenance.get("scale") == dimensions.scale,
        "donor_dimensions": (
            len(provenance.get("product_donors", [])) == dimensions.products
            and len(provenance.get("demand_donors", [])) == dimensions.regions
            and len(provenance.get("depot_donors", [])) == dimensions.depots
        ),
        "x0_deferred": (
            instance.initial_inventory is None
            and provenance.get("x0_status")
            == "REQUIRES_FROZEN_GAMMA0_NOMINAL_BASELINE_PREPARATION"
        ),
        "nonnegative_economic_data": all(
            value >= 0
            for values in (
                [value for row in instance.base_demand for value in row],
                [value for row in instance.demand_deviation for value in row],
                [value for plane in instance.transport_cost for row in plane for value in row],
                [value for row in instance.shortage_penalty for value in row],
                instance.capacity,
                [value for row in instance.inventory_upper_bound for value in row],
                instance.fixed_depot_cost,
                [value for row in instance.inventory_cost for value in row],
                instance.product_volume,
            )
            for value in values
        ),
    }
    return {**checks, "pass": all(checks.values())}
