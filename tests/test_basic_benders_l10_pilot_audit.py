from scripts.audit_basic_benders_l10_pilot import build_audit


def test_basic_l10_pilot_is_complete_exact_and_single_scope() -> None:
    audit, hashes, comparison = build_audit()
    assert audit["status"] == "PASS_EXACT_CERTIFIED_DEVELOPMENT_PILOT"
    assert audit["condition_id"] == "BASIC_L10_S20260921"
    assert audit["attempt"] == "attempt-001"
    assert audit["optimization_runs_executed"] == 1
    assert audit["other_conditions_executed"] == 0
    assert all(audit["checks"].values())
    assert len(hashes) == 20
    assert comparison["basic_exact_certification"] is True
    assert comparison["prb_exact_certification"] is True


def test_basic_l10_iteration_evidence_is_persisted() -> None:
    audit, _, _ = build_audit()
    assert audit["trajectory"]["iterations"] == 8
    assert audit["trajectory"]["oracle_calls"] == 10
    assert audit["trajectory"]["scenarios_per_call"] == 41617
    assert {"lower_bound", "upper_bound", "relative_gap", "cumulative_time_seconds", "scenarios_checked", "oracle_trace_seconds", "cuts_added"} <= set(audit["trajectory"]["persisted_fields"])
