from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/summarize_renault8_prb_v2_paired_v1.py"
SPEC = importlib.util.spec_from_file_location("renault8_prb_v2_archive", SCRIPT)
assert SPEC and SPEC.loader
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


def test_archive_has_all_pairs_and_preserves_certification_classes() -> None:
    summary = archive.build()
    assert summary["pairs"] == 8
    assert summary["conditions"] == 16
    assert summary["performance"]["v2_win_count"] + summary["performance"][
        "basic_win_count"
    ] == 8
    certification = {row["method"]: row for row in summary["certification"]}
    assert certification["basic"]["strict_original_count"] == 7
    assert certification["v2"]["strict_original_count"] == 7
    assert certification["basic"]["independently_numerically_validated_count"] == 1
    assert certification["v2"]["independently_numerically_validated_count"] == 1


def test_paired_table_has_unique_cases_and_objective_matches() -> None:
    path = archive.ANALYSIS_ROOT / "paired_results_8.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8
    assert len({row["case"] for row in rows}) == 8
    assert all(float(row["paired_objective_absolute_difference"]) <= 1e-4 for row in rows)


def test_provenance_hashes_all_source_results() -> None:
    manifest = json.loads(
        (archive.ANALYSIS_ROOT / "provenance_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["optimization_calls_during_analysis"] == 0
    assert len(manifest["input_sources"]) == 16
    for record in manifest["input_sources"]:
        path = ROOT / record["result_path"]
        assert archive.sha256(path) == record["result_sha256"]
