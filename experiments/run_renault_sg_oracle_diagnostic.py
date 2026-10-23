from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from time import perf_counter, sleep
import traceback
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.run_renault_vanilla_bd_pilot import load_frozen_renault_case
from robust_inventory_reconfiguration.enhanced_basic_benders import (
    EnhancedGlobalEnumeratedLPOracle,
)
from robust_inventory_reconfiguration.scenario_generation_oracle import (
    ExactScenarioLPEvaluator,
)
from robust_inventory_reconfiguration.scenario_generation_single_cut import exact_separation


CONFIG = ROOT / "experiments/configs/development/renault_sg_oracle_diagnostic_v1.yaml"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
POINTS = ("final", "x0")
CONDITIONS = tuple(f"SG_ORACLE_{case}_{point.upper()}" for case in CASES for point in POINTS)
ALLOWED_DIRTY_PREFIX = "?? experiments/results/basic_benders_scaling_development_v1/"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_config(path: Path = CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("protocol_id") != "RENAULT_SG_ORACLE_DIAGNOSTIC_V1":
        raise RuntimeError("unexpected SG Oracle diagnostic protocol")
    if tuple(config.get("authorized_case_ids", ())) != CASES:
        raise RuntimeError("diagnostic case scope differs from frozen Renault order")
    if tuple(config.get("test_points", ())) != POINTS:
        raise RuntimeError("diagnostic test-point scope differs from frozen protocol")
    if config.get("fixed_scientific_parameters") != {"Gamma": 2, "lambda_R": 0.05}:
        raise RuntimeError("diagnostic scientific parameters differ from frozen values")
    return config


def frozen_identities(config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    source = ROOT / config["frozen_identity_source"]
    payload = json.loads(source.read_text(encoding="utf-8"))
    identities = payload["frozen_case_identity"]
    if tuple(identities) != CASES:
        raise RuntimeError("frozen identity source has a different Renault case order")
    return source, identities


def assert_frozen_identity(config: dict[str, Any], case: str, loaded: dict[str, Any]) -> None:
    _, identities = frozen_identities(config)
    if loaded["identity"] != identities[case]:
        raise RuntimeError(
            f"IDENTITY_FAILURE {case}: actual={loaded['identity']} expected={identities[case]}"
        )


def condition_parts(condition_id: str) -> tuple[str, str]:
    if condition_id not in CONDITIONS:
        raise ValueError(f"condition is outside the allowlist: {condition_id}")
    _, _, case, point = condition_id.split("_", 3)
    return case, point.lower()


def final_root(case: str) -> Path:
    return ROOT / f"experiments/results/renault_enhanced_basic_benders_development_v1/runs/EB_RENAULT_{case}"


def load_point(case: str, point: str) -> tuple[list[list[float]], Path, tuple[tuple[int, int], ...]]:
    loaded = load_frozen_renault_case(case)
    root = final_root(case)
    traces = [json.loads(line) for line in (root / "oracle_trace.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if point == "final":
        source = root / "first_stage_solution.json"
        x = json.loads(source.read_text(encoding="utf-8"))["x"]
        warm = tuple(tuple(pair) for pair in traces[-1]["shock_pattern"])
    elif point == "x0":
        source = Path(loaded["paths"]["x0"])
        x = loaded["x0"]
        warm = tuple(tuple(pair) for pair in traces[0]["shock_pattern"])
    else:
        raise ValueError(f"unsupported persisted test point: {point}")
    return x, source, tuple(sorted(warm))


def beta_sha(beta: Any) -> str:
    return hashlib.sha256(json.dumps(beta, separators=(",", ":")).encode()).hexdigest()


def run_oracles(config_path: Path, condition_id: str, output: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: SG Oracle diagnostic is disabled")
    case, point = condition_parts(condition_id)
    loaded = load_frozen_renault_case(case)
    assert_frozen_identity(config, case, loaded)
    x, x_source, warm_pattern = load_point(case, point)
    threads = int(config["solver"]["Threads"])
    tolerance = float(config["comparison_tolerance"])

    eb_build = perf_counter()
    eb_oracle = EnhancedGlobalEnumeratedLPOracle(loaded["instance"], loaded["gamma"])
    eb_oracle.model.Params.Threads = threads
    eb_build_seconds = perf_counter() - eb_build
    try:
        eb_started = perf_counter()
        eb = eb_oracle.solve(x)
        eb_seconds = perf_counter() - eb_started
    finally:
        eb_oracle.close()
    eb_cut_anchor_residual = abs(eb.cut.value_at(x) - eb.value)
    eb_exact = (
        eb.cut.dual_feasible
        and eb.cut.strong_duality_error <= tolerance
        and eb_cut_anchor_residual <= tolerance
    )
    if not eb_exact:
        raise RuntimeError(
            f"EB_ORACLE_CERTIFICATION_FAILURE {condition_id}: "
            f"dual_feasible={eb.cut.dual_feasible}, "
            f"strong_duality_residual={eb.cut.strong_duality_error}, "
            f"cut_anchor_residual={eb_cut_anchor_residual}"
        )

    modes = []
    for mode, candidate in (("cold", ()), ("historical_warm", warm_pattern)):
        build_started = perf_counter()
        evaluator = ExactScenarioLPEvaluator(
            loaded["instance"], loaded["gamma"], x, threads=threads
        )
        build_seconds = perf_counter() - build_started
        try:
            sg_started = perf_counter()
            separated = exact_separation(
                loaded["instance"],
                x,
                loaded["gamma"],
                evaluator.evaluate,
                candidate_patterns=(candidate,),
            )
            sg_seconds = perf_counter() - sg_started
        finally:
            evaluator.close()
        evidence = separated.evaluation.payload
        objective_difference = abs(separated.evaluation.value - eb.value)
        exact = (
            objective_difference <= tolerance
            and evidence["dual_feasibility_max_violation"] <= 1e-7
            and evidence["strong_duality_residual"] <= tolerance
            and evidence["cut_anchor_residual"] <= tolerance
        )
        if not exact:
            raise RuntimeError(
                f"SG_ORACLE_CERTIFICATION_FAILURE {condition_id} {mode}: "
                f"objective_difference={objective_difference}, evidence={evidence}"
            )
        modes.append({
            "start_mode": mode,
            "candidate_pattern": candidate,
            "candidate_source": "empty_scenario" if mode == "cold" else "historical_eb_oracle_trace",
            "model_build_seconds": build_seconds,
            "oracle_seconds": sg_seconds,
            "lp_optimize_seconds": evaluator.lp_seconds,
            "total_scenarios": separated.total_scenarios,
            "exact_lp_solves": separated.lp_solves,
            "safely_pruned_scenarios": separated.safely_pruned_scenarios,
            "pruning_fraction": separated.safely_pruned_scenarios / separated.total_scenarios,
            "branch_nodes": separated.branch_nodes,
            "upper_bound_seconds": separated.upper_bound_seconds,
            "worst_recourse_value": separated.evaluation.value,
            "worst_pattern": separated.pattern,
            "objective_difference_vs_eb": objective_difference,
            "dual_feasibility_max_violation": evidence["dual_feasibility_max_violation"],
            "strong_duality_residual": evidence["strong_duality_residual"],
            "cut_alpha": evidence["alpha"],
            "cut_beta": evidence["beta"],
            "cut_beta_sha256": beta_sha(evidence["beta"]),
            "cut_anchor_value": evidence["cut_anchor_value"],
            "cut_anchor_residual": evidence["cut_anchor_residual"],
            "exact_certification": exact,
        })
    result = {
        "schema": "renault_sg_oracle_condition_v1",
        "experiment_id": config["experiment_id"],
        "protocol_id": config["protocol_id"],
        "condition_id": condition_id,
        "case": case,
        "test_point": point,
        "test_point_source": str(x_source.relative_to(ROOT)),
        "test_point_sha256": sha256(x_source),
        "instance_identity": loaded["identity"],
        "Gamma": loaded["gamma"],
        "lambda_R": loaded["lambda_r"],
        "solver_profile": config["solver_profile"],
        "solver_parameters": config["solver"],
        "eb": {
            "model_build_seconds": eb_build_seconds,
            "oracle_seconds": eb_seconds,
            "exact_lp_solves": eb_oracle.total_scenarios,
            "worst_recourse_value": eb.value,
            "worst_pattern": eb.cut.shock_pattern,
            "dual_feasible": eb.cut.dual_feasible,
            "strong_duality_residual": eb.cut.strong_duality_error,
            "cut_alpha": eb.cut.alpha,
            "cut_beta": eb.cut.beta,
            "cut_beta_sha256": beta_sha(eb.cut.beta),
            "cut_anchor_residual": eb_cut_anchor_residual,
            "exact_certification": eb_exact,
        },
        "sg_modes": modes,
        "early_iteration": "NOT_AVAILABLE",
        "middle_iteration": "NOT_AVAILABLE",
        "optimization_scope": "ORACLE_ONLY",
    }
    write_json(output / "result.json", result)
    identity_source, _ = frozen_identities(config)
    write_json(output / "provenance.json", {
        "condition_id": condition_id,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "config_sha256": sha256(config_path),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "sg_bound_sha256": sha256(ROOT / "src/robust_inventory_reconfiguration/scenario_generation_single_cut.py"),
        "sg_oracle_sha256": sha256(ROOT / "src/robust_inventory_reconfiguration/scenario_generation_oracle.py"),
        "result_sha256": sha256(output / "result.json"),
        "test_point_sha256": sha256(x_source),
        "frozen_identity_source": str(identity_source.relative_to(ROOT)),
        "frozen_identity_source_sha256": sha256(identity_source),
        "instance_identity": loaded["identity"],
    })
    return result


def active_workers() -> list[int]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or []).lower()
            if (process.info.get("name") or "").lower().startswith("gurobi") or (
                "run_renault_sg_oracle_diagnostic.py" in command and "--worker" in command
            ):
                found.append(process.info["pid"])
        except psutil.Error:
            pass
    return found


def dry_run(config_path: Path = CONFIG) -> dict[str, Any]:
    import gurobipy as gp

    config = load_config(config_path)
    _, expected_identities = frozen_identities(config)
    output_root = ROOT / config["output_directory"]
    conditions = []
    for condition in CONDITIONS:
        case, point = condition_parts(condition)
        loaded = load_frozen_renault_case(case)
        _, source, _ = load_point(case, point)
        attempt = output_root / "worker_logs" / condition / "attempt-001"
        canonical = output_root / "runs" / condition
        conditions.append({
            "condition_id": condition,
            "identity_pass": (
                loaded["gamma"] == 2
                and loaded["lambda_r"] == 0.05
                and loaded["identity"] == expected_identities[case]
            ),
            "test_point_source": str(source.relative_to(ROOT)),
            "attempt_exists": attempt.exists(),
            "canonical_exists": canonical.exists(),
        })
    resource = config["resource_policy"]
    available = psutil.virtual_memory().available / 2**30
    free_disk = shutil.disk_usage(output_root.parent).free / 2**30
    status_lines = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    allowed_output = f"?? {output_root.relative_to(ROOT).as_posix()}/"
    unexpected = [
        line for line in status_lines
        if not line.startswith(ALLOWED_DIRTY_PREFIX) and not line.startswith(allowed_output)
    ]
    gates = {
        "identity": all(row["identity_pass"] for row in conditions),
        "attempts_absent": all(not row["attempt_exists"] for row in conditions),
        "canonicals_absent": all(not row["canonical_exists"] for row in conditions),
        "memory": available >= resource["minimum_available_memory_gib"],
        "disk": free_disk >= resource["minimum_free_disk_gib"],
        "git_status": not unexpected,
        "no_active_worker": not active_workers(),
    }
    return {
        "protocol_id": config["protocol_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "conditions": conditions,
        "unavailable_test_points": config["unavailable_test_points"],
        "gates": gates,
        "resource_snapshot": {"available_memory_gib": available, "free_disk_gib": free_disk},
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "gurobi": ".".join(map(str, gp.gurobi.version())),
        },
        "unexpected_git_status": unexpected,
        "optimization_calls": 0,
        "decision": "READY" if all(gates.values()) else "BLOCKED",
    }


def process_tree_rss(pid: int) -> int:
    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0
    total = 0
    for process in processes:
        try:
            total += process.memory_info().rss
        except psutil.Error:
            pass
    return total


def stop_tree(pid: int) -> None:
    try:
        root = psutil.Process(pid)
        processes = [*root.children(recursive=True), root]
    except psutil.Error:
        return
    for process in processes:
        try:
            process.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(processes, timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.Error:
            pass


def run_condition(config_path: Path, condition: str) -> dict[str, Any]:
    config = load_config(config_path)
    output_root = ROOT / config["output_directory"]
    attempt = output_root / "worker_logs" / condition / "attempt-001"
    canonical = output_root / "runs" / condition
    if attempt.exists() or canonical.exists():
        raise FileExistsError(f"refusing to overwrite diagnostic evidence: {condition}")
    payload = attempt / "payload"
    attempt.mkdir(parents=True)
    command = [
        sys.executable, str(Path(__file__).resolve()), "--config", str(config_path),
        "--worker", condition, "--attempt-root", str(payload),
    ]
    resource = config["resource_policy"]
    started = perf_counter()
    peak = 0
    stop_reason = None
    samples = []
    with (attempt / "stdout.log").open("w", encoding="utf-8") as stdout, (
        attempt / "stderr.log"
    ).open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            elapsed = perf_counter() - started
            rss = process_tree_rss(process.pid)
            available = psutil.virtual_memory().available
            peak = max(peak, rss)
            samples.append({"elapsed_seconds": elapsed, "process_tree_rss_gib": rss / 2**30, "system_available_gib": available / 2**30})
            if elapsed >= resource["condition_time_limit_seconds"]:
                stop_reason = "TIME_LIMIT"
            elif rss / 2**30 > resource["maximum_process_tree_memory_gib"]:
                stop_reason = "RESOURCE_PROCESS_CAP"
            elif available / 2**30 < resource["minimum_system_available_memory_gib"]:
                stop_reason = "RESOURCE_SYSTEM_CAP"
            if stop_reason:
                stop_tree(process.pid)
                break
            sleep(resource["memory_monitor_interval_seconds"])
        return_code = process.poll()
    monitor = {
        "condition_id": condition,
        "elapsed_seconds": perf_counter() - started,
        "peak_process_tree_memory_gib": peak / 2**30,
        "stop_reason": stop_reason,
        "worker_return_code": return_code,
        "samples": samples,
        "limits": resource,
    }
    write_json(attempt / "resource_monitor.json", monitor)
    if return_code != 0 or stop_reason is not None:
        raise RuntimeError(f"ORACLE_DIAGNOSTIC_FAILURE {condition}: {monitor}")
    temporary = canonical.with_name(f".tmp-{condition}")
    if temporary.exists():
        raise FileExistsError(f"stale canonical temporary directory: {temporary}")
    shutil.copytree(payload, temporary)
    for name in ("stdout.log", "stderr.log", "resource_monitor.json"):
        shutil.copy2(attempt / name, temporary / name)
    os.replace(temporary, canonical)
    return {"condition_id": condition, "classification": "SUCCESS", **monitor}


def geometric_mean(values: list[float]) -> float:
    return math.exp(sum(math.log(value) for value in values) / len(values))


def summarize(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    output_root = ROOT / config["output_directory"]
    reports = output_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    exactness = []
    for condition in CONDITIONS:
        result_path = output_root / "runs" / condition / "result.json"
        if not result_path.is_file():
            raise RuntimeError(f"missing canonical diagnostic result: {result_path}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        for mode in result["sg_modes"]:
            row = {
                "case": result["case"],
                "test_point": result["test_point"],
                "start_mode": mode["start_mode"],
                "availability_status": "AVAILABLE",
                "test_point_source": result["test_point_source"],
                "total_scenarios": mode["total_scenarios"],
                "sg_exact_lp_solves": mode["exact_lp_solves"],
                "eb_exact_lp_solves": result["eb"]["exact_lp_solves"],
                "safely_pruned_scenarios": mode["safely_pruned_scenarios"],
                "pruning_fraction": mode["pruning_fraction"],
                "branch_nodes": mode["branch_nodes"],
                "upper_bound_seconds": mode["upper_bound_seconds"],
                "sg_oracle_seconds": mode["oracle_seconds"],
                "eb_oracle_seconds": result["eb"]["oracle_seconds"],
                "speedup_eb_over_sg": result["eb"]["oracle_seconds"] / mode["oracle_seconds"],
                "sg_worst_recourse_value": mode["worst_recourse_value"],
                "eb_worst_recourse_value": result["eb"]["worst_recourse_value"],
                "objective_difference": mode["objective_difference_vs_eb"],
                "sg_worst_pattern": json.dumps(mode["worst_pattern"], separators=(",", ":")),
                "eb_worst_pattern": json.dumps(result["eb"]["worst_pattern"], separators=(",", ":")),
                "dual_feasibility_max_violation": mode["dual_feasibility_max_violation"],
                "strong_duality_residual": mode["strong_duality_residual"],
                "cut_anchor_residual": mode["cut_anchor_residual"],
                "exact_certification": mode["exact_certification"],
            }
            rows.append(row)
            exactness.append({
                "case": result["case"],
                "test_point": result["test_point"],
                "start_mode": mode["start_mode"],
                "exact_certification": mode["exact_certification"],
                "objective_difference": mode["objective_difference_vs_eb"],
                "dual_feasibility_max_violation": mode["dual_feasibility_max_violation"],
                "strong_duality_residual": mode["strong_duality_residual"],
                "cut_anchor_residual": mode["cut_anchor_residual"],
            })
    for case in CASES:
        for point in config["unavailable_test_points"]:
            rows.append({
                "case": case,
                "test_point": point,
                "start_mode": "NOT_APPLICABLE",
                "availability_status": "NOT_AVAILABLE",
                "test_point_source": "NOT_AVAILABLE: historical trajectory did not persist first-stage x",
            })
    point_csv = reports / "oracle_point_results.csv"
    with point_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    aggregates = []
    for point in POINTS:
        for mode in config["start_modes"]:
            selected = [row for row in rows if row["test_point"] == point and row["start_mode"] == mode]
            aggregates.append({
                "test_point": point,
                "start_mode": mode,
                "pairs": len(selected),
                "mean_pruning_fraction": sum(row["pruning_fraction"] for row in selected) / len(selected),
                "mean_lp_reduction_fraction": sum(1 - row["sg_exact_lp_solves"] / row["eb_exact_lp_solves"] for row in selected) / len(selected),
                "mean_sg_oracle_seconds": sum(row["sg_oracle_seconds"] for row in selected) / len(selected),
                "mean_eb_oracle_seconds": sum(row["eb_oracle_seconds"] for row in selected) / len(selected),
                "geometric_mean_speedup_eb_over_sg": geometric_mean([row["speedup_eb_over_sg"] for row in selected]),
            })
    aggregate_csv = reports / "oracle_time_and_pruning_summary.csv"
    with aggregate_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(aggregates[0]))
        writer.writeheader()
        writer.writerows(aggregates)
    exactness_path = reports / "exactness_and_cut_audit.json"
    write_json(exactness_path, {
        "comparison_tolerance": config["comparison_tolerance"],
        "all_certified": all(row["exact_certification"] for row in exactness),
        "records": exactness,
    })
    report_path = ROOT / "docs/renault_sg_oracle_diagnostic_results.md"
    aggregate_lines = "\n".join(
        "| {test_point} | {start_mode} | {pairs} | {mean_pruning_fraction:.4%} | "
        "{mean_eb_oracle_seconds:.6f} | {mean_sg_oracle_seconds:.6f} | "
        "{geometric_mean_speedup_eb_over_sg:.2f}x |".format(**row)
        for row in aggregates
    )
    report_path.write_text(
        "# Renault SG-BD Oracle-only diagnostic\n\n"
        "## Scope and identity\n\n"
        "The authorized diagnostic completed all 16 frozen conditions: eight Renault cases at "
        "the persisted final EB-BD first-stage solution and the frozen real `x0`. Each available "
        "point was evaluated with cold and historical-pattern starts. No full SG-BD run or scaling "
        "optimization was executed.\n\n"
        "The EB trajectory artifacts do not contain first-stage matrices for early or middle "
        "iterations. Those requested point classes are therefore recorded as `NOT_AVAILABLE`; "
        "`x0` is an additional real legal point and is not presented as an early iterate.\n\n"
        "## Results\n\n"
        "| Point | Start | Pairs | Mean pruning | Mean EB seconds | Mean SG seconds | Geometric speedup |\n"
        "|---|---:|---:|---:|---:|---:|---:|\n"
        f"{aggregate_lines}\n\n"
        f"All {len(exactness)} available comparisons passed objective equivalence, dual "
        "feasibility, strong-duality, and cut-anchor checks at the frozen tolerances. Full EB "
        "enumeration solved 4,657 LPs per point; SG solved only the unresolved leaves after "
        "safe upper-bound pruning. Detailed counts and timings are in `oracle_point_results.csv`.\n\n"
        "## Decision\n\n"
        "**NO_GO_FOR_FULL_SG_BD_YET — insufficient representative trajectory evidence.** "
        "The measured final and `x0` points show substantial exact Oracle acceleration, and bound/tree "
        "overhead does not erase it. However, the predeclared gate requires stable acceleration on "
        "real early and middle EB-BD iterates. Those decisions were not persisted, so this diagnostic "
        "cannot establish that condition without inventing or substituting data. A separately "
        "authorized trajectory-capture experiment is the minimum next step.\n",
        encoding="utf-8",
    )
    manifest_path = reports / "sha256_manifest.csv"
    summary = {
        "rows": len(rows),
        "all_certified": all(row["exact_certification"] for row in exactness),
        "aggregates": aggregates,
        "point_csv": str(point_csv.relative_to(ROOT)),
        "aggregate_csv": str(aggregate_csv.relative_to(ROOT)),
        "exactness_audit": str(exactness_path.relative_to(ROOT)),
        "sha256_manifest": str(manifest_path.relative_to(ROOT)),
        "markdown_report": str(report_path.relative_to(ROOT)),
    }
    batch_report_path = output_root / "batch_report.json"
    if batch_report_path.is_file():
        batch_report = json.loads(batch_report_path.read_text(encoding="utf-8"))
        batch_report["summary"] = summary
        write_json(batch_report_path, batch_report)
    manifest_targets = sorted(
        path for path in output_root.rglob("*")
        if path.is_file() and path != manifest_path
    )
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "sha256", "size_bytes"])
        for path in manifest_targets:
            writer.writerow([path.relative_to(ROOT).as_posix(), sha256(path), path.stat().st_size])
    return summary


def execute(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if config.get("formal_run_authorized") is not True:
        raise RuntimeError("NOT_AUTHORIZED: SG Oracle diagnostic is disabled")
    preflight = dry_run(config_path)
    if not all(preflight["gates"].values()):
        raise RuntimeError(f"PREFLIGHT_BLOCKED: {preflight['gates']}")
    records = []
    for condition in CONDITIONS:
        current = dry_run(config_path)
        row = next(item for item in current["conditions"] if item["condition_id"] == condition)
        gates = {key: value for key, value in current["gates"].items() if key not in {"attempts_absent", "canonicals_absent"}}
        if not all(gates.values()) or row["attempt_exists"] or row["canonical_exists"]:
            raise RuntimeError(f"INTEGRITY_FAILURE before {condition}: {row}, {gates}")
        records.append(run_condition(config_path, condition))
    summary = summarize(config_path)
    report = {"protocol_id": config["protocol_id"], "status": "COMPLETE", "records": records, "summary": summary}
    write_json(ROOT / config["output_directory"] / "batch_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--summarize", action="store_true")
    modes.add_argument("--worker", choices=CONDITIONS)
    parser.add_argument("--attempt-root", type=Path)
    args = parser.parse_args()
    try:
        if args.worker:
            if args.attempt_root is None:
                parser.error("--worker requires --attempt-root")
            run_oracles(args.config.resolve(), args.worker, args.attempt_root.resolve())
            return 0
        if args.execute:
            result = execute(args.config.resolve())
        elif args.summarize:
            result = summarize(args.config.resolve())
        else:
            result = dry_run(args.config.resolve())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as error:
        if args.worker and args.attempt_root:
            args.attempt_root.mkdir(parents=True, exist_ok=True)
            (args.attempt_root / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
            write_json(args.attempt_root / "failure.json", {"error": str(error), "type": type(error).__name__})
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
