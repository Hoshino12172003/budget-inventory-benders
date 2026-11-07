from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from itertools import combinations
import json
import math
from typing import Any, Iterable

from .instance import InventoryInstance
from .robust_service import canonical_fixed_inventory
from .scenarios import enumerate_scenario_components
from .solver_profile import apply_formal_solver_profile


MODES = ("k1", "k2", "full")
REPORTING_OPTIMALITY_TOLERANCE = 1e-7
INVENTORY_ELIGIBILITY_TOLERANCE = 1e-8
SHIPMENT_USAGE_TOLERANCE = 1e-8
FROZEN_SCENARIO_COUNT = 4657


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def policy_coordinates_hash(y: list[int], x: list[list[float]]) -> str:
    return canonical_hash({"y": y, "x": x})


def scenario_manifest(instance: InventoryInstance, gamma: int) -> dict[str, Any]:
    scenarios = enumerate_scenario_components(instance, gamma)
    entries = [
        {
            "scenario_id": f"S{index:04d}",
            "shock_set": [
                [instance.region_ids[r], instance.product_ids[j]] for r, j in scenario
            ],
        }
        for index, scenario in enumerate(scenarios)
    ]
    return {
        "enumeration_rule": "region_major_then_active_count_then_lexicographic_v1",
        "gamma": gamma,
        "component_count": instance.num_regions * instance.num_products,
        "scenario_count": len(entries),
        "entries_sha256": canonical_hash(entries),
    }


def _eligible_depots(
    instance: InventoryInstance,
    y: list[int],
    x: list[list[float]],
    region_index: int,
    product_index: int,
) -> list[int]:
    eligible = [
        i
        for i in range(instance.num_depots)
        if y[i] == 1
        and x[i][product_index] > INVENTORY_ELIGIBILITY_TOLERANCE
    ]
    return sorted(
        eligible,
        key=lambda i: (
            instance.transport_cost[i][region_index][product_index],
            instance.depot_ids[i],
        ),
    )


def build_mode_arcs(
    instance: InventoryInstance,
    y: list[int],
    x: list[list[float]],
    mode: str,
) -> dict[tuple[int, int], tuple[int, ...]]:
    if mode not in MODES:
        raise ValueError(f"unknown fulfillment mode: {mode}")
    if len(y) != instance.num_depots or any(value not in (0, 1) for value in y):
        raise ValueError("fixed depot activation vector is invalid")
    fixed_x = canonical_fixed_inventory(instance, x)
    for i in range(instance.num_depots):
        if y[i] == 0 and any(
            fixed_x[i][j] > INVENTORY_ELIGIBILITY_TOLERANCE
            for j in range(instance.num_products)
        ):
            raise ValueError("positive fixed inventory exists at a disabled depot")
    limit = {"k1": 1, "k2": 2, "full": None}[mode]
    arcs: dict[tuple[int, int], tuple[int, ...]] = {}
    for r in range(instance.num_regions):
        for j in range(instance.num_products):
            eligible = _eligible_depots(instance, y, fixed_x, r, j)
            selected = eligible if limit is None else eligible[:limit]
            arcs[(r, j)] = tuple(selected)
    return arcs


def validate_nested_arcs(
    k1: dict[tuple[int, int], tuple[int, ...]],
    k2: dict[tuple[int, int], tuple[int, ...]],
    full: dict[tuple[int, int], tuple[int, ...]],
) -> None:
    if set(k1) != set(k2) or set(k1) != set(full):
        raise ValueError("fulfillment modes use different region-product identities")
    for key in k1:
        if not set(k1[key]) <= set(k2[key]) <= set(full[key]):
            raise ValueError(f"fulfillment arc nesting is violated for {key}")


def arc_manifest(
    instance: InventoryInstance,
    arcs: dict[tuple[int, int], tuple[int, ...]],
) -> dict[str, Any]:
    entries = [
        {
            "region_id": instance.region_ids[r],
            "product_id": instance.product_ids[j],
            "depot_ids": [instance.depot_ids[i] for i in arcs[(r, j)]],
        }
        for r in range(instance.num_regions)
        for j in range(instance.num_products)
    ]
    return {
        "region_product_count": len(entries),
        "arc_count": sum(len(entry["depot_ids"]) for entry in entries),
        "entries": entries,
        "entries_sha256": canonical_hash(entries),
    }


