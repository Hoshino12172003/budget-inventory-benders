from scripts.summarize_direct_scaling_l10_results import summarize


def test_all_ten_l10_results_are_reported_from_certified_archives() -> None:
    audit, rows = summarize()
    assert audit["status"] == "COMPLETE_EXACT_CERTIFIED"
    assert audit["counts"] == {
        "authorized": 10,
        "attempted": 10,
        "exact_certified": 10,
        "resource_stop": 0,
        "unattempted": 0,
    }
    assert len(rows) == 10
    assert all(row["Direct status"] == "OPTIMAL" for row in rows)
    assert all(row["Direct exact certification"] is True for row in rows)
    assert all(row["Four-method objective consistency"] == "PASS" for row in rows)
    assert audit["checks"]["historical_first_resource_stop_preserved"] is True
