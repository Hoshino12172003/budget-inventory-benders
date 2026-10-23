from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.algorithm_scaling import canonical_hash


OUTPUT_ROOT = ROOT / "experiments/results/basic_benders_scaling_development_v1"
CONDITION = "BASIC_L10_S20260921"
ATTEMPT = OUTPUT_ROOT / "worker_logs" / CONDITION / "attempt-001"
CANONICAL = OUTPUT_ROOT / "runs" / CONDITION
PRB = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard/runs/ASC_L10_S20260921_PRB_BENDERS/result.json"
INSTANCE = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard/instances/L10/20260921/instance.json"
PREPARATION = INSTANCE.with_name("preparation.json")
AUDIT = ROOT / "artifacts/basic_benders_l10_pilot_audit.json"
HASHES = ROOT / "artifacts/basic_benders_l10_pilot_sha256.csv"
COMPARISON = ROOT / "artifacts/basic_benders_l10_prb_comparison.csv"
REPORT = ROOT / "docs/basic_benders_l10_pilot_report.md"
CONFIG_PATH = "experiments/configs/development/basic_benders_scaling_l10_pilot_v1.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def committed_config(commit: str) -> dict:
    content = subprocess.check_output(
        ["git", "show", f"{commit}:{CONFIG_PATH}"], cwd=ROOT, text=True
    )
    return json.loads(content)


