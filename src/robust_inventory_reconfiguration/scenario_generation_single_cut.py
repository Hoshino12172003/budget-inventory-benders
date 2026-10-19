from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Any, Callable, Iterable


Pattern = tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class FeasibleRecourseUpperBound:
    value: float
    shipment: tuple[tuple[tuple[float, ...], ...], ...]
    shortage: tuple[tuple[float, ...], ...]
    service_violation: tuple[float, ...]


@dataclass(frozen=True)
class ScenarioEvaluation:
    value: float
    payload: Any = None


@dataclass(frozen=True)
class AffineScenarioUpperBound:
    base_value: float
    shock_increment: dict[tuple[int, int], float]

    def value(self, pattern: Pattern) -> float:
        return self.base_value + sum(self.shock_increment[pair] for pair in pattern)


@dataclass(frozen=True)
class ExactSeparationResult:
    pattern: Pattern
    evaluation: ScenarioEvaluation
    total_scenarios: int
    lp_solves: int
    safely_pruned_scenarios: int
    branch_pruned_scenarios: int
    leaf_pruned_scenarios: int


def enumerate_patterns(num_regions: int, num_products: int, gamma: int) -> tuple[Pattern, ...]:
    components = tuple(
        (region, product)
        for region in range(num_regions)
        for product in range(num_products)
    )
    if gamma < 0 or gamma > len(components):
        raise ValueError("gamma is outside the global cardinality uncertainty set")
    return tuple(
        pattern
        for size in range(gamma + 1)
        for pattern in itertools.combinations(components, size)
    )


def _validate(instance: Any, x: list[list[float]]) -> None:
    if len(x) != instance.num_depots or any(
        len(row) != instance.num_products for row in x
    ):
        raise ValueError("first-stage inventory dimensions do not match the instance")
    nonnegative = (
        value
        for values in (
            instance.base_demand,
            instance.demand_deviation,
            instance.shortage_penalty,
        )
        for row in values
        for value in row
    )
    if any(float(value) < 0.0 for value in nonnegative):
        raise ValueError("SG-BD bounds require nonnegative demand, deviation, and penalties")
    if any(float(value) < 0.0 for value in instance.service_penalty):
        raise ValueError("SG-BD bounds require nonnegative service penalties")
    if any(not 0.0 <= float(value) <= 1.0 for value in instance.service_level):
        raise ValueError("SG-BD bounds require service levels in [0, 1]")


def scenario_demand(instance: Any, pattern: Iterable[tuple[int, int]]) -> list[list[float]]:
    active = frozenset(pattern)
    return [
        [
            float(instance.base_demand[r][j])
            + (float(instance.demand_deviation[r][j]) if (r, j) in active else 0.0)
            for j in range(instance.num_products)
        ]
        for r in range(instance.num_regions)
    ]


def no_shipment_upper_bound(instance: Any, pattern: Pattern) -> float:
    demand = scenario_demand(instance, pattern)
    return sum(
        (
            float(instance.shortage_penalty[r][j])
            + float(instance.service_penalty[j]) * float(instance.service_level[j])
        )
        * demand[r][j]
        for r in range(instance.num_regions)
        for j in range(instance.num_products)
    )


def _edge_orders(instance: Any) -> tuple[tuple[tuple[tuple[float, int, int], ...], ...], ...]:
    service_orders = []
    ordinary_orders = []
    for j in range(instance.num_products):
        service_orders.append(tuple(sorted(
            (
                float(instance.shortage_penalty[r][j])
                + float(instance.service_penalty[j])
                - float(instance.transport_cost[i][r][j]),
                i,
                r,
            )
            for i in range(instance.num_depots)
            for r in range(instance.num_regions)
        )))
        ordinary_orders.append(tuple(sorted(
            (
                float(instance.shortage_penalty[r][j])
                - float(instance.transport_cost[i][r][j]),
                i,
                r,
            )
            for i in range(instance.num_depots)
            for r in range(instance.num_regions)
        )))
    return tuple(service_orders), tuple(ordinary_orders)


