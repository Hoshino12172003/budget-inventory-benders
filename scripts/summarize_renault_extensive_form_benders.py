from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.summarize_renault_enhanced_basic_benders import build_rows as build_history_rows


CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
EF_ROOT = ROOT / "experiments/results/renault_extensive_form_benders_development_v1/runs"
EVIDENCE_ROOT = ROOT / "experiments/results/renault_extensive_form_benders_development_v1"
ARTIFACTS = ROOT / "artifacts"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ef_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    direct = {
        row["case"]: row for row in build_history_rows() if row["method"] == "Direct"
    }
    rows = []
    manifest = []
    for case in CASES:
        run = EF_ROOT / f"EF_RENAULT_{case}"
        result_path = run / "result.json"
        provenance_path = run / "provenance.json"
        trajectory_path = run / "iteration_trajectory.json"
        first_stage_path = run / "first_stage_solution.json"
        monitor_path = run / "resource_monitor.json"
        result = read_json(result_path)
        provenance = read_json(provenance_path)
        monitor = read_json(monitor_path)
        checks = {
            "result_sha256": sha256(result_path) == provenance["result_sha256"],
            "trajectory_sha256": sha256(trajectory_path) == provenance["trajectory_sha256"],
            "first_stage_sha256": sha256(first_stage_path) == provenance["first_stage_sha256"],
            "instance_hash": result["identity"]["instance_hash"] == direct[case]["instance_hash"],
            "x0_hash": result["identity"]["x0_hash"] == direct[case]["x0_hash"],
            "worker_exit": monitor["worker_return_code"] == 0 and monitor["stop_reason"] is None,
            "exact_certification": result["exact_certification"] is True,
            "cut_validity": result["cut_validity"] is True,
            "independent_certification": result["independent_global_certification"]["pass"] is True,
        }
        if not all(checks.values()):
            raise RuntimeError(f"EF-BD integrity failure for {case}: {checks}")
        residual = abs(float(result["objective"]) - float(direct[case]["objective"]))
        if residual > 1e-4:
            raise RuntimeError(f"EF-BD objective mismatch for {case}: {residual}")
        rows.append({
            "case": case,
            "condition_id": result["condition_id"],
            "solver_status": result["solver_status"],
            "exact_certification": result["exact_certification"],
            "cut_validity": result["cut_validity"],
            "objective": result["objective"],
            "direct_objective": direct[case]["objective"],
            "direct_objective_residual": residual,
            "final_lower_bound": result["final_lower_bound"],
            "final_upper_bound": result["final_upper_bound"],
            "final_relative_gap": result["final_relative_gap"],
            "iterations": result["iterations"],
            "cuts_added": result["cuts_added"],
            "algorithm_core_time_seconds": result["algorithm_core_time_seconds"],
            "master_time_seconds": result["master_seconds"],
            "oracle_time_seconds": result["oracle_seconds"],
            "certification_time_seconds": result["independent_certification_seconds"],
            "total_time_seconds": result["total_time_seconds"],
            "optimizer_calls": result["oracle_engineering"]["oracle_solve_calls"],
            "scenario_blocks": result["oracle_engineering"]["scenario_blocks"],
            "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"],
            "instance_hash": result["identity"]["instance_hash"],
            "result_sha256": sha256(result_path),
            "provenance_sha256": sha256(provenance_path),
            "execution_git_commit": provenance["git_commit"],
        })
    for path in sorted(item for item in EVIDENCE_ROOT.rglob("*") if item.is_file()):
        relative = path.relative_to(EVIDENCE_ROOT)
        condition = next(part for part in relative.parts if part.startswith("EF_RENAULT_"))
        manifest.append({
            "case": condition.rsplit("_", 1)[1],
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
    return rows, manifest


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ef_rows, manifest = _ef_rows()
    _write_csv(ARTIFACTS / "renault_ef_bd_results.csv", ef_rows)
    history = build_history_rows()
    sg = {
        row["case"]: row
        for row in csv.DictReader((ARTIFACTS / "renault_sg_bd_results.csv").open(encoding="utf-8", newline=""))
    }
    comparison = []
    for row in history:
        comparison.append({
            "case": row["case"], "method": row["method"],
            "algorithm_core_time_seconds": row["algorithm_core_time_seconds"],
            "objective": row["objective"], "exact_certification": row["exact_certification"],
            "pairing_eligible": row["pairing_eligible"],
            "pairing_exclusion_reason": row["pairing_exclusion_reason"],
            "evidence_class": row["evidence_class"], "source": row["source"],
        })
    for case in CASES:
        comparison.append({
            "case": case, "method": "SG-BD",
            "algorithm_core_time_seconds": sg[case]["algorithm_core_time_seconds"],
            "objective": sg[case]["objective"], "exact_certification": True,
            "pairing_eligible": True, "pairing_exclusion_reason": "",
            "evidence_class": "FROZEN_DEVELOPMENT",
            "source": "artifacts/renault_sg_bd_results.csv",
        })
        ef = next(row for row in ef_rows if row["case"] == case)
        comparison.append({
            "case": case, "method": "EF-BD",
            "algorithm_core_time_seconds": ef["algorithm_core_time_seconds"],
            "objective": ef["objective"], "exact_certification": True,
            "pairing_eligible": True, "pairing_exclusion_reason": "",
            "evidence_class": "DEVELOPMENT",
            "source": f"experiments/results/renault_extensive_form_benders_development_v1/runs/EF_RENAULT_{case}/result.json",
        })
    _write_csv(ARTIFACTS / "renault_8method_core_time_comparison.csv", comparison)
    (ARTIFACTS / "renault_ef_bd_sha256_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    by_method: dict[str, list[dict[str, Any]]] = {}
    for row in comparison:
        if row["pairing_eligible"] in (True, "True"):
            by_method.setdefault(row["method"], []).append(row)
    summaries = []
    for method, rows in by_method.items():
        summaries.append((method, len(rows), mean(float(row["algorithm_core_time_seconds"]) for row in rows)))
    summaries.sort(key=lambda item: item[2])
    ef_by_case = {row["case"]: row for row in ef_rows}
    history_by = {(row["case"], row["method"]): row for row in history}
    def paired(method: str) -> tuple[int, int, float]:
        ratios = []
        wins = 0
        for case in CASES:
            other = history_by[case, method]
            if other["pairing_eligible"] is not True:
                continue
            ef_time = float(ef_by_case[case]["algorithm_core_time_seconds"])
            other_time = float(other["algorithm_core_time_seconds"])
            wins += ef_time < other_time
            ratios.append(other_time / ef_time)
        return wins, len(ratios) - wins, math.exp(mean(math.log(value) for value in ratios))

    direct_pair = paired("Direct")
    basic_pair = paired("Basic-BD")
    aggregate_pair = paired("Aggregate-BD")
    report = [
        "# Renault extensive-form Benders result audit",
        "",
        "All timing comparisons below are descriptive cross-batch comparisons, not synchronized runs.",
        "",
        "## EF-BD acceptance",
        "",
        f"- Exact-certified: {sum(row['exact_certification'] for row in ef_rows)}/8",
        f"- Mean core time: {mean(row['algorithm_core_time_seconds'] for row in ef_rows):.6f} s",
        f"- Mean Oracle time: {mean(row['oracle_time_seconds'] for row in ef_rows):.6f} s",
        f"- Mean master time: {mean(row['master_time_seconds'] for row in ef_rows):.6f} s",
        f"- Mean certification time: {mean(row['certification_time_seconds'] for row in ef_rows):.6f} s",
        f"- Maximum Direct objective residual: {max(row['direct_objective_residual'] for row in ef_rows):.3e}",
        f"- Peak process-tree RSS range: {min(row['peak_process_tree_memory_gib'] for row in ef_rows):.3f}--{max(row['peak_process_tree_memory_gib'] for row in ef_rows):.3f} GiB",
        "",
        "## Paired descriptive comparisons",
        "",
        f"- EF-BD vs Direct: {direct_pair[0]} wins / {direct_pair[1]} losses; Direct/EF geometric time ratio {direct_pair[2]:.3f}.",
        f"- EF-BD vs Basic-BD: {basic_pair[0]} wins / {basic_pair[1]} losses; Basic/EF geometric time ratio {basic_pair[2]:.3f}.",
        f"- EF-BD vs Aggregate-BD: {aggregate_pair[0]} wins / {aggregate_pair[1]} losses; Aggregate/EF geometric time ratio {aggregate_pair[2]:.3f}.",
        "- Historical PRB-BD 210330 remains excluded from strict pairing because its internal global-coupling certification failed.",
        "",
        "## Core-time ordering",
        "",
        "| Method | Eligible N | Mean core time (s) |",
        "|---|---:|---:|",
        *[f"| {method} | {count} | {value:.6f} |" for method, count, value in summaries],
        "",
        "EF-BD is a valid traditional single-cut baseline, but the observed ordering is empirical and must not be rewritten to match the prior hypothesis.",
    ]
    (ARTIFACTS / "renault_ef_bd_audit.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    acceptance = {
        "status": "PASS", "ef_certified": 8,
        "ef_mean_core_seconds": mean(row["algorithm_core_time_seconds"] for row in ef_rows),
        "ef_mean_oracle_seconds": mean(row["oracle_time_seconds"] for row in ef_rows),
        "ef_mean_master_seconds": mean(row["master_time_seconds"] for row in ef_rows),
        "ef_total_optimizer_calls": sum(row["optimizer_calls"] for row in ef_rows),
        "ef_total_iterations": sum(row["iterations"] for row in ef_rows),
        "ef_total_cuts": sum(row["cuts_added"] for row in ef_rows),
        "ef_vs_direct": direct_pair, "ef_vs_basic": basic_pair,
        "ef_vs_aggregate": aggregate_pair,
        "ordering": summaries, "optimization_calls": 0,
    }
    (ARTIFACTS / "renault_ef_bd_acceptance_audit.json").write_text(
        json.dumps(acceptance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(acceptance, indent=2))


if __name__ == "__main__":
    main()
