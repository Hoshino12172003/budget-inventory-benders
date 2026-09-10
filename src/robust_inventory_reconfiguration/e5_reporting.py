from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalAdjustment:
    a_plus: list[list[float]]
    a_minus: list[list[float]]
    total_a_plus: float
    total_a_minus: float
    total_adjustment: float
    reconfiguration_index: float
    changed_pair_count: int


def canonical_adjustment(
    x: list[list[float]],
    x0: list[list[float]],
    *,
    material_tolerance: float = 1e-6,
) -> CanonicalAdjustment:
    if len(x) != len(x0) or any(len(row) != len(x0[i]) for i, row in enumerate(x)):
        raise ValueError("x and x0 dimensions differ")
    denominator = sum(map(sum, x0))
    if denominator <= 0:
        raise ValueError("canonical RI requires positive total x0")
    plus = []
    minus = []
    changed = 0
    for current_row, baseline_row in zip(x, x0):
        plus_row = []
        minus_row = []
        for current, baseline in zip(current_row, baseline_row):
            difference = float(current) - float(baseline)
            plus_row.append(max(difference, 0.0))
            minus_row.append(max(-difference, 0.0))
            changed += abs(difference) > material_tolerance
        plus.append(plus_row)
        minus.append(minus_row)
    total_plus = sum(map(sum, plus))
    total_minus = sum(map(sum, minus))
    total = total_plus + total_minus
    return CanonicalAdjustment(
        plus,
        minus,
        total_plus,
        total_minus,
        total,
        total / denominator,
        changed,
    )


def maximum_adjustment_difference(
    canonical: CanonicalAdjustment,
    solver_a_plus: list[list[float]],
    solver_a_minus: list[list[float]],
) -> float:
    return max(
        difference
        for i in range(len(canonical.a_plus))
        for j in range(len(canonical.a_plus[i]))
        for difference in (
            abs(canonical.a_plus[i][j] - solver_a_plus[i][j]),
            abs(canonical.a_minus[i][j] - solver_a_minus[i][j]),
        )
    )
