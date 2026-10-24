from __future__ import annotations

from scripts.build_large_scale_iteration_paper_outputs import (
    build_aggregate_table,
    build_pure_table,
    certified_pair,
)


def result(iterations: int, objective: float = 100.0, certified: bool = True) -> dict:
    return {
        "status": "OPTIMAL",
        "exact_certification": certified,
        "objective": objective,
        "iterations": iterations,
    }


def synthetic_results() -> dict:
    values = {}
    for scale in ("L10", "XL10", "XXL10"):
        for seed in range(20260921, 20260931):
            values[(scale, seed, "pure_benders")] = result(10)
            values[(scale, seed, "aggregate_benders_structured_oracle")] = result(8)
            values[(scale, seed, "prb_benders")] = result(5)
    return values


def test_certified_pair_requires_certification_and_objective_identity() -> None:
    assert certified_pair(result(10), result(5)) is True
    assert certified_pair(result(10, certified=False), result(5)) is False
    assert certified_pair(result(10, objective=100.001), result(5)) is False


def test_pure_paper_table_contains_iterations_only() -> None:
    rows = build_pure_table(synthetic_results())
    assert [row["paired_n"] for row in rows] == [10, 10, 10, 30]
    assert rows[-1]["median_prb_over_pure_iteration_ratio"] == 0.5
    assert rows[-1]["prb_fewer_iterations_count"] == 30
    forbidden = ("runtime", "speedup", "t_core", "oracle", "master")
    assert not any(token in column.lower() for column in rows[0] for token in forbidden)


def test_aggregate_table_is_an_independent_pairing() -> None:
    values = synthetic_results()
    values[("L10", 20260921, "pure_benders")]["status"] = "ERROR"
    pure_rows = build_pure_table(values)
    aggregate_rows = build_aggregate_table(values)
    assert pure_rows[0]["paired_n"] == 9
    assert aggregate_rows[0]["paired_n"] == 10
    assert aggregate_rows[-1]["median_prb_over_aggregate_iteration_ratio"] == 0.625
