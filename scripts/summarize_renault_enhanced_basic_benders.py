from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
OUTPUT = ROOT / "artifacts/renault_eb_bd_comparison_template.csv"
EB_ROOT = ROOT / "experiments/results/renault_enhanced_basic_benders_development_v1/runs"


FIELDS = (
    "case",
    "method",
    "evidence_class",
    "status",
    "exact_certification",
    "pairing_eligible",
    "pairing_exclusion_reason",
    "objective",
    "lower_bound",
    "upper_bound",
    "final_gap",
    "algorithm_core_time_seconds",
    "independent_certification_seconds",
    "iterations",
    "cuts_added",
    "oracle_seconds",
    "peak_process_tree_memory_gib",
    "instance_hash",
    "x0_hash",
    "source",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _blank(case: str, method: str, source: Path) -> dict[str, Any]:
    return {
        field: (
            case if field == "case"
            else method if field == "method"
            else "PENDING_EB_BD_EXECUTION" if field in {"evidence_class", "status", "pairing_exclusion_reason"}
            else False if field == "pairing_eligible"
            else str(source.relative_to(ROOT)) if field == "source"
            else None
        )
        for field in FIELDS
    }


def build_rows() -> list[dict[str, Any]]:
    empirical = {
        row["case"]: row for row in read_csv(ROOT / "table_e1_empirical_performance.csv")
    }
    pilot = read_json(
        ROOT / "experiments/results/renault_vanilla_bd_pilot_210202_development_v1/summary.json"
    )
    basic_results = {"210202": pilot["vanilla"]}
    prb_development = {"210202": pilot["prb"]}
    remaining = ROOT / "experiments/results/renault_vanilla_bd_remaining7_development_v1"
    for case in CASES[1:]:
        basic_results[case] = read_json(remaining / case / "vanilla_outcome.json")
        prb_development[case] = read_json(remaining / case / "prb_outcome.json")

    rows = []
    for case in CASES:
        identity = empirical[case]
        direct_source = ROOT / "table_e1_empirical_performance.csv"
        rows.append({
            "case": case,
            "method": "Direct",
            "evidence_class": "FROZEN_FORMAL",
            "status": identity["direct_optimality_status"],
            "exact_certification": identity["direct_optimality_status"] == "CERTIFIED_EXACT",
            "pairing_eligible": True,
            "pairing_exclusion_reason": None,
            "objective": identity["direct_objective"],
            "lower_bound": None,
            "upper_bound": None,
            "final_gap": identity["direct_final_gap"],
            "algorithm_core_time_seconds": identity["direct_runtime_seconds"],
            "independent_certification_seconds": None,
            "iterations": None,
            "cuts_added": None,
            "oracle_seconds": None,
            "peak_process_tree_memory_gib": None,
            "instance_hash": identity["instance_hash"],
            "x0_hash": identity["x0_hash"],
            "source": str(direct_source.relative_to(ROOT)),
        })
        for method, directory, prefix in (
            ("Global-BD", "e1b_pure_benders_v1", "E1B-{case}-PURE"),
            ("Aggregate-BD", "e1b_standard_vs_prb_v1", "E1B-{case}-STANDARD"),
        ):
            source = ROOT / "experiments/results" / directory / prefix.format(case=case) / "result.json"
            result = read_json(source)
            rows.append({
                "case": case,
                "method": method,
                "evidence_class": "FROZEN_FORMAL",
                "status": result["status"],
                "exact_certification": result["exact_certification_status"].startswith("CERTIFIED_"),
                "pairing_eligible": result["exact_certification_status"].startswith("CERTIFIED_"),
                "pairing_exclusion_reason": None,
                "objective": result["objective"],
                "lower_bound": result["lower_bound"],
                "upper_bound": result["upper_bound"],
                "final_gap": result["relative_gap"],
                "algorithm_core_time_seconds": result["core_runtime_seconds"],
                "independent_certification_seconds": result["certification_runtime_seconds"],
                "iterations": result["iteration_count"],
                "cuts_added": result["aggregate_cut_count"],
                "oracle_seconds": result.get("global_oracle_runtime_seconds", result.get("oracle_runtime_seconds")),
                "peak_process_tree_memory_gib": result.get("peak_memory_gb"),
                "instance_hash": result["instance_hash"],
                "x0_hash": result["x0_hash"],
                "source": str(source.relative_to(ROOT)),
            })
        basic = basic_results[case]
        basic_source = (
            ROOT / "experiments/results/renault_vanilla_bd_pilot_210202_development_v1/summary.json"
            if case == "210202"
            else remaining / case / "vanilla_outcome.json"
        )
        rows.append({
            "case": case,
            "method": "Basic-BD",
            "evidence_class": "FROZEN_DEVELOPMENT",
            "status": basic["status"],
            "exact_certification": basic["exact_certification_pass"],
            "pairing_eligible": basic["exact_certification_pass"],
            "pairing_exclusion_reason": None if basic["exact_certification_pass"] else "BASIC_CERTIFICATION_FAILED",
            "objective": basic["objective"],
            "lower_bound": None,
            "upper_bound": None,
            "final_gap": None,
            "algorithm_core_time_seconds": basic["algorithm_seconds"],
            "independent_certification_seconds": basic["independent_certification_seconds"],
            "iterations": basic["iterations"],
            "cuts_added": basic["cut_count"],
            "oracle_seconds": basic["oracle_seconds"],
            "peak_process_tree_memory_gib": basic["peak_process_tree_rss_gib"],
            "instance_hash": basic["identity"]["instance_hash"],
            "x0_hash": basic["identity"]["x0_hash"],
            "source": str(basic_source.relative_to(ROOT)),
        })
        prb = prb_development[case]
        prb_source = (
            ROOT / "experiments/results/renault_vanilla_bd_pilot_210202_development_v1/summary.json"
            if case == "210202"
            else remaining / case / "prb_outcome.json"
        )
        prb_eligible = bool(prb["exact_certification_pass"] and case != "210330")
        rows.append({
            "case": case,
            "method": "PRB-BD",
            "evidence_class": "FROZEN_DEVELOPMENT",
            "status": prb["status"],
            "exact_certification": prb["exact_certification_pass"],
            "pairing_eligible": prb_eligible,
            "pairing_exclusion_reason": None if prb_eligible else "PRB_INTERNAL_GLOBAL_COUPLING_CERTIFICATION_FAILED",
            "objective": prb["objective"],
            "lower_bound": None,
            "upper_bound": None,
            "final_gap": None,
            "algorithm_core_time_seconds": prb["algorithm_seconds"],
            "independent_certification_seconds": prb["independent_certification_seconds"],
            "iterations": prb["iterations"],
            "cuts_added": prb["cut_count"],
            "oracle_seconds": prb["oracle_seconds"],
            "peak_process_tree_memory_gib": prb["peak_process_tree_rss_gib"],
            "instance_hash": prb["identity"]["instance_hash"],
            "x0_hash": prb["identity"]["x0_hash"],
            "source": str(prb_source.relative_to(ROOT)),
        })
        eb_source = EB_ROOT / f"EB_RENAULT_{case}" / "result.json"
        if not eb_source.is_file():
            rows.append(_blank(case, "EB-BD", eb_source))
        else:
            eb = read_json(eb_source)
            rows.append({
                "case": case,
                "method": "EB-BD",
                "evidence_class": "DEVELOPMENT",
                "status": eb["solver_status"],
                "exact_certification": eb["exact_certification"],
                "pairing_eligible": eb["exact_certification"],
                "pairing_exclusion_reason": None if eb["exact_certification"] else "EB_CERTIFICATION_FAILED",
                "objective": eb["objective"],
                "lower_bound": eb["final_lower_bound"],
                "upper_bound": eb["final_upper_bound"],
                "final_gap": eb["final_relative_gap"],
                "algorithm_core_time_seconds": eb["algorithm_core_time_seconds"],
                "independent_certification_seconds": eb["independent_certification_seconds"],
                "iterations": eb["iterations"],
                "cuts_added": eb["cuts_added"],
                "oracle_seconds": eb["oracle_seconds"],
                "peak_process_tree_memory_gib": None,
                "instance_hash": eb["identity"]["instance_hash"],
                "x0_hash": eb["identity"]["x0_hash"],
                "source": str(eb_source.relative_to(ROOT)),
            })
    return rows


def write_rows(path: Path = OUTPUT) -> list[dict[str, Any]]:
    rows = build_rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rows = write_rows(args.output)
    print(json.dumps({
        "status": "PASS",
        "rows": len(rows),
        "eb_pending": sum(row["method"] == "EB-BD" and row["objective"] is None for row in rows),
        "prb_210330_pairing_eligible": next(
            row["pairing_eligible"] for row in rows if row["case"] == "210330" and row["method"] == "PRB-BD"
        ),
        "output": str(args.output),
        "optimization_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