def feasible_greedy_upper_bound(
    instance: Any,
    x: list[list[float]],
    pattern: Pattern,
) -> FeasibleRecourseUpperBound:
    _validate(instance, x)
    I, R, J = instance.num_depots, instance.num_regions, instance.num_products
    demand = scenario_demand(instance, pattern)
    shipment = [[[0.0 for _ in range(J)] for _ in range(R)] for _ in range(I)]
    remaining_supply = [[max(0.0, float(x[i][j])) for j in range(J)] for i in range(I)]
    remaining_demand = [[float(demand[r][j]) for j in range(J)] for r in range(R)]
    service_orders, ordinary_orders = _edge_orders(instance)

    for j in range(J):
        total_demand = sum(demand[r][j] for r in range(R))
        service_shipping_target = float(instance.service_level[j]) * total_demand
        shipped_for_service = 0.0
        for saving, i, r in reversed(service_orders[j]):
            if saving <= 0.0 or shipped_for_service >= service_shipping_target:
                break
            quantity = min(
                remaining_supply[i][j],
                remaining_demand[r][j],
                service_shipping_target - shipped_for_service,
            )
            shipment[i][r][j] += quantity
            remaining_supply[i][j] -= quantity
            remaining_demand[r][j] -= quantity
            shipped_for_service += quantity

        for saving, i, r in reversed(ordinary_orders[j]):
            if saving <= 0.0:
                break
            quantity = min(remaining_supply[i][j], remaining_demand[r][j])
            shipment[i][r][j] += quantity
            remaining_supply[i][j] -= quantity
            remaining_demand[r][j] -= quantity

    shortage = tuple(tuple(remaining_demand[r][j] for j in range(J)) for r in range(R))
    service_violation = tuple(
        max(
            0.0,
            sum(shortage[r][j] for r in range(R))
            - (1.0 - float(instance.service_level[j]))
            * sum(demand[r][j] for r in range(R)),
        )
        for j in range(J)
    )
    value = sum(
        float(instance.transport_cost[i][r][j]) * shipment[i][r][j]
        for i in range(I)
        for r in range(R)
        for j in range(J)
    )
    value += sum(
        float(instance.shortage_penalty[r][j]) * shortage[r][j]
        for r in range(R)
        for j in range(J)
    )
    value += sum(
        float(instance.service_penalty[j]) * service_violation[j] for j in range(J)
    )
    return FeasibleRecourseUpperBound(
        value,
        tuple(tuple(tuple(row) for row in depot) for depot in shipment),
        shortage,
        service_violation,
    )


def build_affine_scenario_upper_bound(
    instance: Any,
    x: list[list[float]],
) -> AffineScenarioUpperBound:
    """Bound every shocked scenario using one feasible baseline shipment plan.

    Keeping the baseline shipment fixed remains feasible after nonnegative demand
    shocks.  Shortage cost rises exactly by p*delta, while the positive-part
    service penalty can rise by at most phi*SL*delta.
    """
    baseline = feasible_greedy_upper_bound(instance, x, ())
    increments = {
        (r, j): float(instance.demand_deviation[r][j])
        * (
            float(instance.shortage_penalty[r][j])
            + float(instance.service_penalty[j]) * float(instance.service_level[j])
        )
        for r in range(instance.num_regions)
        for j in range(instance.num_products)
    }
    return AffineScenarioUpperBound(baseline.value, increments)


def _components_by_bound_weight(
    bound: AffineScenarioUpperBound,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted(
            bound.shock_increment,
            key=lambda pair: (bound.shock_increment[pair], pair),
            reverse=True,
        )
    )


