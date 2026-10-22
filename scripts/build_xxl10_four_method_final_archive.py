from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path
from statistics import mean

from scipy.stats import wilcoxon


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "experiments/analysis/xxl10_four_method_final"
SEEDS = list(range(20260921, 20260931))
METHODS = ("Direct", "EF-BD", "Aggregate-BD", "PRB-BD")
DIRECT_CORE_SHA256 = "fef8019f9aa9be1d2942a5d3aad363c2c3c28929e52cc02b359d1626a1880edd"
FORMAL_ROOT = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
DIRECT_ROOTS = {
    20260921: ROOT / "experiments/results/direct_scaling_xxl10_paired_pilot_v1",
    20260922: ROOT / "experiments/results/direct_scaling_xxl10_remaining9_v1",
    **{seed: ROOT / "experiments/results/direct_scaling_xxl10_remaining8_v1" for seed in range(20260923, 20260931)},
}
EF_ROOTS = {
    20260921: ROOT / "experiments/results/ef_benders_scaling_xxl10_paired_pilot_v1",
    **{seed: ROOT / "experiments/results/ef_benders_scaling_xxl10_remaining9_v1" for seed in range(20260922, 20260931)},
}


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def direct_batch_record(seed: int) -> dict:
    if seed == 20260921:
        return {}
    name = (
        "DIRECT_XXL10_REMAINING9_V1_METHOD2_THREADS2.json"
        if seed == 20260922
        else "DIRECT_XXL10_REMAINING8_RECOVERY_V1_METHOD2_THREADS2.json"
    )
    report = read_json(DIRECT_ROOTS[seed] / "batch_reports" / name)
    return next(row for row in report["records"] if row["condition_id"] == f"DIRECT_XXL10_S{seed}")


def direct_record(seed: int) -> tuple[dict, list[Path]]:
    root = DIRECT_ROOTS[seed]
    condition = f"DIRECT_XXL10_S{seed}"
    attempt = "attempt-002" if seed == 20260921 else "attempt-001"
    monitor_path = root / "worker_logs" / condition / attempt / "resource_monitor.json"
    monitor = read_json(monitor_path)
    run = root / "runs" / condition
    result_path = run / "result.json"
    files = sorted((root / "worker_logs" / condition).rglob("*"))
    files = [path for path in files if path.is_file()]
    if run.is_dir():
        files.extend(sorted(path for path in run.iterdir() if path.is_file()))
    if result_path.is_file():
        result = read_json(result_path)
        status = result["solver_status"]
        exact = result["exact_certification"] is True
        if status == "OPTIMAL" and exact:
            classification = "CERTIFIED_SUCCESS"
        elif status == "TIME_LIMIT" and result.get("objective") is not None:
            classification = "TIME_LIMIT_WITH_INCUMBENT"
        elif status == "TIME_LIMIT":
            classification = "TIME_LIMIT_NO_INCUMBENT"
        else:
            classification = "INTEGRITY_FAILURE"
        provenance_path = run / "provenance.json"
        provenance = read_json(provenance_path)
        assert provenance["result_sha256"] == file_sha(result_path)
        assert provenance["solver_log_sha256"] == file_sha(run / "solver.log")
        source = result_path
    else:
        batch = direct_batch_record(seed)
        result = {}
        classification = "MONITOR_HARD_TIME_LIMIT"
        exact = False
        status = None
        source = root / "batch_reports" / "DIRECT_XXL10_REMAINING8_RECOVERY_V1_METHOD2_THREADS2.json"
        files.append(source)
        assert seed == 20260927
        assert batch["classification"] == "TIME_LIMIT"
        assert monitor["stop_reason"] == "MONITOR_HARD_TIME_LIMIT"
        assert monitor["worker_return_code"] == 15
    instance = read_json(FORMAL_ROOT / "instances" / "XXL10" / str(seed) / "preparation.json")
    return {
        "seed": seed,
        "method": "Direct",
        "condition_id": condition,
        "classification": classification,
        "solver_status": status,
        "exact_certification": exact,
        "cut_validity": None,
        "objective": result.get("objective"),
        "lower_bound": result.get("best_bound"),
        "upper_bound": result.get("objective"),
        "final_gap": result.get("mip_gap"),
        "core_time_seconds": result.get("T_core_seconds"),
        "oracle_time_seconds": None,
        "master_time_seconds": None,
        "certification_time_seconds": result.get("certification_seconds"),
        "total_time_seconds": result.get("total_wall_seconds"),
        "iterations": None,
        "cuts": None,
        "peak_process_tree_memory_gib": monitor.get("peak_process_tree_memory_gib"),
        "worker_return_code": monitor.get("worker_return_code"),
        "stop_reason": monitor.get("stop_reason"),
        "instance_hash": instance["instance_hash"],
        "x0_hash": instance["x0_hash"],
        "source_file": relative(source),
        "source_sha256": file_sha(source),
    }, files


