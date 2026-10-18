from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_direct_scaling as runner


CONFIG = ROOT / "experiments/configs/formal/direct_scaling_xl10_remaining7_8gib_v1.yaml"
OUTPUT_ROOT = ROOT / "experiments/results/direct_scaling_extension_v1"
XL10_CANDIDATE_CONFIG = ROOT / "experiments/configs/formal/direct_scaling_xl10_low_memory_candidate_v1.yaml"
XL10_REMAINING9_CONFIG = ROOT / "experiments/configs/formal/direct_scaling_xl10_remaining9_v1.yaml"
PROTOCOL_ID = "DIRECT_XL10_REMAINING7_8GIB_V1"
CONDITION_IDS = [f"DIRECT_XL10_S{seed}" for seed in range(20260924, 20260931)]
EXPECTED_ATTEMPTS = {CONDITION_IDS[0]: "attempt-002", **{item: "attempt-001" for item in CONDITION_IDS[1:]}}
RESOURCE_FAILURES = {"RESOURCE_PROCESS_CAP", "RESOURCE_SYSTEM_CAP", "MONITOR_HARD_TIME_LIMIT"}


def direct_solver_processes() -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or []).lower()
            name = (process.info.get("name") or "").lower()
        except psutil.Error:
            continue
        if ("run_direct_scaling.py" in command and "--worker" in command) or name.startswith("gurobi"):
            found.append({"pid": process.info["pid"], "name": name, "command": command})
    return found


def assert_no_solver_processes() -> None:
    active = direct_solver_processes()
    if active:
        raise RuntimeError(f"INTEGRITY_FAILURE: lingering Direct/Gurobi processes: {active}")


def build_plan(config: dict, output_root: Path) -> list[dict]:
    authorized = runner.authorized_conditions(config)
    if [row["condition_id"] for row in authorized] != CONDITION_IDS:
        raise RuntimeError("INTEGRITY_FAILURE: remaining-seven authorization scope changed")
    plan = [
        {
            **condition,
            "next_attempt": f"attempt-{runner.next_attempt_number(output_root, condition['condition_id']):03d}",
        }
        for condition in authorized
    ]
    actual = {row["condition_id"]: row["next_attempt"] for row in plan}
    if actual != EXPECTED_ATTEMPTS:
        raise RuntimeError(f"INTEGRITY_FAILURE: attempt identities changed: {actual}")
    return plan


def audit_archive(config: dict, condition: dict, output_root: Path) -> dict:
    run_root = output_root / "runs" / condition["condition_id"]
    result_path = run_root / "result.json"
    provenance_path = run_root / "provenance.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    instance, preparation, _ = runner.verified_input(config, condition)
    checks = {
        "condition": result.get("condition_id") == condition["condition_id"],
        "size": result.get("size") == condition["size"],
        "seed": result.get("seed") == condition["seed"],
        "config": result.get("config_hash") == runner.canonical_hash(config),
        "instance": result.get("instance_hash") == preparation["instance_hash"] == runner.canonical_hash(instance.to_dict()),
        "archive_complete": provenance.get("archive_complete") is True,
        "result_hash": provenance.get("result_sha256") == runner.file_sha256(result_path),
    }
    for key, filename in (
        ("first_stage_solution_sha256", "first_stage_solution.json"),
        ("solver_log_sha256", "solver.log"),
        ("solver_progress_sha256", "solver_progress.json"),
    ):
        if key in provenance:
            checks[key] = provenance[key] == runner.file_sha256(run_root / filename)
    if not all(checks.values()):
        raise RuntimeError(f"archive identity failure: {checks}")
    return result