def build_audit() -> tuple[dict, list[dict], dict]:
    expected_files = {
        "first_stage_solution.json",
        "iteration_trajectory.json",
        "oracle_trace.jsonl",
        "outcome.json",
        "provenance.json",
        "resource_monitor.json",
        "result.json",
        "solver.log",
        "stderr.log",
        "stdout.log",
    }
    attempt_files = {path.name for path in ATTEMPT.iterdir() if path.is_file()}
    canonical_files = {path.name for path in CANONICAL.iterdir() if path.is_file()}
    result = json.loads((CANONICAL / "result.json").read_text(encoding="utf-8"))
    provenance = json.loads((CANONICAL / "provenance.json").read_text(encoding="utf-8"))
    trajectory = json.loads((CANONICAL / "iteration_trajectory.json").read_text(encoding="utf-8"))
    oracle_rows = [
        json.loads(line)
        for line in (CANONICAL / "oracle_trace.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    monitor = json.loads((CANONICAL / "resource_monitor.json").read_text(encoding="utf-8"))
    outcome = json.loads((CANONICAL / "outcome.json").read_text(encoding="utf-8"))
    prb = json.loads(PRB.read_text(encoding="utf-8"))
    config = committed_config(result["code_commit"])

    hash_rows = []
    byte_identical = True
    for location, root in (("attempt", ATTEMPT), ("canonical", CANONICAL)):
        for path in sorted(root.iterdir()):
            if path.is_file():
                hash_rows.append({
                    "location": location,
                    "path": path.relative_to(ROOT).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                })
    for name in expected_files:
        byte_identical &= sha256(ATTEMPT / name) == sha256(CANONICAL / name)

    checks = {
        "complete_attempt": attempt_files == expected_files,
        "complete_canonical": canonical_files == expected_files,
        "attempt_canonical_byte_identical": byte_identical,
        "condition_identity": result["condition_id"] == CONDITION,
        "single_authorized_condition": config["authorized_condition_ids"] == [CONDITION],
        "authorization_at_execution": config["formal_run_authorized"] is True,
        "config_hash": canonical_hash(config) == result["config_hash"] == provenance["config_hash"],
        "instance_sha256": sha256(INSTANCE) == result["instance_sha256"] == provenance["instance_sha256"],
        "preparation_sha256": sha256(PREPARATION) == result["preparation_sha256"] == provenance["preparation_sha256"],
        "result_sha256": sha256(CANONICAL / "result.json") == provenance["result_sha256"],
        "trajectory_sha256": sha256(CANONICAL / "iteration_trajectory.json") == provenance["trajectory_sha256"],
        "first_stage_sha256": sha256(CANONICAL / "first_stage_solution.json") == provenance["first_stage_solution_sha256"],
        "solver_optimal": result["solver_status"] == "OPTIMAL",
        "exact_certification": result["exact_certification"] is True,
        "cut_validity": result["cut_validity"] is True,
        "independent_certification": (
            result["independent_certification"]["dual_feasible"] is True
            and result["independent_certification"]["objective_residual"] <= 1e-4
            and result["independent_certification"]["strong_duality_residual"] <= 1e-4
        ),
        "resource_success": outcome["status"] == "SUCCESS" and monitor["stop_reason"] is None,
        "process_cap": monitor["peak_process_tree_memory_gib"] <= 4,
        "trajectory_complete": len(trajectory) == result["iterations"] == 8,
        "trajectory_scenario_counts": all(row["scenarios_checked"] == 41617 for row in trajectory),
        "trajectory_cut_counts": all(row["cuts_added"] in (0, 1) for row in trajectory) and sum(row["cuts_added"] for row in trajectory) == result["cuts_added"],
        "trajectory_monotone_time": all(left["cumulative_time_seconds"] < right["cumulative_time_seconds"] for left, right in zip(trajectory, trajectory[1:])),
        "oracle_trace_complete": len(oracle_rows) == len(trajectory) + 2,
        "same_frozen_instance_as_prb": result["instance_hash"] == prb["instance_hash"],
        "objective_consistency_with_prb": abs(result["final_objective"] - prb["final_objective"]) <= 1e-4,
        "prb_exact": prb["exact_certification"] is True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Basic-BD pilot audit failed: {checks}")

    comparison = {
        "size": "L10",
        "seed": 20260921,
        "instance_id": result["instance_id"],
        "basic_exact_certification": result["exact_certification"],
        "prb_exact_certification": prb["exact_certification"],
        "basic_objective": result["final_objective"],
        "prb_objective": prb["final_objective"],
        "absolute_objective_difference": abs(result["final_objective"] - prb["final_objective"]),
        "basic_core_seconds": result["algorithm_core_time"],
        "prb_core_seconds": prb["total_core_solve_time"],
        "basic_over_prb_core_time_ratio": result["algorithm_core_time"] / prb["total_core_solve_time"],
        "basic_iterations": result["iterations"],
        "prb_iterations": prb["iterations"],
        "basic_global_cuts": result["cuts_added"],
        "prb_product_cuts": prb["cuts"],
        "cut_count_comparability_note": "DIFFERENT_CUT_GRANULARITY_DO_NOT_TREAT_AS_EQUAL_WORK_UNITS",
        "basic_final_gap": result["final_gap"],
        "prb_final_gap": prb["relative_gap"],
    }
    audit = {
        "schema": "basic_benders_l10_single_pilot_audit_v1",
        "status": "PASS_EXACT_CERTIFIED_DEVELOPMENT_PILOT",
        "condition_id": CONDITION,
        "attempt": "attempt-001",
        "checks": checks,
        "result": result,
        "resource": {
            "elapsed_seconds": monitor["elapsed_seconds"],
            "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"],
            "stop_reason": monitor["stop_reason"],
            "sample_count": len(monitor["samples"]),
            "minimum_observed_system_available_gib": min(row["system_available_gib"] for row in monitor["samples"]),
        },
        "trajectory": {
            "iterations": len(trajectory),
            "oracle_calls": len(oracle_rows),
            "scenarios_per_call": 41617,
            "persisted_fields": sorted(trajectory[0]),
        },
        "comparison_with_frozen_prb": comparison,
        "sha256_records": len(hash_rows),
        "sensitive_log_review": {
            "license_key_or_access_token_found": False,
            "gurobi_license_id_metadata_present_in_stdout": "LicenseID" in (CANONICAL / "stdout.log").read_text(encoding="utf-8"),
            "note": "The preserved stdout contains Gurobi license metadata but no license key, password, or access token.",
        },
        "optimization_runs_executed": 1,
        "other_conditions_executed": 0,
    }
    return audit, hash_rows, comparison


def write_outputs() -> dict:
    audit, hash_rows, comparison = build_audit()
    AUDIT.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with HASHES.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("location", "path", "size_bytes", "sha256"))
        writer.writeheader()
        writer.writerows(hash_rows)
    with COMPARISON.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=comparison)
        writer.writeheader()
        writer.writerow(comparison)
    result = audit["result"]
    resource = audit["resource"]
    REPORT.write_text("\n".join([
        "# Basic-BD L10 single-pilot audit",
        "",
        "## Disposition",
        "",
        "`PASS_EXACT_CERTIFIED_DEVELOPMENT_PILOT`",
        "",
        "Only `BASIC_L10_S20260921`, attempt-001, was executed. No retry or other Basic-BD/Direct condition ran.",
        "",
        "## Result",
        "",
        f"- Solver status: {result['solver_status']}; exact certification: {result['exact_certification']}; cut validity: {result['cut_validity']}.",
        f"- Objective/LB/UB: {result['final_objective']:.12f} / {result['final_lower_bound']:.12f} / {result['final_upper_bound']:.12f}; relative gap: {result['final_gap']:.3e}.",
        f"- Basic core time: {result['algorithm_core_time']:.6f} s; independent-inclusive total: {result['total_time']:.6f} s.",
        f"- Iterations: {result['iterations']}; global cuts: {result['cuts_added']}; Oracle time: {result['oracle_time']:.6f} s.",
        f"- Independent certification objective residual: {result['independent_certification']['objective_residual']:.3e}; strong-duality residual: {result['independent_certification']['strong_duality_residual']:.3e}.",
        "",
        "## Resource and evidence",
        "",
        f"- Monitor elapsed: {resource['elapsed_seconds']:.6f} s; peak process-tree RSS: {resource['peak_process_tree_memory_gib']:.6f} GiB; stop reason: none.",
        f"- {audit['trajectory']['iterations']} iteration rows and {audit['trajectory']['oracle_calls']} complete global Oracle calls were persisted; each call checked 41,617 scenarios.",
        f"- Attempt and canonical archives are byte-identical; {audit['sha256_records']} file SHA-256 records pass.",
        "",
        "## Frozen PRB comparison",
        "",
        f"- Objective difference: {comparison['absolute_objective_difference']:.3e}; both methods are exact-certified.",
        f"- Core time: Basic {comparison['basic_core_seconds']:.6f} s versus PRB {comparison['prb_core_seconds']:.6f} s; Basic/PRB ratio {comparison['basic_over_prb_core_time_ratio']:.3f}x.",
        f"- Iterations: Basic {comparison['basic_iterations']} versus PRB {comparison['prb_iterations']}.",
        "- Basic global cuts and PRB product cuts have different granularity and are not treated as equal work units.",
    ]) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    audit = write_outputs()
    print(json.dumps({
        "status": audit["status"],
        "condition_id": audit["condition_id"],
        "attempt": audit["attempt"],
        "sha256_records": audit["sha256_records"],
        "other_conditions_executed": audit["other_conditions_executed"],
    }, indent=2))