def resource_estimate(
    instance: InventoryInstance,
    arcs: dict[tuple[int, int], tuple[int, ...]],
    gamma: int,
) -> dict[str, int]:
    blocks_per_product = sum(
        math.comb(instance.num_regions, g) for g in range(gamma + 1)
    )
    max_shipment_variables = max(
        sum(len(arcs[(r, j)]) for r in range(instance.num_regions))
        for j in range(instance.num_products)
    )
    variables_per_product_model = blocks_per_product * (
        max_shipment_variables + instance.num_regions + 1
    )
    constraints_per_product_model = blocks_per_product * (
        instance.num_regions + instance.num_depots + 1
    )
    return {
        "local_blocks_per_product": blocks_per_product,
        "sequential_product_models_per_mode": instance.num_products,
        "maximum_variables_in_one_product_model": variables_per_product_model,
        "maximum_constraints_in_one_product_model_before_tiebreak": constraints_per_product_model,
        "full_global_scenario_count": len(
            enumerate_scenario_components(instance, gamma)
        ),
    }


@dataclass(frozen=True)
class ProductBlockResult:
    product_index: int
    shocked_regions: tuple[int, ...]
    recourse_cost: float
    transportation_cost: float
    shortage_penalty_cost: float
    service_violation_penalty_cost: float
    shortage_by_region: tuple[float, ...]
    service_violation_quantity: float
    shipment_by_region: tuple[float, ...]
    source_count_by_region: tuple[int, ...]
    used_depot_ids_by_region: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["shocked_regions"] = list(self.shocked_regions)
        value["shortage_by_region"] = list(self.shortage_by_region)
        value["shipment_by_region"] = list(self.shipment_by_region)
        value["source_count_by_region"] = list(self.source_count_by_region)
        value["used_depot_ids_by_region"] = [
            list(ids) for ids in self.used_depot_ids_by_region
        ]
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProductBlockResult":
        return cls(
            product_index=int(value["product_index"]),
            shocked_regions=tuple(int(v) for v in value["shocked_regions"]),
            recourse_cost=float(value["recourse_cost"]),
            transportation_cost=float(value["transportation_cost"]),
            shortage_penalty_cost=float(value["shortage_penalty_cost"]),
            service_violation_penalty_cost=float(
                value["service_violation_penalty_cost"]
            ),
            shortage_by_region=tuple(float(v) for v in value["shortage_by_region"]),
            service_violation_quantity=float(value["service_violation_quantity"]),
            shipment_by_region=tuple(float(v) for v in value["shipment_by_region"]),
            source_count_by_region=tuple(
                int(v) for v in value["source_count_by_region"]
            ),
            used_depot_ids_by_region=tuple(
                tuple(str(v) for v in ids)
                for ids in value["used_depot_ids_by_region"]
            ),
        )


