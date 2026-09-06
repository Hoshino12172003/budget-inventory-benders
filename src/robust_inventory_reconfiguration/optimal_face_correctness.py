from __future__ import annotations

from dataclasses import dataclass

from .instance import InventoryInstance
from .reconfiguration_model import first_stage_expenditure_value


EXACT_SOLUTION_IDENTITY = "EXACT_SOLUTION_IDENTITY"
OPTIMAL_FACE_EQUIVALENT = "OPTIMAL_FACE_EQUIVALENT"
FAIL = "FAIL"


@dataclass(frozen=True)
class ComparisonEvidence:
    exact_certified: bool
    prb_certified: bool
    exact_feasible: bool
    prb_feasible: bool
    objective_difference: float
    objective_scale: float
    first_stage_difference: float
    robust_recourse_difference: float
    y_identical: bool
    maximum_x_difference: float
    fill_rate_difference: float
    exact_on_optimal_face: bool
    prb_on_optimal_face: bool


@dataclass(frozen=True)
class CorrectnessTolerances:
    objective_absolute: float = 1e-4
    objective_relative: float = 1e-6
    first_stage_absolute: float = 1e-4
    robust_recourse_absolute: float = 1e-4
    x_absolute: float = 1e-5
    fill_rate_absolute: float = 1e-6


@dataclass(frozen=True)
class FirstStageFeasibility:
    feasible: bool
    first_stage_expenditure: float
    maximum_violation: float


def classify_solution_comparison(
    evidence: ComparisonEvidence,
    tolerances: CorrectnessTolerances = CorrectnessTolerances(),
) -> str:
    objective_tolerance = max(
        tolerances.objective_absolute,
        tolerances.objective_relative * evidence.objective_scale,
    )
    shared_requirements = (
        evidence.exact_certified
        and evidence.prb_certified
        and evidence.exact_feasible
        and evidence.prb_feasible
        and evidence.objective_difference <= objective_tolerance
        and evidence.first_stage_difference <= tolerances.first_stage_absolute
        and evidence.robust_recourse_difference <= tolerances.robust_recourse_absolute
        and evidence.y_identical
        and evidence.fill_rate_difference <= tolerances.fill_rate_absolute
    )
    if not shared_requirements:
        return FAIL
    if evidence.maximum_x_difference <= tolerances.x_absolute:
        return EXACT_SOLUTION_IDENTITY
    if evidence.exact_on_optimal_face and evidence.prb_on_optimal_face:
        return OPTIMAL_FACE_EQUIVALENT
    return FAIL


def audit_first_stage_feasibility(
    instance: InventoryInstance,
    x0: list[list[float]],
    y: list[int],
    x: list[list[float]],
    a_plus: list[list[float]],
    a_minus: list[list[float]],
    lambda_r: float,
    budget: float,
    *,
    tolerance: float = 1e-6,
) -> FirstStageFeasibility:
    violations = []
    violations.extend(max(0.0, -value) for row in x for value in row)
    violations.extend(max(0.0, -value) for row in a_plus for value in row)
    violations.extend(max(0.0, -value) for row in a_minus for value in row)
    violations.extend(min(abs(value), abs(value - 1)) if value not in (0, 1) else 0.0 for value in y)
    for i in range(instance.num_depots):
        load = sum(instance.product_volume[j] * x[i][j] for j in range(instance.num_products))
        violations.append(max(0.0, load - instance.capacity[i] * y[i]))
        for j in range(instance.num_products):
            violations.append(
                max(0.0, x[i][j] - instance.inventory_upper_bound[i][j] * y[i])
            )
            violations.append(
                abs(x[i][j] - x0[i][j] - a_plus[i][j] + a_minus[i][j])
            )
    first_stage = first_stage_expenditure_value(
        instance, y, x, a_plus, a_minus, lambda_r
    )
    violations.append(max(0.0, first_stage - budget))
    maximum = max(violations, default=0.0)
    return FirstStageFeasibility(maximum <= tolerance, first_stage, maximum)