def _branch_bound(
    bound: AffineScenarioUpperBound,
    components: tuple[tuple[int, int], ...],
    index: int,
    selected: Pattern,
    gamma: int,
) -> float:
    base = bound.value(selected)
    remaining_slots = gamma - len(selected)
    if remaining_slots <= 0:
        return base
    contributions = (
        bound.shock_increment[pair]
        for pair in components[index:]
        if bound.shock_increment[pair] > 0.0
    )
    return base + sum(itertools.islice(contributions, remaining_slots))


def exact_separation(
    instance: Any,
    x: list[list[float]],
    gamma: int,
    evaluator: Callable[[Pattern], ScenarioEvaluation],
    *,
    candidate_patterns: Iterable[Pattern] = ((),),
    tolerance: float = 1e-9,
) -> ExactSeparationResult:
    _validate(instance, x)
    affine_bound = build_affine_scenario_upper_bound(instance, x)
    components = _components_by_bound_weight(affine_bound)
    total = sum(math.comb(len(components), size) for size in range(gamma + 1))
    cache: dict[Pattern, ScenarioEvaluation] = {}
    best_pattern: Pattern | None = None
    best_evaluation: ScenarioEvaluation | None = None

    def evaluate(pattern: Pattern) -> None:
        nonlocal best_pattern, best_evaluation
        canonical = tuple(sorted(pattern))
        if len(canonical) > gamma or len(set(canonical)) != len(canonical):
            raise ValueError("candidate pattern is outside the uncertainty set")
        if canonical not in cache:
            cache[canonical] = evaluator(canonical)
        if best_evaluation is None or cache[canonical].value > best_evaluation.value + tolerance:
            best_pattern, best_evaluation = canonical, cache[canonical]

    for pattern in candidate_patterns:
        evaluate(pattern)

    branch_pruned: set[Pattern] = set()
    leaf_pruned: set[Pattern] = set()

    def visit(index: int, selected: Pattern) -> None:
        assert best_evaluation is not None
        remaining = len(components) - index
        if _branch_bound(affine_bound, components, index, selected, gamma) <= best_evaluation.value - tolerance:
            for size in range(min(remaining, gamma - len(selected)) + 1):
                for suffix in itertools.combinations(components[index:], size):
                    pattern = tuple(sorted((*selected, *suffix)))
                    if pattern not in cache:
                        branch_pruned.add(pattern)
            return
        if index == len(components) or len(selected) == gamma:
            canonical = tuple(sorted(selected))
            if canonical in cache:
                return
            if affine_bound.value(canonical) <= best_evaluation.value - tolerance:
                leaf_pruned.add(canonical)
                return
            evaluate(canonical)
            return
        component = components[index]
        visit(index + 1, (*selected, component))
        visit(index + 1, selected)

    visit(0, ())
    if best_pattern is None or best_evaluation is None:
        raise RuntimeError("SG-BD exact separation evaluated no scenario")
    safely_pruned = len(branch_pruned | leaf_pruned)
    if len(cache) + safely_pruned != total:
        raise RuntimeError("SG-BD scenario accounting is incomplete")
    return ExactSeparationResult(
        best_pattern,
        best_evaluation,
        total,
        len(cache),
        safely_pruned,
        len(branch_pruned),
        len(leaf_pruned),
    )


def static_pruning_screen(
    instance: Any,
    x: list[list[float]],
    gamma: int,
    certified_incumbent: float,
    *,
    tolerance: float = 1e-9,
) -> dict[str, int | float]:
    _validate(instance, x)
    patterns = enumerate_patterns(instance.num_regions, instance.num_products, gamma)
    affine_bound = build_affine_scenario_upper_bound(instance, x)
    leaf_prunable = sum(
        affine_bound.value(pattern) <= certified_incumbent - tolerance
        for pattern in patterns
    )
    return {
        "total_scenarios": len(patterns),
        "leaf_upper_bound_prunable": leaf_prunable,
        "unresolved_requiring_exact_lp_at_most": len(patterns) - leaf_prunable,
        "leaf_pruning_fraction": leaf_prunable / len(patterns),
    }