def solve_product_blocks(
    instance: InventoryInstance,
    x: list[list[float]],
    arcs: dict[tuple[int, int], tuple[int, ...]],
    product_index: int,
    gamma: int,
    *,
    threads: int,
    optimality_tolerance: float = REPORTING_OPTIMALITY_TOLERANCE,
    shipment_usage_tolerance: float = SHIPMENT_USAGE_TOLERANCE,
) -> tuple[list[ProductBlockResult], dict[str, Any]]:
    """Solve one product's exact local blocks; this is the only Gurobi path."""
    import gurobipy as gp
    from gurobipy import GRB

    if threads != 1:
        raise ValueError("the frozen E8 protocol requires Threads=1")
    if product_index not in range(instance.num_products):
        raise ValueError("product index is outside the instance")
    fixed_x = canonical_fixed_inventory(instance, x)
    regions = range(instance.num_regions)
    depots = range(instance.num_depots)
    model = gp.Model(f"e8_{instance.name}_p{product_index}")
    model.Params.OutputFlag = 0
    model.Params.Threads = threads
    apply_formal_solver_profile(model, mixed_integer=False)
    blocks: dict[tuple[int, ...], dict[str, Any]] = {}
    for local_gamma in range(gamma + 1):
        for shocked_regions in combinations(regions, local_gamma):
            shocked = set(shocked_regions)
            q = {
                (i, r): model.addVar(
                    lb=0.0, name=f"q_p{product_index}_s{'-'.join(map(str, shocked_regions)) or 'none'}_i{i}_r{r}"
                )
                for r in regions
                for i in arcs[(r, product_index)]
            }
            u = model.addVars(
                regions,
                lb=0.0,
                name=f"u_p{product_index}_s{'-'.join(map(str, shocked_regions)) or 'none'}",
            )
            e = model.addVar(
                lb=0.0,
                name=f"e_p{product_index}_s{'-'.join(map(str, shocked_regions)) or 'none'}",
            )
            demands = []
            for r in regions:
                demand = instance.base_demand[r][product_index]
                if r in shocked:
                    demand += instance.demand_deviation[r][product_index]
                demands.append(demand)
                model.addConstr(
                    gp.quicksum(q[i, r] for i in arcs[(r, product_index)])
                    + u[r]
                    >= demand
                )
            for i in depots:
                variables = [q[i, r] for r in regions if (i, r) in q]
                model.addConstr(gp.quicksum(variables) <= fixed_x[i][product_index])
            model.addConstr(
                gp.quicksum(u[r] for r in regions) - e
                <= (1.0 - instance.service_level[product_index]) * sum(demands)
            )
            transportation = gp.quicksum(
                instance.transport_cost[i][r][product_index] * variable
                for (i, r), variable in q.items()
            )
            shortage = gp.quicksum(
                instance.shortage_penalty[r][product_index] * u[r]
                for r in regions
            )
            service = instance.service_penalty[product_index] * e
            cost = transportation + shortage + service
            blocks[shocked_regions] = {
                "q": q,
                "u": u,
                "e": e,
                "transportation": transportation,
                "shortage": shortage,
                "service": service,
                "cost": cost,
            }
    model.setObjective(
        gp.quicksum(block["cost"] for block in blocks.values()), GRB.MINIMIZE
    )
    model.optimize()
    primary_status = int(model.Status)
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"E8 product recourse failed: status={model.Status}")
    optimum = {
        shocked_regions: block["cost"].getValue()
        for shocked_regions, block in blocks.items()
    }
    for shocked_regions, block in blocks.items():
        model.addConstr(
            block["cost"] <= optimum[shocked_regions] + optimality_tolerance
        )
    model.setObjective(
        gp.quicksum(
            block["u"][r] * block["u"][r]
            for block in blocks.values()
            for r in regions
        ),
        GRB.MINIMIZE,
    )
    model.optimize()
    tiebreak_status = int(model.Status)
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"E8 reporting tie-break failed: status={model.Status}")
    results = []
    for shocked_regions, block in blocks.items():
        shipment_by_region = []
        source_count_by_region = []
        used_depots_by_region = []
        for r in regions:
            used = tuple(
                instance.depot_ids[i]
                for i in arcs[(r, product_index)]
                if block["q"][i, r].X > shipment_usage_tolerance
            )
            used_depots_by_region.append(used)
            source_count_by_region.append(len(used))
            shipment_by_region.append(
                sum(block["q"][i, r].X for i in arcs[(r, product_index)])
            )
        results.append(
            ProductBlockResult(
                product_index=product_index,
                shocked_regions=tuple(shocked_regions),
                recourse_cost=float(optimum[shocked_regions]),
                transportation_cost=float(block["transportation"].getValue()),
                shortage_penalty_cost=float(block["shortage"].getValue()),
                service_violation_penalty_cost=float(block["service"].getValue()),
                shortage_by_region=tuple(block["u"][r].X for r in regions),
                service_violation_quantity=float(block["e"].X),
                shipment_by_region=tuple(shipment_by_region),
                source_count_by_region=tuple(source_count_by_region),
                used_depot_ids_by_region=tuple(used_depots_by_region),
            )
        )
    diagnostics = {
        "primary_status": primary_status,
        "tiebreak_status": tiebreak_status,
        "runtime_seconds": float(model.Runtime),
        "variable_count": int(model.NumVars),
        "constraint_count": int(model.NumConstrs),
        "threads": threads,
        "model_disposed": True,
    }
    model.dispose()
    return results, diagnostics


def _block_index(
    blocks: Iterable[ProductBlockResult],
) -> dict[tuple[int, tuple[int, ...]], ProductBlockResult]:
    output: dict[tuple[int, tuple[int, ...]], ProductBlockResult] = {}
    for block in blocks:
        key = (block.product_index, block.shocked_regions)
        if key in output:
            raise ValueError(f"duplicate product block: {key}")
        output[key] = block
    return output


