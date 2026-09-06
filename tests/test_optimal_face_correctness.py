from dataclasses import replace

from robust_inventory_reconfiguration.optimal_face_correctness import (
    EXACT_SOLUTION_IDENTITY,
    FAIL,
    OPTIMAL_FACE_EQUIVALENT,
    ComparisonEvidence,
    audit_first_stage_feasibility,
    classify_solution_comparison,
)


def valid_evidence() -> ComparisonEvidence:
    return ComparisonEvidence(
        exact_certified=True,
        prb_certified=True,
        exact_feasible=True,
        prb_feasible=True,
        objective_difference=1e-8,
        objective_scale=100.0,
        first_stage_difference=1e-8,
        robust_recourse_difference=1e-8,
        y_identical=True,
        maximum_x_difference=1e-8,
        fill_rate_difference=1e-9,
        exact_on_optimal_face=True,
        prb_on_optimal_face=True,
    )


def test_unique_optimum_is_exact_solution_identity() -> None:
    assert classify_solution_comparison(valid_evidence()) == EXACT_SOLUTION_IDENTITY


def test_multiple_optimum_with_different_x_is_optimal_face_equivalent() -> None:
    evidence = replace(valid_evidence(), maximum_x_difference=100.0)
    assert classify_solution_comparison(evidence) == OPTIMAL_FACE_EQUIVALENT


def test_objective_difference_fails() -> None:
    assert classify_solution_comparison(
        replace(valid_evidence(), objective_difference=1.0)
    ) == FAIL


def test_robust_recourse_difference_fails() -> None:
    assert classify_solution_comparison(
        replace(valid_evidence(), robust_recourse_difference=1.0)
    ) == FAIL


def test_fill_rate_difference_fails() -> None:
    assert classify_solution_comparison(
        replace(valid_evidence(), fill_rate_difference=1e-3)
    ) == FAIL


def test_infeasible_solution_fails() -> None:
    assert classify_solution_comparison(
        replace(valid_evidence(), prb_feasible=False)
    ) == FAIL


def test_uncertified_solution_fails() -> None:
    assert classify_solution_comparison(
        replace(valid_evidence(), exact_certified=False)
    ) == FAIL


def test_different_activation_vector_fails() -> None:
    assert classify_solution_comparison(
        replace(valid_evidence(), y_identical=False)
    ) == FAIL


def test_large_x_difference_does_not_fail_when_both_are_on_optimal_face() -> None:
    evidence = replace(valid_evidence(), maximum_x_difference=1_000.0)
    assert classify_solution_comparison(evidence) != FAIL


def test_first_stage_feasibility_checks_inventory_bounds_and_balance(tiny_instance) -> None:
    x0 = [[2.0, 1.0]]
    feasible = audit_first_stage_feasibility(
        tiny_instance,
        x0,
        [1],
        [[3.0, 2.0]],
        [[1.0, 1.0]],
        [[0.0, 0.0]],
        0.05,
        20.0,
    )
    infeasible = audit_first_stage_feasibility(
        tiny_instance,
        x0,
        [0],
        [[3.0, 2.0]],
        [[1.0, 1.0]],
        [[0.0, 0.0]],
        0.05,
        20.0,
    )
    assert feasible.feasible
    assert not infeasible.feasible
