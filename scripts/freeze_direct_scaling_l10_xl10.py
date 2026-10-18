from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_direct_scaling as runner


DIRECT = ROOT / "experiments/results/direct_scaling_extension_v1"
SCALING = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
ARTIFACTS = ROOT / "artifacts"
DOC = ROOT / "docs/direct_scaling_l10_xl10_freeze_decision.md"
SIZES = ("L10", "XL10")
SEEDS = tuple(range(20260921, 20260931))
METHODS = ("pure_benders", "aggregate_benders_structured_oracle", "prb_benders")
STATUS_NAMES = ("CERTIFIED", "RESOURCE_FAILURE", "TIME_FAILURE", "NUMERICAL_CERTIFICATION_FAILURE", "UNEXECUTED")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def config_index() -> tuple[dict[str, tuple[Path, dict]], dict[str, dict]]:
    by_hash = {}
    by_protocol = {}
    paths = list((ROOT / "experiments/configs/formal").glob("direct_scaling*.yaml"))
    paths.append(DIRECT / "execution_config.json")
    for path in paths:
        config = runner.load_config(path)
        if "fixed_scientific_parameters" not in config:
            continue
        by_hash[runner.canonical_hash(config)] = (path, config)
        if config.get("resource_protocol_id"):
            by_protocol[config["resource_protocol_id"]] = config
    return by_hash, by_protocol