def compose_scenario_results(
    instance: InventoryInstance,
    gamma: int,
    blocks: Iterable[ProductBlockResult],
) -> list[dict[str, Any]]:
    block_index = _block_index(blocks)
    scenarios = enumerate_scenario_components(instance, gamma)
    results = []
    for scenario_index, scenario in enumerate(scenarios):
        by_product = tuple(
            tuple(r for r, product in scenario if product == j)
            for j in range(instance.num_products)
        )
        selected = [block_index[(j, by_product[j])] for j in range(instance.num_products)]
        shortage_by_product = [sum(block.shortage_by_region) for block in selected]
        shortage_by_region = [
            sum(block.shortage_by_region[r] for block in selected)
            for r in range(instance.num_regions)
        ]
        demand_by_region = [
            sum(
                instance.base_demand[r][j]
                + (instance.demand_deviation[r][j] if (r, j) in scenario else 0.0)
                for j in range(instance.num_products)
            )
            for r in range(instance.num_regions)
        ]
        region_fill_rates = [
            1.0 if demand == 0.0 else 1.0 - shortage_by_region[r] / demand
            for r, demand in enumerate(demand_by_region)
        ]
        worst_region = min(
            range(instance.num_regions), key=lambda r: (region_fill_rates[r], r)
        )
        total_shortage = sum(shortage_by_product)
        total_demand = sum(demand_by_region)
        multi_source_pair_count = sum(
            count >= 2 for block in selected for count in block.source_count_by_region
        )
        multi_source_shipment_quantity = sum(
            shipment
            for block in selected
            for shipment, count in zip(
                block.shipment_by_region, block.source_count_by_region, strict=True
            )
            if count >= 2
        )
        transportation = sum(block.transportation_cost for block in selected)
        shortage_penalty = sum(block.shortage_penalty_cost for block in selected)
        service_penalty = sum(
            block.service_violation_penalty_cost for block in selected
        )
        recourse = sum(block.recourse_cost for block in selected)
        results.append(
            {
                "scenario_id": f"S{scenario_index:04d}",
                "shock_set": [
                    [instance.region_ids[r], instance.product_ids[j]] for r, j in scenario
                ],
                "recourse_cost": recourse,
                "transportation_cost": transportation,
                "shortage_penalty_cost": shortage_penalty,
                "service_violation_penalty_cost": service_penalty,
                "cost_component_residual": recourse
                - transportation
                - shortage_penalty
                - service_penalty,
                "total_shortage": total_shortage,
                "shortage_by_product": {
                    instance.product_ids[j]: shortage_by_product[j]
                    for j in range(instance.num_products)
                },
                "demand_weighted_fill_rate": (
                    1.0 if total_demand == 0.0 else 1.0 - total_shortage / total_demand
                ),
                "worst_region_fill_rate": region_fill_rates[worst_region],
                "worst_region_id": instance.region_ids[worst_region],
                "service_violation_quantity": sum(
                    block.service_violation_quantity for block in selected
                ),
                "actual_multi_source_region_product_count": int(
                    multi_source_pair_count
                ),
                "actual_multi_source_shipment_quantity": multi_source_shipment_quantity,
                "actual_source_count": sum(
                    count
                    for block in selected
                    for count in block.source_count_by_region
                ),
            }
        )
    return results


def _extreme(
    rows: list[dict[str, Any]], field: str, *, maximum: bool
) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize an empty scenario set")
    target = (max if maximum else min)(float(row[field]) for row in rows)
    tolerance = 1e-10 * max(1.0, abs(target))
    tied = [row for row in rows if abs(float(row[field]) - target) <= tolerance]
    return {
        "metric": field,
        "value": target,
        "representative_scenario_id": tied[0]["scenario_id"],
        "representative_shock_set": tied[0]["shock_set"],
        "tie_count": len(tied),
    }


