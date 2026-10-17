from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_direct_scaling as runner


SOURCE = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
DIRECT = ROOT / "experiments/results/direct_scaling_extension_v1"
AUDIT = ROOT / "artifacts/direct_scaling_l10_execution_audit.json"
TABLE = ROOT / "artifacts/table_direct_scaling_l10_four_method_comparison.csv"
REPORT = ROOT / "docs/direct_scaling_l10_execution_report.md"
EXECUTION_CONFIG = DIRECT / "execution_config.json"
METHODS = ("pure_benders", "aggregate_benders_structured_oracle", "prb_benders")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize() -> tuple[dict, list[dict]]:
    config = runner.load_config(EXECUTION_CONFIG)
    active_config = runner.load_config(runner.CONFIG)
    authorized = runner.authorized_conditions(config)
    source_rows = read_csv(SOURCE / "algorithm_scaling_all_results.csv")
    source = {
        (row["seed"], row["method"]): row
        for row in source_rows
        if row["size"] == "L10" and row["method"] in METHODS
    }
    attempt_root = DIRECT / "worker_logs/DIRECT_L10_S20260921/attempt-001"
    monitor = json.loads((attempt_root / "resource_monitor.json").read_text(encoding="utf-8"))
    progress = json.loads((attempt_root / "solver_progress.json").read_text(encoding="utf-8"))
    solver_log = (attempt_root / "solver.log").read_text(encoding="utf-8", errors="replace")
    time_limit_match = re.search(r"TimeLimit\s+([0-9.eE+-]+)", solver_log)
    dimensions_match = re.search(
        r"Optimize a model with (\d+) rows, (\d+) columns and (\d+) nonzeros",
        solver_log,
    )
    if dimensions_match is None:
        raise RuntimeError("solver log does not contain model dimensions")
    remaining_time_limit = float(time_limit_match.group(1)) if time_limit_match else None
    model_build_seconds = 900.0 - remaining_time_limit if remaining_time_limit is not None else None
    attempt_files = {
        path.name: {"sha256": sha256(path), "size_bytes": path.stat().st_size}
        for path in sorted(attempt_root.iterdir()) if path.is_file()
    }
    rows = []
    for condition in authorized:
        seed = str(condition["seed"])
        methods = {method: source[(seed, method)] for method in METHODS}
        objectives = [float(row["final_objective"]) for row in methods.values()]
        attempted = condition["seed"] == 20260921
        rows.append({
            "Seed": seed,
            "Direct status": "RESOURCE_PROCESS_CAP" if attempted else "UNATTEMPTED_AFTER_BATCH_SAFETY_STOP",
            "Direct exact certification": False,
            "Direct objective": "NOT_AVAILABLE",
            "Direct best bound": progress["best_bound"] if attempted else "NOT_AVAILABLE",
            "Direct relative gap": "NOT_AVAILABLE",
            "Direct core time seconds": "NOT_AVAILABLE",
            "Direct monitored wall seconds": monitor["wall_clock_seconds"] if attempted else "NOT_AVAILABLE",
            "Direct peak process-tree GiB": monitor["peak_process_tree_memory_gib"] if attempted else "NOT_AVAILABLE",
            "Pure objective": methods["pure_benders"]["final_objective"],
            "Pure core time seconds": methods["pure_benders"]["total_core_solve_time"],
            "Aggregate+Structured objective": methods["aggregate_benders_structured_oracle"]["final_objective"],
            "Aggregate+Structured core time seconds": methods["aggregate_benders_structured_oracle"]["total_core_solve_time"],
            "PRB objective": methods["prb_benders"]["final_objective"],
            "PRB core time seconds": methods["prb_benders"]["total_core_solve_time"],
            "Source three-method objective consistency": "PASS" if max(objectives) - min(objectives) <= 1e-4 else "FAIL",
            "Direct/PRB speedup": "NOT_AVAILABLE",
            "Pure/PRB time ratio": float(methods["pure_benders"]["total_core_solve_time"]) / float(methods["prb_benders"]["total_core_solve_time"]),
            "Aggregate/PRB time ratio": float(methods["aggregate_benders_structured_oracle"]["total_core_solve_time"]) / float(methods["prb_benders"]["total_core_solve_time"]),
        })
    checks = {
        "authorization_exactly_10_l10": len(authorized) == 10 and all(row["size"] == "L10" for row in authorized),
        "only_one_condition_attempted": (
            (not (DIRECT / "runs").exists() or not any((DIRECT / "runs").iterdir()))
            and len([
                path for path in (DIRECT / "worker_logs").iterdir()
                if path.is_dir() and any(path.glob("attempt-*"))
            ]) == 1
        ),
        "resource_stop_recorded": monitor["stop_reason"] == "RESOURCE_PROCESS_CAP",
        "process_cap_not_relaxed": config["resource_policy"]["maximum_process_tree_memory_gib_by_size"]["L10"] == 4,
        "remaining_nine_unattempted": sum(row["Direct status"].startswith("UNATTEMPTED") for row in rows) == 9,
        "source_l10_30_exact_certified": len(source) == 30 and all(row["exact_certification"] == "True" for row in source.values()),
        "source_objectives_consistent": all(row["Source three-method objective consistency"] == "PASS" for row in rows),
        "no_direct_result_misrepresented": all(row["Direct objective"] == "NOT_AVAILABLE" for row in rows),
        "execution_gate_closed_after_stop": active_config["formal_run_authorized"] is False,
    }
    audit = {
        "schema": "direct_scaling_l10_execution_audit_v1",
        "status": "BATCH_STOPPED_AFTER_RESOURCE_CAP",
        "counts": {"authorized": 10, "attempted": 1, "exact_certified": 0, "resource_stop": 1, "unattempted": 9},
        "attempted_condition": "DIRECT_L10_S20260921",
        "stop_scope": "Remaining L10 conditions were not started because the first same-scale Direct model exceeded the unchanged process-tree cap.",
        "resource_monitor": monitor,
        "last_solver_progress": progress,
        "available_incumbent": None if progress["incumbent"] >= 1e99 else progress["incumbent"],
        "available_best_bound": progress["best_bound"],
        "model_build_seconds_derived_from_logged_remaining_time_limit": model_build_seconds,
        "solver_log_model_dimensions": {
            "variables": int(dimensions_match.group(2)),
            "constraints": int(dimensions_match.group(1)),
            "nonzeros": int(dimensions_match.group(3)),
        },
        "config_hash": runner.canonical_hash(config),
        "execution_config_sha256": sha256(EXECUTION_CONFIG),
        "model_identity": runner.model_identity(),
        "execution_code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "historical_environment_limit": "Scaling V2 software environment remains NOT_VERIFIABLE; no exact environment identity is claimed.",
        "attempt_files": attempt_files,
        "checks": checks,
        "optimization_calls_by_summarizer": 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Direct L10 execution audit failed: {checks}")
    return audit, rows


def write_report(audit: dict) -> None:
    monitor = audit["resource_monitor"]
    progress = audit["last_solver_progress"]
    REPORT.write_text("\n".join([
        "# Direct scaling L10 execution report",
        "",
        "## Decision",
        "",
        "`BATCH_STOPPED_AFTER_RESOURCE_CAP`",
        "",
        "The authorized batch did not complete. The first L10 condition reached the unchanged 4-GiB process-tree cap, and the remaining nine same-scale conditions were not started because continuing presented the same model-scale memory risk.",
        "",
        "- Attempted: 1/10 (`DIRECT_L10_S20260921`).",
        "- Exact-certified: 0/10.",
        "- Resource-stop: 1/10.",
        "- Unattempted after safety stop: 9/10.",
        f"- Peak process-tree RSS: {monitor['peak_process_tree_memory_gib']:.6f} GiB.",
        f"- Monitored wall time: {monitor['wall_clock_seconds']:.6f} s.",
        f"- Last solver checkpoint: runtime {progress['runtime_seconds']:.6f} s, no feasible incumbent, best bound {progress['best_bound']:.12f}.",
        "- No tolerance, model, parameter, or resource threshold was changed; the condition was not retried.",
        "- No XL10 or XXL10 condition was started.",
        "- The active formal execution gate was closed after the resource stop.",
        "",
        "The solver log, stdout/stderr, resource monitor, and last available solver-progress checkpoint are retained under the formal Direct output root. No `result.json` is synthesized because the worker was terminated by the external hard resource guard before solver termination and certification.",
    ]) + "\n", encoding="utf-8")


def main() -> None:
    audit, rows = summarize()
    AUDIT.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_csv(TABLE, rows)
    write_report(audit)
    print(json.dumps({"status": audit["status"], "counts": audit["counts"], "peak_gib": audit["resource_monitor"]["peak_process_tree_memory_gib"], "optimization_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
