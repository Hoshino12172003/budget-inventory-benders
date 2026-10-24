from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/configs/formal/e1b_standard_vs_prb_authorization.json"


def audit() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    references = manifest["prb_e1a_references"]
    missing = [case for case, ref in references.items() if not (ROOT / ref["result_path"]).is_file()]

    with (ROOT / "table_e1_empirical_performance_evidence.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    with (ROOT / "table_e1_output_evidence_registry.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        registry = list(csv.DictReader(stream))

    summary = json.loads(
        (ROOT / "artifacts/e1_empirical_performance_summary.json").read_text(encoding="utf-8")
    )
    required_docs = [
        "docs/e1a_e1b_e1c_evidence_reconciliation.md",
        "docs/e2_e7_reused_baseline_audit.md",
        "docs/paper_claims_evidence_matrix.md",
        "docs/pr11_scientific_blocker_resolution.md",
    ]
    checks = {
        "eight_manifest_references": len(references) == 8,
        "all_expected_sources_missing": len(missing) == 8,
        "eight_case_labels": len(rows) == 8,
        "all_prb_rows_historical": all(
            row["prb_evidence_level"] == "HISTORICAL_SUMMARY_ONLY" for row in rows
        ),
        "all_prb_sources_marked_missing": all(
            row["prb_source_status"] == "SOURCE_MISSING" for row in rows
        ),
        "development_crosscheck_7_pass_1_fail": (
            sum(row["development_crosscheck_status"] == "PASS" for row in rows) == 7
            and sum(row["development_crosscheck_status"] != "PASS" for row in rows) == 1
        ),
        "affected_outputs_registered": len(registry) >= 13,
        "historical_outputs_not_confirmatory": all(
            row["confirmatory_use"] == "false"
            for row in registry
            if row["evidence_level"] == "HISTORICAL_SUMMARY_ONLY"
        ),
        "summary_not_confirmatory": (
            summary["status"] == "E1_HISTORICAL_SUMMARY_SOURCE_INCOMPLETE"
            and summary["evidence_reconciliation"]["confirmatory_runtime_use_allowed"] is False
            and summary["evidence_reconciliation"]["confirmatory_certification_use_allowed"] is False
        ),
        "required_reconciliation_docs_present": all((ROOT / path).is_file() for path in required_docs),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "missing_cases": sorted(missing),
        "optimization_calls": 0,
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