def ef_record(seed: int) -> tuple[dict, list[Path]]:
    root = EF_ROOTS[seed]
    condition = f"EF_XXL10_S{seed}"
    run = root / "runs" / condition
    result_path = run / "result.json"
    result = read_json(result_path)
    provenance = read_json(run / "provenance.json")
    assert provenance["result_sha256"] == file_sha(result_path)
    assert provenance["trajectory_sha256"] == file_sha(run / "iteration_trajectory.json")
    assert provenance["first_stage_sha256"] == file_sha(run / "first_stage_solution.json")
    monitor_path = run / "resource_monitor.json"
    monitor = read_json(monitor_path)
    files = sorted(path for path in root.rglob("*") if path.is_file() and condition in path.as_posix())
    return {
        "seed": seed,
        "method": "EF-BD",
        "condition_id": condition,
        "classification": "CERTIFIED_SUCCESS",
        "solver_status": result["solver_status"],
        "exact_certification": result["exact_certification"],
        "cut_validity": result["cut_validity"],
        "objective": result["final_objective"],
        "lower_bound": result["final_lower_bound"],
        "upper_bound": result["final_upper_bound"],
        "final_gap": result["final_gap"],
        "core_time_seconds": result["algorithm_core_time"],
        "oracle_time_seconds": result["oracle_time"],
        "master_time_seconds": result["master_time"],
        "certification_time_seconds": result["certification_time"],
        "total_time_seconds": result["total_time"],
        "iterations": result["iterations"],
        "cuts": result["cuts_added"],
        "peak_process_tree_memory_gib": monitor.get("peak_process_tree_memory_gib"),
        "worker_return_code": monitor.get("worker_return_code"),
        "stop_reason": monitor.get("stop_reason"),
        "instance_hash": result["instance_hash"],
        "x0_hash": provenance["x0_hash"],
        "source_file": relative(result_path),
        "source_sha256": file_sha(result_path),
    }, files


def structured_record(seed: int, method: str) -> tuple[dict, list[Path]]:
    suffix = "AGGREGATE_BENDERS_STRUCTURED_ORACLE" if method == "Aggregate-BD" else "PRB_BENDERS"
    condition = f"ASC_XXL10_S{seed}_{suffix}"
    run = FORMAL_ROOT / "runs" / condition
    result_path = run / "result.json"
    result = read_json(result_path)
    provenance = read_json(run / "provenance.json")
    assert provenance["result_sha256"] == file_sha(result_path)
    assert provenance["trajectory_sha256"] == file_sha(run / "iteration_trajectory.json")
    preparation = read_json(FORMAL_ROOT / "instances" / "XXL10" / str(seed) / "preparation.json")
    files = sorted(path for path in run.iterdir() if path.is_file())
    return {
        "seed": seed,
        "method": method,
        "condition_id": condition,
        "classification": "CERTIFIED_SUCCESS",
        "solver_status": result["solver_status"],
        "exact_certification": result["exact_certification"],
        "cut_validity": True,
        "objective": result["final_objective"],
        "lower_bound": result["final_lower_bound"],
        "upper_bound": result["final_upper_bound"],
        "final_gap": result["relative_gap"],
        "core_time_seconds": result["total_core_solve_time"],
        "oracle_time_seconds": result["oracle_time"],
        "master_time_seconds": result["master_time"],
        "certification_time_seconds": result["certification_time"],
        "total_time_seconds": None,
        "iterations": result["iterations"],
        "cuts": result["cuts"],
        "peak_process_tree_memory_gib": result.get("peak_process_tree_memory_gib"),
        "worker_return_code": None,
        "stop_reason": None,
        "instance_hash": result["instance_hash"],
        "x0_hash": preparation["x0_hash"],
        "source_file": relative(result_path),
        "source_sha256": file_sha(result_path),
    }, files


