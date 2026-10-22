from scripts.build_xxl10_four_method_final_archive import METHODS, OUTPUT, build, read_json


def test_archive_has_40_records_and_expected_certification_counts():
    audit = build()
    assert audit["optimization_calls"] == 0
    assert audit["record_count"] == 40
    assert audit["counts"]["Direct"] == {"executed": 10, "exact_certified": 3}
    for method in METHODS[1:]:
        assert audit["counts"][method] == {"executed": 10, "exact_certified": 10}


def test_direct_edge_cases_remain_noncertified_and_uninvented():
    import csv

    with (OUTPUT / "xxl10_four_method_records.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    seed22 = next(row for row in rows if row["method"] == "Direct" and row["seed"] == "20260922")
    seed27 = next(row for row in rows if row["method"] == "Direct" and row["seed"] == "20260927")
    assert seed22["classification"] == "TIME_LIMIT_NO_INCUMBENT"
    assert seed22["objective"] == seed22["lower_bound"] == seed22["final_gap"] == ""
    assert seed27["classification"] == "MONITOR_HARD_TIME_LIMIT"
    assert seed27["solver_status"] == seed27["objective"] == seed27["final_gap"] == ""
    assert seed27["worker_return_code"] == "15"


def test_integrity_audit_keeps_direct_core_hash_frozen():
    audit = read_json(OUTPUT / "xxl10_integrity_audit.json")
    assert audit["direct_core_runner_sha256"] == "fef8019f9aa9be1d2942a5d3aad363c2c3c28929e52cc02b359d1626a1880edd"
    assert audit["all_40_instance_identities_match"] is True
    assert audit["all_available_provenance_hashes_match"] is True


def test_paper_outputs_exist_and_are_nonempty():
    for name in (
        "xxl10_four_method_results.xlsx",
        "xxl10_certified_core_time_by_seed.png",
        "xxl10_certified_core_time_by_seed.pdf",
        "xxl10_four_method_paper_table.md",
    ):
        path = OUTPUT / name
        assert path.is_file() and path.stat().st_size > 0
