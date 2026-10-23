from scripts.audit_e1a_missing_source_reconciliation import audit


def test_missing_source_reconciliation_is_fail_closed() -> None:
    result = audit()
    assert result["status"] == "PASS"
    assert result["optimization_calls"] == 0
    assert len(result["missing_cases"]) == 8
    assert all(result["checks"].values())