def summarize_scenarios(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [row.get("scenario_id") for row in rows]
    expected = [f"S{index:04d}" for index in range(len(rows))]
    if ids != expected or not ids or ids[0] != "S0000":
        raise ValueError("scenario rows are incomplete or out of canonical order")
    required = {
        "recourse_cost",
        "transportation_cost",
        "shortage_penalty_cost",
        "service_violation_penalty_cost",
        "total_shortage",
        "demand_weighted_fill_rate",
        "worst_region_fill_rate",
        "service_violation_quantity",
    }
    if any(not required <= row.keys() for row in rows):
        raise ValueError("scenario row is missing a publishable metric")
    return {
        "scenario_count": len(rows),
        "nominal": rows[0],
        "worst_economic_cost": _extreme(rows, "recourse_cost", maximum=True),
        "maximum_total_shortage": _extreme(rows, "total_shortage", maximum=True),
        "worst_region_service": _extreme(
            rows, "worst_region_fill_rate", maximum=False
        ),
        "maximum_service_violation": _extreme(
            rows, "service_violation_quantity", maximum=True
        ),
        "maximum_shortage_penalty_cost": _extreme(
            rows, "shortage_penalty_cost", maximum=True
        ),
    }


def checkpoint_payload(
    identity: dict[str, Any],
    product_index: int,
    blocks: list[ProductBlockResult],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema": "e8_product_checkpoint_v1",
        "identity": identity,
        "product_index": product_index,
        "solver_status": "OPTIMAL",
        "blocks": [block.to_dict() for block in blocks],
        "diagnostics": diagnostics,
    }
    return {**payload, "payload_sha256": canonical_hash(payload)}


def validate_checkpoint(
    value: dict[str, Any],
    expected_identity: dict[str, Any],
    expected_product_index: int,
    expected_block_count: int,
) -> list[ProductBlockResult]:
    recorded_hash = value.get("payload_sha256")
    payload = {key: item for key, item in value.items() if key != "payload_sha256"}
    if recorded_hash != canonical_hash(payload):
        raise ValueError("checkpoint payload hash mismatch")
    if value.get("schema") != "e8_product_checkpoint_v1":
        raise ValueError("checkpoint schema mismatch")
    if value.get("identity") != expected_identity:
        raise ValueError("checkpoint identity mismatch")
    if value.get("product_index") != expected_product_index:
        raise ValueError("checkpoint product mismatch")
    if value.get("solver_status") != "OPTIMAL":
        raise ValueError("checkpoint does not contain an optimal solve")
    blocks = [ProductBlockResult.from_dict(item) for item in value.get("blocks", [])]
    if len(blocks) != expected_block_count:
        raise ValueError("checkpoint block count mismatch")
    keys = {(block.product_index, block.shocked_regions) for block in blocks}
    if len(keys) != len(blocks) or any(
        block.product_index != expected_product_index for block in blocks
    ):
        raise ValueError("checkpoint block identities are invalid")
    return blocks


def validate_mode_order(
    summaries: dict[str, dict[str, Any]], tolerance: float
) -> None:
    if set(summaries) != set(MODES):
        raise ValueError("all three fulfillment modes are required")
    costs = {
        mode: float(summaries[mode]["worst_economic_cost"]["value"])
        for mode in MODES
    }
    if costs["full"] > costs["k2"] + tolerance or costs["k2"] > costs["k1"] + tolerance:
        raise ValueError("fixed-policy recourse monotonicity Full <= k2 <= k1 failed")


def paired_reporting_rows(
    rows_by_mode: dict[str, list[dict[str, Any]]],
    summaries: dict[str, dict[str, Any]],
    tolerance: float,
) -> list[dict[str, Any]]:
    """Build nominal and Full-worst-cost paired rows from complete mode results."""
    if set(rows_by_mode) != set(MODES) or set(summaries) != set(MODES):
        raise ValueError("all three fulfillment modes are required for reporting")
    validate_mode_order(summaries, tolerance)
    reference = rows_by_mode["full"]
    if len(reference) != FROZEN_SCENARIO_COUNT:
        raise ValueError("reporting requires the complete frozen scenario set")
    reference_keys = [
        (row.get("scenario_id"), row.get("shock_set")) for row in reference
    ]
    for mode in MODES:
        rows = rows_by_mode[mode]
        if len(rows) != FROZEN_SCENARIO_COUNT:
            raise ValueError("reporting requires the complete frozen scenario set")
        if [(row.get("scenario_id"), row.get("shock_set")) for row in rows] != reference_keys:
            raise ValueError("fulfillment modes do not use identical scenarios")
        if summarize_scenarios(rows) != summaries[mode]:
            raise ValueError("scenario rows do not reproduce the stored summary")
    full_worst_id = summaries["full"]["worst_economic_cost"][
        "representative_scenario_id"
    ]
    by_mode_and_id = {
        mode: {row["scenario_id"]: row for row in rows_by_mode[mode]}
        for mode in MODES
    }
    output = []
    for basis, scenario_id in (
        ("nominal_demand", "S0000"),
        ("full_mode_worst_economic_cost", full_worst_id),
    ):
        for mode in MODES:
            output.append(
                {
                    "evaluation_basis": basis,
                    "mode": mode,
                    **by_mode_and_id[mode][scenario_id],
                }
            )
    return output
