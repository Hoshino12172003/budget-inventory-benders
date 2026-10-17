from scripts.summarize_direct_scaling_l10_results import summarize


def test_l10_resource_stop_is_reported_without_fabricated_direct_results() -> None:
    audit, rows = summarize()
    assert audit["status"] == "BATCH_STOPPED_AFTER_RESOURCE_CAP"
    assert audit["counts"] == {
        "authorized": 10,
        "attempted": 1,
        "exact_certified": 0,
        "resource_stop": 1,
        "unattempted": 9,
    }
    assert audit["available_incumbent"] is None
    assert len(rows) == 10
    assert all(row["Direct objective"] == "NOT_AVAILABLE" for row in rows)
    assert all(row["Source three-method objective consistency"] == "PASS" for row in rows)
