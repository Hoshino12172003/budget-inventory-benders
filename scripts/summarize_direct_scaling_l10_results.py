from __future__ import annotations

import csv
import hashlib
import json
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
CANDIDATE_CONFIG = ROOT / "experiments/configs/formal/direct_scaling_xl10_low_memory_candidate_v1.yaml"
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
    candidate_config = runner.load_config(CANDIDATE_CONFIG)
    candidate_condition = runner.authorized_conditions(candidate_config)[0]
    authorized = runner.authorized_conditions(config)
    source_rows = read_csv(SOURCE / "algorithm_scaling_all_results.csv")
    source = {
        (row["seed"], row["method"]): row
        for row in source_rows
        if row["size"] == "L10" and row["method"] in METHODS
    }
    historical_attempt = DIRECT / "worker_logs/DIRECT_L10_S20260921/attempt-001"
    historical_monitor = json.loads(
        (historical_attempt / "resource_monitor.json").read_text(encoding="utf-8")
    )
    historical_attempt_files = {
        path.name: {"sha256": sha256(path), "size_bytes": path.stat().st_size}
        for path in sorted(historical_attempt.iterdir()) if path.is_file()
    }
    rows = []
    direct_records = []
    for condition in authorized:
        seed = str(condition["seed"])
        methods = {method: source[(seed, method)] for method in METHODS}
        run_root = DIRECT / "runs" / condition["condition_id"]
        result_path = run_root / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        provenance = json.loads((run_root / "provenance.json").read_text(encoding="utf-8"))
        attempt_roots = sorted((DIRECT / "worker_logs" / condition["condition_id"]).glob("attempt-*"))
        monitor_path = next(
            path / "resource_monitor.json"
            for path in reversed(attempt_roots)
            if (path / "resource_monitor.json").is_file()
        )
        monitor = json.loads(monitor_path.read_text(encoding="utf-8"))
        direct_records.append({
            "result": result,
            "provenance": provenance,
            "result_hash_matches": provenance.get("result_sha256") == sha256(result_path),
            "monitor": monitor,
        })
        objectives = [float(result["objective"]), *[float(row["final_objective"]) for row in methods.values()]]
        prb_time = float(methods["prb_benders"]["total_core_solve_time"])
        rows.append({
            "Seed": seed,
            "Direct status": result["solver_status"],
            "Direct exact certification": result["exact_certification"],
            "Direct objective": result["objective"],
            "Direct best bound": result["best_bound"],
            "Direct relative gap": result["mip_gap"],
            "Direct core time seconds": result["T_core_seconds"],
            "Direct monitored wall seconds": monitor["wall_clock_seconds"],
            "Direct peak process-tree GiB": monitor["peak_process_tree_memory_gib"],
            "Pure objective": methods["pure_benders"]["final_objective"],
            "Pure core time seconds": methods["pure_benders"]["total_core_solve_time"],
            "Aggregate+Structured objective": methods["aggregate_benders_structured_oracle"]["final_objective"],
            "Aggregate+Structured core time seconds": methods["aggregate_benders_structured_oracle"]["total_core_solve_time"],
            "PRB objective": methods["prb_benders"]["final_objective"],
            "PRB core time seconds": methods["prb_benders"]["total_core_solve_time"],
            "Four-method objective consistency": "PASS" if max(objectives) - min(objectives) <= 1e-4 else "FAIL",
            "Direct/PRB speedup": float(result["T_core_seconds"]) / prb_time,
            "Pure/PRB time ratio": float(methods["pure_benders"]["total_core_solve_time"]) / prb_time,
            "Aggregate/PRB time ratio": float(methods["aggregate_benders_structured_oracle"]["total_core_solve_time"]) / prb_time,
        })
    checks = {
        "authorization_exactly_10_l10": len(authorized) == 10 and all(row["size"] == "L10" for row in authorized),
        "ten_canonical_results_present": len(direct_records) == 10,
        "ten_exact_certified": all(
            row["result"]["solver_status"] == "OPTIMAL"
            and row["result"]["exact_certification"] is True
            and row["result"]["certification_status"] == "PASS"
            for row in direct_records
        ),
        "ten_archives_complete": all(row["provenance"].get("archive_complete") is True for row in direct_records),
        "ten_result_hashes_match": all(row["result_hash_matches"] for row in direct_records),
        "historical_first_resource_stop_preserved": historical_monitor["stop_reason"] == "RESOURCE_PROCESS_CAP",
        "source_l10_30_exact_certified": len(source) == 30 and all(row["exact_certification"] == "True" for row in source.values()),
        "four_method_objectives_consistent": all(row["Four-method objective consistency"] == "PASS" for row in rows),
        "xl10_candidate_protocol_exhausted": runner.verified_existing_result(
            candidate_config, candidate_condition, DIRECT
        ) is True,
    }
    audit = {
        "schema": "direct_scaling_l10_execution_audit_v2",
        "status": "COMPLETE_EXACT_CERTIFIED",
        "counts": {"authorized": 10, "attempted": 10, "exact_certified": 10, "resource_stop": 0, "unattempted": 0},
        "historical_first_resource_stop": historical_monitor,
        "config_hash": runner.canonical_hash(config),
        "execution_config_sha256": sha256(EXECUTION_CONFIG),
        "model_identity": runner.model_identity(),
        "execution_code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "historical_environment_limit": "Scaling V2 software environment remains NOT_VERIFIABLE; no exact environment identity is claimed.",
        "historical_first_attempt_files": historical_attempt_files,
        "checks": checks,
        "optimization_calls_by_summarizer": 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Direct L10 execution audit failed: {checks}")
    return audit, rows


def write_report(audit: dict) -> None:
    REPORT.write_text("\n".join([
        "# Direct scaling L10 execution report",
        "",
        "## Decision",
        "",
        "`COMPLETE_EXACT_CERTIFIED`",
        "",
        "All ten authorized L10 Direct conditions have canonical, hash-verified, exact-certified result archives.",
        "",
        "- Attempted: 10/10.",
        "- Exact-certified: 10/10.",
        "- Resource-stop final outcomes: 0/10.",
        "- Unattempted: 0/10.",
        "- The original 4-GiB resource-stop evidence for the first condition remains preserved as historical attempt evidence.",
        "- The XL10 low-memory candidate execution gate remains closed.",
        "",
        "No optimization is invoked by this reporting script.",
    ]) + "\n", encoding="utf-8")


def main() -> None:
    audit, rows = summarize()
    AUDIT.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_csv(TABLE, rows)
    write_report(audit)
    print(json.dumps({"status": audit["status"], "counts": audit["counts"], "optimization_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