def audit_prior_certified_results(output_root: Path) -> list[dict]:
    audits = []
    for seed, config_path, expected_attempt in (
        (20260921, XL10_CANDIDATE_CONFIG, "attempt-002"),
        (20260922, XL10_REMAINING9_CONFIG, "attempt-001"),
        (20260923, XL10_REMAINING9_CONFIG, "attempt-001"),
    ):
        config = runner.load_config(config_path)
        condition = next(row for row in runner.conditions(config) if row["condition_id"] == f"DIRECT_XL10_S{seed}")
        result = audit_archive(config, condition, output_root)
        monitor_path = output_root / "worker_logs" / condition["condition_id"] / expected_attempt / "resource_monitor.json"
        monitor = json.loads(monitor_path.read_text(encoding="utf-8"))
        checks = {
            "attempt": monitor.get("attempt") == expected_attempt,
            "worker_return_code": monitor.get("worker_return_code") == 0,
            "stop_reason": monitor.get("stop_reason") is None,
            "solver_status": result.get("solver_status") == "OPTIMAL",
            "exact_certification": result.get("exact_certification") is True,
            "certification_status": result.get("certification_status") == "PASS",
        }
        if not all(checks.values()):
            raise RuntimeError(f"prior XL10 certification audit failed for {condition['condition_id']}: {checks}")
        audits.append({
            "condition_id": condition["condition_id"],
            "attempt": expected_attempt,
            "solver_status": result["solver_status"],
            "exact_certification": result["exact_certification"],
            "objective": result["objective"],
            "T_core_seconds": result["T_core_seconds"],
            "peak_process_tree_memory_gib": monitor["peak_process_tree_memory_gib"],
            "result_sha256": runner.file_sha256(output_root / "runs" / condition["condition_id"] / "result.json"),
            "provenance_sha256": runner.file_sha256(output_root / "runs" / condition["condition_id"] / "provenance.json"),
            "resource_monitor_sha256": runner.file_sha256(monitor_path),
        })
    return audits


def latest_monitor(condition: dict, output_root: Path) -> dict:
    attempts = sorted((output_root / "worker_logs" / condition["condition_id"]).glob("attempt-*"))
    if not attempts:
        raise RuntimeError("missing attempt evidence")
    path = attempts[-1] / "resource_monitor.json"
    return json.loads(path.read_text(encoding="utf-8"))


def classify_condition(config: dict, condition: dict, output_root: Path) -> dict:
    try:
        monitor = latest_monitor(condition, output_root)
        if monitor.get("resource_protocol_id") != PROTOCOL_ID:
            raise RuntimeError("resource protocol identity mismatch")
        run_root = output_root / "runs" / condition["condition_id"]
        if run_root.exists():
            result = audit_archive(config, condition, output_root)
            if result.get("solver_status") == "OPTIMAL" and result.get("exact_certification") is True:
                if monitor.get("stop_reason") is not None or monitor.get("worker_return_code") != 0:
                    raise RuntimeError("successful archive has failed resource monitor")
                status = "SUCCESS"
            elif result.get("solver_status") == "TIME_LIMIT":
                status = "RESOURCE_OR_TIME_FAILURE"
            else:
                raise RuntimeError("solver or certification status is not an allowed final state")
        elif monitor.get("stop_reason") in RESOURCE_FAILURES:
            result = {}
            status = "RESOURCE_OR_TIME_FAILURE"
        else:
            raise RuntimeError("no canonical archive and no recognized resource/time stop")
        return {
            "condition_id": condition["condition_id"],
            "attempt": monitor["attempt"],
            "status": status,
            "solver_status": result.get("solver_status"),
            "exact_certification": result.get("exact_certification"),
            "stop_reason": monitor.get("stop_reason"),
            "peak_process_tree_memory_gib": monitor.get("peak_process_tree_memory_gib"),
            "wall_clock_seconds": monitor.get("wall_clock_seconds"),
            "objective": result.get("objective"),
            "best_bound": result.get("best_bound"),
            "mip_gap": result.get("mip_gap"),
            "detail": "",
        }
    except Exception as exc:
        return {
            "condition_id": condition["condition_id"],
            "attempt": f"attempt-{runner.next_attempt_number(output_root, condition['condition_id']) - 1:03d}",
            "status": "INTEGRITY_FAILURE",
            "solver_status": None,
            "exact_certification": None,
            "stop_reason": None,
            "peak_process_tree_memory_gib": None,
            "wall_clock_seconds": None,
            "objective": None,
            "best_bound": None,
            "mip_gap": None,
            "detail": f"{type(exc).__name__}: {exc}",
        }