def audit_attempts(condition_id: str) -> list[dict]:
    rows = []
    attempt_root = DIRECT / "worker_logs" / condition_id
    for attempt in sorted(attempt_root.glob("attempt-*")) if attempt_root.is_dir() else []:
        monitor_path = attempt / "resource_monitor.json"
        monitor = read_json(monitor_path) if monitor_path.is_file() else {}
        progress_path = attempt / "solver_progress.json"
        progress = read_json(progress_path) if progress_path.is_file() else {}
        progress_gap = None
        if progress.get("incumbent") is not None and progress.get("best_bound") is not None:
            incumbent = float(progress["incumbent"])
            if abs(incumbent) < 1e99:
                progress_gap = abs(incumbent - float(progress["best_bound"])) / max(abs(incumbent), 1.0)
        rows.append({
            "attempt": attempt.name,
            "resource_protocol_id": monitor.get("resource_protocol_id"),
            "stop_reason": monitor.get("stop_reason"),
            "worker_return_code": monitor.get("worker_return_code"),
            "peak_process_tree_memory_gib": monitor.get("peak_process_tree_memory_gib"),
            "wall_clock_seconds": monitor.get("wall_clock_seconds"),
            "progress_incumbent": progress.get("incumbent"),
            "progress_best_bound": progress.get("best_bound"),
            "progress_relative_gap": progress_gap,
            "progress_is_exact_certification": False,
            "files": [
                {"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in sorted(attempt.iterdir()) if path.is_file()
            ],
        })
    return rows


def audit_condition(size: str, seed: int, configs: dict[str, tuple[Path, dict]]) -> tuple[dict, list[dict]]:
    condition_id = f"DIRECT_{size}_S{seed}"
    attempts = audit_attempts(condition_id)
    run_root = DIRECT / "runs" / condition_id
    if not run_root.is_dir():
        resource_stops = [row for row in attempts if row["stop_reason"] in {"RESOURCE_PROCESS_CAP", "RESOURCE_SYSTEM_CAP"}]
        time_stops = [row for row in attempts if row["stop_reason"] == "MONITOR_HARD_TIME_LIMIT"]
        status = "RESOURCE_FAILURE" if resource_stops else "TIME_FAILURE" if time_stops else "UNEXECUTED"
        return {
            "condition_id": condition_id,
            "size": size,
            "seed": seed,
            "status": status,
            "canonical_result": None,
            "attempts": attempts,
        }, []

    result_path = run_root / "result.json"
    provenance_path = run_root / "provenance.json"
    result = read_json(result_path)
    provenance = read_json(provenance_path)
    if result.get("config_hash") not in configs:
        raise RuntimeError(f"unknown Direct config hash for {condition_id}: {result.get('config_hash')}")
    config_path, config = configs[result["config_hash"]]
    condition = next(row for row in runner.conditions(config) if row["condition_id"] == condition_id)
    instance, preparation, input_hashes = runner.verified_input(config, condition)
    checks = {
        "condition_id": result.get("condition_id") == condition_id,
        "size": result.get("size") == size,
        "seed": result.get("seed") == seed,
        "instance_hash": result.get("instance_hash") == preparation["instance_hash"] == runner.canonical_hash(instance.to_dict()),
        "instance_file_sha256": provenance.get("instance_sha256") == input_hashes["instance_sha256"],
        "preparation_file_sha256": provenance.get("preparation_sha256") == input_hashes["preparation_sha256"],
        "result_sha256": provenance.get("result_sha256") == sha256(result_path),
        "archive_complete": provenance.get("archive_complete") is True,
        "model_identity": provenance.get("model_identity", {}).get("sha256") == result.get("model_identity"),
    }
    artifact_hashes = []
    for provenance_key, filename in (
        ("first_stage_solution_sha256", "first_stage_solution.json"),
        ("solver_log_sha256", "solver.log"),
        ("solver_progress_sha256", "solver_progress.json"),
    ):
        path = run_root / filename
        checks[provenance_key] = provenance.get(provenance_key) == sha256(path)
        artifact_hashes.append({"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)})
    if not all(checks.values()):
        raise RuntimeError(f"canonical archive audit failed for {condition_id}: {checks}")
    certified = result.get("solver_status") == "OPTIMAL" and result.get("exact_certification") is True and result.get("certification_status") == "PASS"
    status = "CERTIFIED" if certified else "NUMERICAL_CERTIFICATION_FAILURE"
    canonical = {
        "solver_status": result.get("solver_status"),
        "exact_certification": result.get("exact_certification"),
        "certification_status": result.get("certification_status"),
        "objective": result.get("objective"),
        "best_bound": result.get("best_bound"),
        "mip_gap": result.get("mip_gap"),
        "T_core_seconds": result.get("T_core_seconds"),
        "config_path": config_path.relative_to(ROOT).as_posix(),
        "config_hash": result["config_hash"],
        "code_commit": result.get("code_commit"),
        "instance_hash": result["instance_hash"],
        "result_sha256": sha256(result_path),
        "provenance_sha256": sha256(provenance_path),
        "checks": checks,
    }
    audit_rows = [
        {"condition_id": condition_id, "artifact_role": "result", "path": result_path.relative_to(ROOT).as_posix(), "size_bytes": result_path.stat().st_size, "sha256": sha256(result_path)},
        {"condition_id": condition_id, "artifact_role": "provenance", "path": provenance_path.relative_to(ROOT).as_posix(), "size_bytes": provenance_path.stat().st_size, "sha256": sha256(provenance_path)},
        *[{"condition_id": condition_id, "artifact_role": "canonical_artifact", **row} for row in artifact_hashes],
    ]
    return {"condition_id": condition_id, "size": size, "seed": seed, "status": status, "canonical_result": canonical, "attempts": attempts}, audit_rows


def build_freeze() -> tuple[dict, list[dict], list[dict], list[dict]]:
    configs, protocols = config_index()
    conditions = []
    sha_rows = []
    for size in SIZES:
        for seed in SEEDS:
            condition, canonical_rows = audit_condition(size, seed, configs)
            conditions.append(condition)
            sha_rows.extend(canonical_rows)
            for attempt in condition["attempts"]:
                sha_rows.extend({"condition_id": condition["condition_id"], "artifact_role": attempt["attempt"], **row} for row in attempt["files"])

    batch_root = DIRECT / "batch_reports" / "DIRECT_XL10_REMAINING7_8GIB_V1"
    batch_reports = [
        {"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(batch_root.iterdir()) if path.is_file()
    ]
    sha_rows.extend(
        {"condition_id": "DIRECT_XL10_REMAINING7_BATCH", "artifact_role": "batch_report", **row}
        for row in batch_reports
    )

    failure = next(row for row in conditions if row["condition_id"] == "DIRECT_XL10_S20260924")
    if failure["status"] != "RESOURCE_FAILURE" or [row["stop_reason"] for row in failure["attempts"]] != ["RESOURCE_PROCESS_CAP", "RESOURCE_PROCESS_CAP"]:
        raise RuntimeError("XL10 seed 20260924 does not contain the two required resource-cap failures")
    attempt002 = failure["attempts"][1]
    if attempt002["progress_relative_gap"] is None or not 0.0037 < attempt002["progress_relative_gap"] < 0.0040:
        raise RuntimeError("XL10 seed 20260924 attempt-002 progress gap is missing or unexpected")

    source_rows = read_csv(SCALING / "algorithm_scaling_all_results.csv")
    source = {(row["size"], int(row["seed"]), row["method"]): row for row in source_rows}
    pairs = []
    for direct in conditions:
        if direct["status"] != "CERTIFIED":
            continue
        method_rows = [source[(direct["size"], direct["seed"], method)] for method in METHODS]
        if not all(row["solver_status"] == "OPTIMAL" and row["exact_certification"] == "True" for row in method_rows):
            raise RuntimeError(f"non-certified scaling comparator for {direct['condition_id']}")
        canonical = direct["canonical_result"]
        objectives = [float(canonical["objective"]), *[float(row["final_objective"]) for row in method_rows]]
        if max(objectives) - min(objectives) > 1e-4:
            raise RuntimeError(f"four-method objective mismatch for {direct['condition_id']}")
        times = {row["method"]: float(row["total_core_solve_time"]) for row in method_rows}
        pairs.append({
            "size": direct["size"],
            "seed": direct["seed"],
            "direct_condition_id": direct["condition_id"],
            "objective_spread": max(objectives) - min(objectives),
            "direct_core_seconds": canonical["T_core_seconds"],
            "pure_core_seconds": times["pure_benders"],
            "aggregate_structured_core_seconds": times["aggregate_benders_structured_oracle"],
            "prb_core_seconds": times["prb_benders"],
            "direct_to_prb_time_ratio": float(canonical["T_core_seconds"]) / times["prb_benders"],
            "pure_to_prb_time_ratio": times["pure_benders"] / times["prb_benders"],
            "aggregate_to_prb_time_ratio": times["aggregate_benders_structured_oracle"] / times["prb_benders"],
            "valid_four_method_pair": True,
        })
    if len(pairs) != 19 or any(row["seed"] == 20260924 and row["size"] == "XL10" for row in pairs):
        raise RuntimeError("valid four-method pairing set is not the frozen 19-condition set")

    summaries = []
    for size in SIZES:
        scoped = [row for row in conditions if row["size"] == size]
        paired = [row for row in pairs if row["size"] == size]
        counts = {name: sum(row["status"] == name for row in scoped) for name in STATUS_NAMES}
        summaries.append({
            "size": size,
            "planned_conditions": 10,
            "direct_certified": counts["CERTIFIED"],
            "direct_resource_failure": counts["RESOURCE_FAILURE"],
            "direct_time_failure": counts["TIME_FAILURE"],
            "direct_numerical_certification_failure": counts["NUMERICAL_CERTIFICATION_FAILURE"],
            "direct_unexecuted": counts["UNEXECUTED"],
            "direct_completion_rate": counts["CERTIFIED"] / 10,
            "valid_four_method_pairs": len(paired),
            "direct_mean_core_seconds_paired": statistics.fmean(float(row["direct_core_seconds"]) for row in paired),
            "pure_mean_core_seconds_paired": statistics.fmean(float(row["pure_core_seconds"]) for row in paired),
            "aggregate_structured_mean_core_seconds_paired": statistics.fmean(float(row["aggregate_structured_core_seconds"]) for row in paired),
            "prb_mean_core_seconds_paired": statistics.fmean(float(row["prb_core_seconds"]) for row in paired),
            "mean_direct_to_prb_time_ratio_paired": statistics.fmean(float(row["direct_to_prb_time_ratio"]) for row in paired),
            "mean_pure_to_prb_time_ratio_paired": statistics.fmean(float(row["pure_to_prb_time_ratio"]) for row in paired),
            "mean_aggregate_to_prb_time_ratio_paired": statistics.fmean(float(row["aggregate_to_prb_time_ratio"]) for row in paired),
        })

    used_protocol_ids = sorted({attempt["resource_protocol_id"] for row in conditions for attempt in row["attempts"] if attempt["resource_protocol_id"]})
    protocol_rows = [{
        "resource_protocol_id": protocol_id,
        "historical_formal_run_authorized": protocols[protocol_id].get("formal_run_authorized"),
        "solver_parameters": protocols[protocol_id]["solver_parameters"],
        "resource_policy": protocols[protocol_id]["resource_policy"],
    } for protocol_id in used_protocol_ids]
    counts = {name: sum(row["status"] == name for row in conditions) for name in STATUS_NAMES}
    manifest = {
        "schema": "direct_scaling_l10_xl10_freeze_v1",
        "freeze_id": "DIRECT_SCALING_L10_XL10_FREEZE_V1",
        "decision": "L10 and XL10 are frozen; no further XL10 Direct retries are authorized.",
        "optimization_calls": 0,
        "scope": {"included_scales": ["L10", "XL10"], "planned_conditions": 20, "xxl10": "NOT_EXECUTED_OUTSIDE_COMPLETED_SCALE_SCOPE"},
        "counts": counts,
        "valid_four_method_pairs": len(pairs),
        "xl10_terminal_failure": {
            "condition_id": failure["condition_id"],
            "attempts": [row["attempt"] for row in failure["attempts"]],
            "stop_reasons": [row["stop_reason"] for row in failure["attempts"]],
            "attempt_002_progress_relative_gap": attempt002["progress_relative_gap"],
            "attempt_002_progress_gap_percent": 100 * attempt002["progress_relative_gap"],
            "interpretation": "UNVERIFIED_INTERRUPTED_SOLVER_PROGRESS_NOT_A_FINAL_EXACT_GAP",
        },
        "environment_limit": "Scaling V2 historical solver version remains NOT_VERIFIABLE; exact software-environment identity with the Direct runs is not claimed.",
        "protocols": protocol_rows,
        "batch_reports": batch_reports,
        "conditions": conditions,
    }
    return manifest, sha_rows, pairs, summaries


def write_outputs() -> dict:
    manifest, sha_rows, pairs, summaries = build_freeze()
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "direct_scaling_l10_xl10_freeze_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_csv(ARTIFACTS / "direct_scaling_l10_xl10_sha256_audit.csv", sha_rows)
    write_csv(ARTIFACTS / "direct_scaling_l10_xl10_valid_pairs.csv", pairs)
    write_csv(ARTIFACTS / "direct_scaling_l10_xl10_scale_summary.csv", summaries)
    summary_lines = [
        "# Direct scaling L10 and XL10 freeze decision",
        "",
        "## Decision",
        "",
        "L10 and XL10 are formally frozen. No further XL10 Direct retries are authorized. XXL10 has not been executed and is outside the completed-scale statistics.",
        "",
        "## Frozen counts",
        "",
        "- L10: 10/10 exact-certified.",
        "- XL10: 9/10 exact-certified; 1/10 resource failure.",
        "- Combined completed-scale scope: 19 certified, 1 resource failure, 0 time failures, 0 numerical-certification failures, 0 unexecuted.",
        "- Valid four-method pairs: 19. `DIRECT_XL10_S20260924` is excluded from paired timing but retained in the ten-condition XL10 completion denominator.",
        "",
        "## Terminal XL10 failure",
        "",
        "`DIRECT_XL10_S20260924` attempt-001 and attempt-002 both stopped at `RESOURCE_PROCESS_CAP`. Attempt-002's last solver-progress record implies a 0.382551% gap; this is interrupted, unverified progress and is not a final exact or certified gap.",
        "",
        "## Comparability boundary",
        "",
        "Direct protocols and their resource limits, Method, and Threads settings are preserved in the manifest. The historical Scaling V2 solver version remains `NOT_VERIFIABLE`; exact software-environment identity is not claimed.",
        "",
        "No optimizer or instance generator is invoked by the freeze script.",
    ]
    DOC.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    frozen = write_outputs()
    print(json.dumps({"freeze_id": frozen["freeze_id"], "counts": frozen["counts"], "valid_four_method_pairs": frozen["valid_four_method_pairs"], "optimization_calls": 0}, indent=2))