def geometric_mean(values: list[float]) -> float:
    return exp(mean(log(value) for value in values))


def comparison(rows: list[dict], baseline: str, comparator: str) -> dict:
    lookup = {(row["seed"], row["method"]): row for row in rows}
    pairs = []
    for seed in SEEDS:
        left, right = lookup[seed, baseline], lookup[seed, comparator]
        if left["exact_certification"] and right["exact_certification"]:
            pairs.append((left["core_time_seconds"], right["core_time_seconds"]))
    ratios = [left / right for left, right in pairs]
    statistic, p_value = wilcoxon([left for left, _ in pairs], [right for _, right in pairs]) if len(pairs) >= 2 else (None, None)
    return {
        "baseline": baseline,
        "comparator": comparator,
        "paired_n": len(pairs),
        "geometric_mean_baseline_over_comparator": geometric_mean(ratios) if ratios else None,
        "comparator_wins": sum(right < left for left, right in pairs),
        "baseline_wins": sum(left < right for left, right in pairs),
        "ties": sum(left == right for left, right in pairs),
        "wilcoxon_statistic": statistic,
        "wilcoxon_two_sided_p": p_value,
    }


def source_manifest(paths: set[Path]) -> list[dict]:
    rows = []
    for path in sorted(paths):
        rows.append({"path": relative(path), "size_bytes": path.stat().st_size, "sha256": file_sha(path)})
    return rows


def markdown_table(rows: list[dict], fields: list[str]) -> str:
    def cell(value: object) -> str:
        if value is None:
            return "NA"
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)
    header = "| " + " | ".join(fields) + " |"
    divider = "| " + " | ".join("---" for _ in fields) + " |"
    return "\n".join([header, divider, *("| " + " | ".join(cell(row[field]) for field in fields) + " |" for row in rows)])


