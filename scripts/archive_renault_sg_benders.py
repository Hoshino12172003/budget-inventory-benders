from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any

from summarize_renault_enhanced_basic_benders import CASES, FIELDS, ROOT, build_rows


RESULT_ROOT = ROOT / "experiments/results/renault_sg_benders_development_v1"
ARTIFACT_ROOT = ROOT / "artifacts"
SUMMARY_PATH = ROOT / "docs/renault_sg_bd_results.md"
PAYLOAD_FILES = (
    "first_stage_solution.json",
    "iteration_trajectory.json",
    "oracle_trace.jsonl",
    "provenance.json",
    "result.json",
    "solver.log",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    historical_rows = build_rows()
    historical = {(row["case"], row["method"]): row for row in historical_rows}
    sg_rows = []
    speedup_rows = []
    hash_rows = []
    checks = {}
    for case in CASES:
        condition = f"SG_RENAULT_{case}"
        attempt = RESULT_ROOT / "worker_logs" / condition / "attempt-001"
        canonical = RESULT_ROOT / "runs" / condition
        payload = attempt / "payload"
        result = json.loads((canonical / "result.json").read_text(encoding="utf-8"))
        provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8"))
        monitor = json.loads((canonical / "resource_monitor.json").read_text(encoding="utf-8"))
        trajectory = json.loads((canonical / "iteration_trajectory.json").read_text(encoding="utf-8"))
        trace = [
            json.loads(line)
            for line in (canonical / "oracle_trace.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        commit = provenance["git_commit"]
        historical_hashes = {
            "config": hashlib.sha256(git_blob(commit, "experiments/configs/development/renault_sg_benders_v1.yaml")).hexdigest(),
            "implementation": hashlib.sha256(git_blob(commit, "src/robust_inventory_reconfiguration/scenario_generation_benders.py")).hexdigest(),
            "bound": hashlib.sha256(git_blob(commit, "src/robust_inventory_reconfiguration/scenario_generation_single_cut.py")).hexdigest(),
            "runner": hashlib.sha256(git_blob(commit, "experiments/run_renault_sg_benders.py")).hexdigest(),
        }
        per_case = {
            "canonical_matches_attempt": all(
                sha256(canonical / name) == sha256(payload / name) for name in PAYLOAD_FILES
            ),
            "result_sha256": sha256(canonical / "result.json") == provenance["result_sha256"],
            "trajectory_sha256": sha256(canonical / "iteration_trajectory.json") == provenance["trajectory_sha256"],
            "oracle_trace_sha256": sha256(canonical / "oracle_trace.jsonl") == provenance["oracle_trace_sha256"],
            "first_stage_sha256": sha256(canonical / "first_stage_solution.json") == provenance["first_stage_sha256"],
            "execution_code_identity": (
                historical_hashes["config"] == provenance["config_sha256"]
                and historical_hashes["implementation"] == provenance["implementation_sha256"]
                and historical_hashes["bound"] == provenance["bound_sha256"]
                and historical_hashes["runner"] == provenance["runner_sha256"]
            ),
            "condition_identity": result["condition_id"] == condition == provenance["condition_id"],
            "instance_identity": result["identity"] == provenance["identity"],
            "exact_certification": result["exact_certification"] is True,
            "cut_validity": result["cut_validity"] is True,
            "direct_objective_consistency": result["direct_objective_residual"] <= 1e-4,
            "independent_full_enumeration": result["independent_global_certification"]["pass"] is True,
            "worker_clean_exit": monitor["worker_return_code"] == 0 and monitor["stop_reason"] is None,
            "trajectory_complete": len(trajectory) == result["iterations"],
            "oracle_trace_complete": len(trace) == result["iterations"] + 1,
            "all_iterates_persisted": all(row.get("first_stage_x") for row in trajectory),
            "scenario_accounting": all(
                row["exact_lp_solves"] + row["safely_pruned_scenarios"] == row["total_scenarios"] == 4657
                for row in trace
            ),
        }
        checks[case] = per_case
        if not all(per_case.values()):
            raise RuntimeError(f"SG-BD archive validation failed for {case}: {per_case}")
        sg_rows.append({
            "case": case,
            "condition_id": condition,
            "solver_status": result["solver_status"],
            "exact_certification": result["exact_certification"],
            "cut_validity": result["cut_validity"],
            "objective": result["objective"],
            "direct_objective": result["direct_objective"],
            "direct_objective_residual": result["direct_objective_residual"],
            "final_lower_bound": result["final_lower_bound"],
            "final_upper_bound": result["final_upper_bound"],
            "final_relative_gap": result["final_relative_gap"],
            "iterations": result["iterations"],
            "cuts_added": result["cuts_added"],
            "algorithm_core_time_seconds": result["algorithm_core_time_seconds"],
            "oracle_time_seconds": result["oracle_seconds"],
            "certification_time_seconds": result["independent_certification_seconds"],
            "total_time_seconds": result["total_time_seconds"],
            "scenario_lp_solves": result["oracle_engineering"]["scenario_lp_solves"],
            "safely_pruned_scenarios": result["oracle_engineering"]["safely_pruned_scenarios"],
            "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"],
            "instance_hash": result["identity"]["instance_hash"],
            "result_sha256": provenance["result_sha256"],
            "provenance_sha256": sha256(canonical / "provenance.json"),
            "execution_git_commit": commit,
        })
        eb_time = float(historical[(case, "EB-BD")]["algorithm_core_time_seconds"])
        sg_time = float(result["algorithm_core_time_seconds"])
        speedup_rows.append({
            "case": case,
            "eb_bd_core_time_seconds": eb_time,
            "sg_bd_core_time_seconds": sg_time,
            "eb_over_sg_speedup": eb_time / sg_time,
            "sg_faster_than_direct": sg_time < float(historical[(case, "Direct")]["algorithm_core_time_seconds"]),
        })
        for evidence_class, base in (("attempt", attempt), ("canonical", canonical)):
            for path in sorted(item for item in base.rglob("*") if item.is_file()):
                hash_rows.append({
                    "case": case,
                    "evidence_class": evidence_class,
                    "path": str(path.relative_to(ROOT)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                })

    long_rows = list(historical_rows)
    for row in sg_rows:
        long_rows.append({
            "case": row["case"],
            "method": "SG-BD",
            "evidence_class": "FROZEN_DEVELOPMENT",
            "status": row["solver_status"],
            "exact_certification": row["exact_certification"],
            "pairing_eligible": row["exact_certification"],
            "pairing_exclusion_reason": None,
            "objective": row["objective"],
            "lower_bound": row["final_lower_bound"],
            "upper_bound": row["final_upper_bound"],
            "final_gap": row["final_relative_gap"],
            "algorithm_core_time_seconds": row["algorithm_core_time_seconds"],
            "independent_certification_seconds": row["certification_time_seconds"],
            "iterations": row["iterations"],
            "cuts_added": row["cuts_added"],
            "oracle_seconds": row["oracle_time_seconds"],
            "peak_process_tree_memory_gib": row["peak_process_tree_memory_gib"],
            "instance_hash": row["instance_hash"],
            "x0_hash": historical[(row["case"], "Direct")]["x0_hash"],
            "source": f"experiments/results/renault_sg_benders_development_v1/runs/{row['condition_id']}/result.json",
        })
    by_case_method = {(row["case"], row["method"]): row for row in long_rows}
    methods = ("Direct", "Basic-BD", "EB-BD", "SG-BD", "Aggregate-BD", "PRB-BD", "Global-BD")
    wide_rows = []
    for case in CASES:
        wide: dict[str, Any] = {"case": case}
        for method in methods:
            item = by_case_method[(case, method)]
            prefix = method.lower().replace("-", "_")
            wide[f"{prefix}_core_time_seconds"] = item["algorithm_core_time_seconds"]
            wide[f"{prefix}_exact_certification"] = item["exact_certification"]
            wide[f"{prefix}_pairing_eligible"] = item["pairing_eligible"]
            wide[f"{prefix}_source"] = item["source"]
        wide_rows.append(wide)
    means = {
        method: sum(
            float(by_case_method[(case, method)]["algorithm_core_time_seconds"])
            for case in CASES
        ) / len(CASES)
        for method in methods
    }
    sg_mean = means["SG-BD"]
    eb_speedup = math.exp(
        sum(math.log(row["eb_over_sg_speedup"]) for row in speedup_rows) / len(speedup_rows)
    )
    audit = {
        "status": "PASS",
        "expected": 8,
        "exact_certified": sum(row["exact_certification"] is True for row in sg_rows),
        "objective_consistent_with_direct": sum(row["direct_objective_residual"] <= 1e-4 for row in sg_rows),
        "checks": checks,
        "method_mean_core_seconds": means,
        "observed_mean_time_order_fastest_to_slowest": sorted(means, key=means.get),
        "sg_vs_eb_geometric_speedup": eb_speedup,
        "sg_vs_direct_wins": sum(row["sg_faster_than_direct"] for row in speedup_rows),
        "sg_mean_oracle_seconds": sum(row["oracle_time_seconds"] for row in sg_rows) / len(sg_rows),
        "prb_210330_strict_pairing_eligible": by_case_method[("210330", "PRB-BD")]["pairing_eligible"],
        "cross_batch_warning": "Each method retains its named frozen source batch; timings were not relabeled as one concurrent batch.",
        "optimization_calls": 0,
    }
    write_csv(ARTIFACT_ROOT / "renault_sg_bd_results.csv", sg_rows, list(sg_rows[0]))
    write_csv(ARTIFACT_ROOT / "renault_sg_bd_vs_eb_speedup.csv", speedup_rows, list(speedup_rows[0]))
    write_csv(ARTIFACT_ROOT / "renault_seven_algorithm_long_form.csv", long_rows, list(FIELDS))
    write_csv(ARTIFACT_ROOT / "renault_seven_algorithm_core_time_comparison.csv", wide_rows, list(wide_rows[0]))
    write_csv(ARTIFACT_ROOT / "renault_sg_bd_sha256_manifest.csv", hash_rows, list(hash_rows[0]))
    (ARTIFACT_ROOT / "renault_sg_bd_acceptance_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    SUMMARY_PATH.write_text(
        "# Renault SG-BD development results\n\n"
        "All eight frozen Renault cases completed once and passed SG exact separation, global cut, "
        "independent full-enumeration, Direct-objective, identity, resource, and SHA-256 checks.\n\n"
        f"- SG-BD mean algorithm core time: {sg_mean:.6f} s\n"
        f"- EB-BD mean algorithm core time: {means['EB-BD']:.6f} s\n"
        f"- EB-BD / SG-BD geometric mean speedup: {eb_speedup:.6f}x\n"
        f"- SG-BD wins against Direct: {audit['sg_vs_direct_wins']}/8\n"
        f"- Mean SG-BD Oracle time: {audit['sg_mean_oracle_seconds']:.6f} s\n"
        f"- Observed mean-time order: {' < '.join(audit['observed_mean_time_order_fastest_to_slowest'])}\n\n"
        "The seven methods retain their original evidence classes and source paths; the table does not "
        "relabel separate historical batches as a single run. Historical PRB case 210330 remains "
        "ineligible for strict pairing because its internal global-coupling certification failed.\n",
        encoding="utf-8",
    )
    return audit


if __name__ == "__main__":
    print(json.dumps(build_archive(), indent=2, sort_keys=True))