def write_status(output_root: Path, rows: list[dict]) -> None:
    target = output_root / "batch_reports" / PROTOCOL_ID
    target.mkdir(parents=True, exist_ok=True)
    table = target / "condition_status.csv"
    with table.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("SUCCESS", "RESOURCE_OR_TIME_FAILURE", "INTEGRITY_FAILURE", "UNEXECUTED")
    }
    counts.update({
        "certified": counts["SUCCESS"],
        "resource_failure": sum(
            row["stop_reason"] in {"RESOURCE_PROCESS_CAP", "RESOURCE_SYSTEM_CAP"} for row in rows
        ),
        "time_failure": sum(
            row["solver_status"] == "TIME_LIMIT" or row["stop_reason"] == "MONITOR_HARD_TIME_LIMIT"
            for row in rows
        ),
    })
    (target / "summary.json").write_text(
        json.dumps({"resource_protocol_id": PROTOCOL_ID, "denominator": 7, "counts": counts, "rows": rows}, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def execute_batch(config_path: Path, config: dict, output_root: Path) -> None:
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("FORMAL_DIRECT_EXECUTION_NOT_AUTHORIZED")
    plan = build_plan(config, output_root)
    assert_no_solver_processes()
    rows = [
        {"condition_id": item["condition_id"], "attempt": item["next_attempt"], "status": "UNEXECUTED",
         "solver_status": None, "exact_certification": None, "stop_reason": None,
         "peak_process_tree_memory_gib": None, "wall_clock_seconds": None, "objective": None,
         "best_bound": None, "mip_gap": None, "detail": ""}
        for item in plan
    ]
    write_status(output_root, rows)
    for index, condition in enumerate(plan):
        runner.validate_execution_gate(config, condition, output_root)
        assert_no_solver_processes()
        execution_error = None
        try:
            runner.run_monitored(config_path, config, condition, output_root)
        except Exception as exc:
            execution_error = f"{type(exc).__name__}: {exc}"
        assert_no_solver_processes()
        rows[index] = classify_condition(config, condition, output_root)
        if execution_error:
            rows[index]["detail"] = execution_error + ("; " + rows[index]["detail"] if rows[index]["detail"] else "")
        write_status(output_root, rows)
        if rows[index]["status"] == "INTEGRITY_FAILURE":
            raise RuntimeError(f"batch stopped after integrity failure: {rows[index]}")
        if rows[index]["status"] == "RESOURCE_OR_TIME_FAILURE" and index + 1 < len(plan):
            assert_no_solver_processes()
            runner.validate_execution_gate(config, plan[index + 1], output_root)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    config = runner.load_config(args.config)
    if args.dry_run:
        plan = build_plan(config, args.output_root)
        prior_audit = audit_prior_certified_results(args.output_root)
        environment = runner.validate_environment(config)
        print(json.dumps({
            "optimization_calls": 0,
            "resource_protocol_id": config["resource_protocol_id"],
            "formal_run_authorized": config["formal_run_authorized"],
            "formal_execution_permitted": config["formal_run_authorized"] is True and environment["pass"],
            "denominator": len(plan),
            "conditions": [{"condition_id": row["condition_id"], "attempt": row["next_attempt"]} for row in plan],
            "prior_certified_results": prior_audit,
            "resource_policy": config["resource_policy"],
            "solver_parameters": config["solver_parameters"],
            "current_available_memory_gib": psutil.virtual_memory().available / 2**30,
            "current_free_disk_gib": shutil.disk_usage(args.output_root.parent).free / 2**30,
            "environment": environment,
            "active_direct_or_gurobi_processes": direct_solver_processes(),
        }, indent=2))
        return
    execute_batch(args.config, config, args.output_root)


if __name__ == "__main__":
    main()