def build() -> dict:
    assert file_sha(ROOT / "experiments/run_direct_scaling.py") == DIRECT_CORE_SHA256
    records: list[dict] = []
    sources: set[Path] = set()
    for seed in SEEDS:
        for factory in (
            lambda value: direct_record(value),
            lambda value: ef_record(value),
            lambda value: structured_record(value, "Aggregate-BD"),
            lambda value: structured_record(value, "PRB-BD"),
        ):
            row, files = factory(seed)
            records.append(row)
            sources.update(files)
    assert len(records) == 40
    lookup = {(row["seed"], row["method"]): row for row in records}
    for seed in SEEDS:
        hashes = {lookup[seed, method]["instance_hash"] for method in METHODS}
        assert len(hashes) == 1
        certified_objectives = [lookup[seed, method]["objective"] for method in METHODS if lookup[seed, method]["exact_certification"]]
        assert max(certified_objectives) - min(certified_objectives) <= 2e-5
    assert sum(row["exact_certification"] for row in records if row["method"] == "Direct") == 3
    for method in METHODS[1:]:
        assert sum(row["exact_certification"] for row in records if row["method"] == method) == 10

    summaries = []
    for method in METHODS:
        selected = [row for row in records if row["method"] == method]
        certified = [row for row in selected if row["exact_certification"]]
        limited = [row for row in selected if not row["exact_certification"]]
        summaries.append({
            "method": method,
            "scheduled_n": 10,
            "executed_n": 10,
            "exact_certified_n": len(certified),
            "exact_certification_rate": len(certified) / 10,
            "time_or_monitor_limited_n": len(limited),
            "mean_core_time_certified_seconds": mean(row["core_time_seconds"] for row in certified),
            "mean_oracle_time_certified_seconds": mean(row["oracle_time_seconds"] for row in certified if row["oracle_time_seconds"] is not None) if method != "Direct" else None,
        })
    comparisons = [
        comparison(records, "Direct", "EF-BD"),
        comparison(records, "Direct", "Aggregate-BD"),
        comparison(records, "Direct", "PRB-BD"),
        comparison(records, "EF-BD", "Aggregate-BD"),
        comparison(records, "EF-BD", "PRB-BD"),
        comparison(records, "Aggregate-BD", "PRB-BD"),
    ]
    diagnostics = [row for row in records if row["method"] == "Direct"]
    manifest = source_manifest(sources)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "xxl10_four_method_records.csv", records)
    write_csv(OUTPUT / "xxl10_four_method_summary.csv", summaries)
    write_csv(OUTPUT / "xxl10_paired_comparisons.csv", comparisons)
    write_csv(OUTPUT / "xxl10_direct_diagnostics.csv", diagnostics)
    write_csv(OUTPUT / "xxl10_source_sha256_manifest.csv", manifest)
    source_rows = [{"method": row["method"], "seed": row["seed"], "source_file": row["source_file"], "source_sha256": row["source_sha256"]} for row in records]
    write_csv(OUTPUT / "xxl10_data_sources.csv", source_rows)

    summary_fields = ["method", "scheduled_n", "executed_n", "exact_certified_n", "exact_certification_rate", "time_or_monitor_limited_n", "mean_core_time_certified_seconds"]
    paper = [
        "# XXL10 four-method computational comparison",
        "",
        markdown_table(summaries, summary_fields),
        "",
        "Notes:",
        "",
        "- Direct has 3/10 exact-certified results. Its seven limited runs remain in the fixed denominator but are excluded from ordinary exact-pair speedups.",
        "- `DIRECT_XXL10_S20260922` remains in the historical batch report as `STOPPED_INTEGRITY_FAILURE`; the independent read-only audit classifies the preserved evidence as `TIME_LIMIT_NO_INCUMBENT`.",
        "- `DIRECT_XXL10_S20260927` ended at the outer monitor hard limit with Worker return code 15. No solver objective, bound, gap, or final solver status is inferred.",
        "- EF-BD, Aggregate-BD, and PRB-BD have 10/10 exact-certified results. Timing comparisons against Direct use only the three jointly exact-certified seeds.",
        "- Scaling V2 historical solver version remains not fully verifiable; Direct and EF-BD were recorded with Python 3.12.7 and Gurobi 13.0.1.",
        "",
        "## Paired comparisons",
        "",
        markdown_table(comparisons, list(comparisons[0])),
    ]
    (OUTPUT / "xxl10_four_method_paper_table.md").write_text("\n".join(paper) + "\n", encoding="utf-8")

    analysis_files = sorted(
        path for path in OUTPUT.iterdir()
        if path.is_file() and path.name != "xxl10_integrity_audit.json" and not path.name.endswith(".inspect.ndjson")
    )
    audit = {
        "schema": "xxl10_four_method_final_integrity_audit_v1",
        "generated_date": date.today().isoformat(),
        "optimization_calls": 0,
        "direct_core_runner_sha256": file_sha(ROOT / "experiments/run_direct_scaling.py"),
        "record_count": len(records),
        "counts": {row["method"]: {"executed": row["executed_n"], "exact_certified": row["exact_certified_n"]} for row in summaries},
        "direct_stage_counts": {"pilot": 1, "remaining9": 1, "remaining8": 8},
        "seed22_historical_report_preserved": True,
        "seed22_posthoc_classification": "TIME_LIMIT_NO_INCUMBENT",
        "seed27_monitor_hard_time_limit_preserved": True,
        "all_40_instance_identities_match": True,
        "all_available_provenance_hashes_match": True,
        "source_file_count": len(manifest),
        "source_bytes": sum(row["size_bytes"] for row in manifest),
        "analysis_sha256": {relative(path): file_sha(path) for path in analysis_files},
    }
    (OUTPUT / "xxl10_integrity_audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, allow_nan=False))
