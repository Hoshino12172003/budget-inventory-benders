from __future__ import annotations

from scripts.summarize_renault_four_method_results import (
    audit_recovered_results,
    build_table_rows,
)


def test_recovered_e1b_artifacts_are_complete_and_exact_certified() -> None:
    audit = audit_recovered_results()
    assert audit["status"] == "PASS"
    assert audit["file_count"] == 88
    assert audit["run_count"] == 16
    assert audit["exact_certified_count"] == 16
    assert audit["solver_version"] == "13.0.2"
    assert audit["sensitive_match_count"] == 0


def test_four_method_table_is_complete_and_objective_consistent() -> None:
    rows = build_table_rows(audit_recovered_results())
    assert len(rows) == 8
    assert all(row["Objective consistency"] == "PASS_ALL_FOUR" for row in rows)
    assert all("NOT_VERIFIABLE" not in str(value) for row in rows for value in row.values())
    assert all(str(row["Pure certification"]).startswith("CERTIFIED_") for row in rows)
    assert all(str(row["Aggregate+Structured certification"]).startswith("CERTIFIED_") for row in rows)
