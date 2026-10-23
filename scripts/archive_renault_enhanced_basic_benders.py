from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from summarize_renault_enhanced_basic_benders import CASES, ROOT, build_rows


RESULT_ROOT = ROOT / "experiments/results/renault_enhanced_basic_benders_development_v1"
ARTIFACT_ROOT = ROOT / "artifacts"
SUMMARY_PATH = ROOT / "docs/renault_eb_bd_results.md"
PAYLOAD_FILES = (
    "first_stage_solution.json",
    "iteration_trajectory.json",
    "oracle_trace.jsonl",
    "provenance.json",
    "result.json",
    "solver.log",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def git_blob(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def build_archive() -> dict[str, Any]:
    comparison_rows = build_rows()
    by_case_method = {
        (row["case"], row["method"]): row for row in comparison_rows
    }
    eb_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    speedup_rows: list[dict[str, Any]] = []
    hash_rows: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}

    for case in CASES:
        condition = f"EB_RENAULT_{case}"
        attempt = RESULT_ROOT / "worker_logs" / condition / "attempt-001"
        canonical = RESULT_ROOT / "runs" / condition
        result = json.loads((canonical / "result.json").read_text(encoding="utf-8"))
        provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8"))
        monitor = json.loads((canonical / "resource_monitor.json").read_text(encoding="utf-8"))
        payload = attempt / "payload"

        per_case_checks = {
            "canonical_matches_attempt": all(
                sha256(canonical / name) == sha256(payload / name) for name in PAYLOAD_FILES
            ),
            "result_sha256": sha256(canonical / "result.json") == provenance["result_sha256"],
            "trajectory_sha256": sha256(canonical / "iteration_trajectory.json") == provenance["trajectory_sha256"],
            "first_stage_sha256": sha256(canonical / "first_stage_solution.json") == provenance["first_stage_sha256"],
            "identity_matches": result["identity"] == provenance["identity"],
            "condition_matches": result["condition_id"] == condition == provenance["condition_id"],
            "worker_clean_exit": monitor["worker_return_code"] == 0 and monitor["stop_reason"] is None,
            "exact_certification": result["exact_certification"] is True,
            "cut_validity": result["cut_validity"] is True,
        }
        commit = provenance["git_commit"]
        historical_hashes = {
            "config": hashlib.sha256(git_blob(commit, "experiments/configs/development/renault_enhanced_basic_benders_v1.yaml")).hexdigest(),
            "implementation": hashlib.sha256(git_blob(commit, "src/robust_inventory_reconfiguration/enhanced_basic_benders.py")).hexdigest(),
            "runner": hashlib.sha256(git_blob(commit, "experiments/run_renault_enhanced_basic_benders.py")).hexdigest(),
        }
        per_case_checks["execution_code_identity"] = (
            historical_hashes["config"] == provenance["config_sha256"]
            and historical_hashes["implementation"] == provenance["implementation_sha256"]
            and historical_hashes["runner"] == provenance["runner_sha256"]
        )
        checks[case] = per_case_checks
        if not all(per_case_checks.values()):
            raise RuntimeError(f"EB-BD archive validation failed for {case}: {per_case_checks}")

        direct = by_case_method[(case, "Direct")]
        objective_difference = abs(float(result["objective"]) - float(direct["objective"]))
        objective_consistent = objective_difference <= 1e-4
        if not objective_consistent:
            raise RuntimeError(f"objective mismatch for {case}: {objective_difference}")
        eb_rows.append({
            "case": case,
            "condition_id": condition,
            "solver_status": result["solver_status"],
            "exact_certification": result["exact_certification"],
            "cut_validity": result["cut_validity"],
            "final_objective": result["objective"],
            "direct_objective": direct["objective"],
            "absolute_objective_difference": objective_difference,
            "objective_consistent_with_direct": objective_consistent,
            "final_gap": result["final_relative_gap"],
            "iterations": result["iterations"],
            "cuts_added": result["cuts_added"],
            "algorithm_core_time_seconds": result["algorithm_core_time_seconds"],
            "oracle_time_seconds": result["oracle_seconds"],
            "certification_time_seconds": result["independent_certification_seconds"],
            "total_time_seconds": result["total_time_seconds"],
            "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"],
            "resource_stop_reason": monitor["stop_reason"],
            "worker_return_code": monitor["worker_return_code"],
            "instance_hash": result["identity"]["instance_hash"],
            "result_sha256": provenance["result_sha256"],
            "provenance_sha256": sha256(canonical / "provenance.json"),
            "execution_git_commit": commit,
        })
        run_rows.append({
            "case": case,
            "condition_id": condition,
            "attempt": "attempt-001",
            "classification": "SUCCESS",
            "stop_reason": monitor["stop_reason"],
            "worker_return_code": monitor["worker_return_code"],
            "elapsed_seconds": monitor["elapsed_seconds"],
            "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"],
        })
        basic_time = float(by_case_method[(case, "Basic-BD")]["algorithm_core_time_seconds"])
        eb_time = float(result["algorithm_core_time_seconds"])
        speedup_rows.append({
            "case": case,
            "basic_bd_core_time_seconds": basic_time,
            "eb_bd_core_time_seconds": eb_time,
            "basic_over_eb_speedup": basic_time / eb_time,
            "faster_method": "EB-BD" if eb_time < basic_time else "Basic-BD",
        })
        for evidence_class, base in (("attempt", attempt), ("canonical", canonical)):
            for path in sorted(p for p in base.rglob("*") if p.is_file()):
                hash_rows.append({
                    "case": case,
                    "evidence_class": evidence_class,
                    "path": str(path.relative_to(ROOT)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                })

    methods = ("Direct", "Basic-BD", "EB-BD", "Aggregate-BD", "PRB-BD", "Global-BD")
    wide_rows = []
    for case in CASES:
        row: dict[str, Any] = {"case": case}
        for method in methods:
            item = by_case_method[(case, method)]
            prefix = method.lower().replace("-", "_")
            row[f"{prefix}_core_time_seconds"] = item["algorithm_core_time_seconds"]
            row[f"{prefix}_exact_certification"] = item["exact_certification"]
            row[f"{prefix}_pairing_eligible"] = item["pairing_eligible"]
        wide_rows.append(row)

    method_means = {
        method: sum(float(by_case_method[(case, method)]["algorithm_core_time_seconds"]) for case in CASES) / len(CASES)
        for method in methods
    }
    geometric_speedup = math.exp(
        sum(math.log(float(row["basic_over_eb_speedup"])) for row in speedup_rows) / len(speedup_rows)
    )
    oracle_mean = sum(float(row["oracle_time_seconds"]) for row in eb_rows) / len(eb_rows)
    core_mean = method_means["EB-BD"]
    oracle_share = sum(float(row["oracle_time_seconds"]) for row in eb_rows) / sum(
        float(row["algorithm_core_time_seconds"]) for row in eb_rows
    )
    audit = {
        "status": "PASS",
        "expected": 8,
        "exact_certified": sum(row["exact_certification"] is True for row in eb_rows),
        "cut_valid": sum(row["cut_validity"] is True for row in eb_rows),
        "objective_consistent_with_direct": sum(row["objective_consistent_with_direct"] is True for row in eb_rows),
        "resource_or_time_failures": sum(row["classification"] != "SUCCESS" for row in run_rows),
        "checks": checks,
        "method_mean_core_seconds": method_means,
        "mean_core_time_order_fastest_to_slowest": sorted(method_means, key=method_means.get),
        "eb_vs_basic_geometric_speedup": geometric_speedup,
        "eb_vs_direct_wins": sum(
            float(by_case_method[(case, "EB-BD")]["algorithm_core_time_seconds"])
            < float(by_case_method[(case, "Direct")]["algorithm_core_time_seconds"])
            for case in CASES
        ),
        "eb_oracle_mean_seconds": oracle_mean,
        "eb_oracle_share_of_core_time": oracle_share,
        "prb_210330_strict_pairing_eligible": by_case_method[("210330", "PRB-BD")]["pairing_eligible"],
        "optimization_calls": 0,
    }

    write_csv(ARTIFACT_ROOT / "renault_eb_bd_results.csv", eb_rows, list(eb_rows[0]))
    write_csv(ARTIFACT_ROOT / "renault_six_algorithm_core_time_comparison.csv", wide_rows, list(wide_rows[0]))
    write_csv(ARTIFACT_ROOT / "renault_eb_bd_vs_basic_speedup.csv", speedup_rows, list(speedup_rows[0]))
    write_csv(ARTIFACT_ROOT / "renault_eb_bd_run_status.csv", run_rows, list(run_rows[0]))
    write_csv(ARTIFACT_ROOT / "renault_eb_bd_sha256_manifest.csv", hash_rows, list(hash_rows[0]))
    (ARTIFACT_ROOT / "renault_eb_bd_acceptance_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    SUMMARY_PATH.write_text(
        "# Renault EB-BD development results\n\n"
        "The eight pre-specified Renault cases completed under the frozen development protocol. "
        "All eight runs are exact-certified, cut-valid, resource-clean, and objective-consistent with Direct Gurobi.\n\n"
        f"- EB-BD mean algorithm core time: {core_mean:.6f} s\n"
        f"- Basic-BD mean algorithm core time: {method_means['Basic-BD']:.6f} s\n"
        f"- Basic-BD / EB-BD geometric mean speedup: {geometric_speedup:.6f}x\n"
        f"- EB-BD wins against Direct: {audit['eb_vs_direct_wins']}/8\n"
        f"- EB-BD mean oracle time: {oracle_mean:.6f} s ({oracle_share:.2%} of core time)\n"
        f"- Mean-time order, fastest to slowest: {' < '.join(audit['mean_core_time_order_fastest_to_slowest'])}\n\n"
        "EB-BD is faster than the original Basic-BD on every case, but it is slower than Direct and "
        "does not fall between Direct and Aggregate-BD on these data. Its runtime remains dominated by "
        "exact enumeration of all admissible global scenarios. Renault case 210330 remains excluded from "
        "strict PRB development pairing because its historical internal global-coupling certification failed; "
        "that record was not reclassified.\n",
        encoding="utf-8",
    )
    return audit


if __name__ == "__main__":
    print(json.dumps(build_archive(), indent=2, sort_keys=True))
