"""Non-destructive paired Scaling30 continuation with explicit numerical sign-off.

Place next to BOTH original, unmodified runners under experiments/:
  run_prb_basic_v2_fair_scaling30.py
  run_accelerated_prb_v2_scaling30.py

- Reuses legacy exact-certified Basic/V2 results only after legacy's complete
  identity and result-hash verification; NEVER modifies those archives.
- Runs missing Basic via the unmodified legacy runner; runs missing V2 here.
- For V2 failing the legacy strict coupling flag, only accepts a separately
  labelled 'independently_numerically_validated' result after independent
  original-product recourse audit, returned-cut checks and bounded residuals.
- Preserves the original strict pass/fail flag in every new result.
- New result/log/CSV directory; never patches old failure records.

A numerical sign-off is NOT the same as the original strict exact certificate;
keep certificate classes separated in paper and experiment reporting.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from time import perf_counter, sleep
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import run_accelerated_prb_v2_scaling30 as frozen
import run_prb_basic_v2_fair_scaling30 as legacy

PROTOCOL = "NUMERIC_GUARD_V1_SEPARATE_CLASS"
REL_GAP_TOL = 1e-6
OBJECTIVE_TOL = 1e-4
# Explicit, conservative and bounded *provisional numerical* thresholds.
# Not a proof of a generic solver accuracy guarantee.
NUMERIC_ABS_FLOOR = 1e-6
NUMERIC_ABS_CEILING = 1e-5
NUMERIC_REL_FACTOR = 5e-12
INDEPENDENT_RECOURSE_TOL = 1e-6
CUT_FINAL_OVER_TOL = 1e-6
CUT_DUALITY_TOL = 1e-6
TIMEOUT = 900
POLL = 0.25


def new_root(workers: int) -> Path:
    return ROOT / f"experiments/results/prb_basic_v2_fair_scaling30_W{workers}_numeric_guard_v1"


def new_dest(size: str, seed: int, workers: int) -> Path:
    return new_root(workers) / "runs" / f"{size}_S{seed}_V2"


def numeric_tolerance(scale: float) -> float:
    return min(NUMERIC_ABS_CEILING, max(NUMERIC_ABS_FLOOR, NUMERIC_REL_FACTOR * scale))


def identity(size: str, seed: int, workers: int, hashes: dict) -> dict:
    import gurobipy as gp
    return {
        "protocol": PROTOCOL,
        "size": size, "seed": seed, "method": "v2", "workers": workers,
        "python": platform.python_version(),
        "gurobi": list(gp.gurobi.version()),
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "git_commit": frozen.commit(),
        "new_runner_sha256": frozen.sha256(Path(__file__)),
        "legacy_runner_sha256": frozen.sha256(Path(legacy.__file__)),
        "frozen_loader_sha256": frozen.sha256(Path(frozen.__file__)),
        "model_hashes": frozen.code_hashes(), "input_hashes": hashes,
        "Gamma": 2, "beta": 1.0, "lambda_R": 0.05,
        "relative_gap": REL_GAP_TOL, "cut_tolerance": 1e-7,
        "max_iterations": 500,
        "objective_tolerance": OBJECTIVE_TOL,
        "numeric_abs_floor": NUMERIC_ABS_FLOOR,
        "numeric_abs_ceiling": NUMERIC_ABS_CEILING,
        "numeric_rel_factor": NUMERIC_REL_FACTOR,
        "independent_recourse_tolerance": INDEPENDENT_RECOURSE_TOL,
        "cut_at_final_x_over_tolerance": CUT_FINAL_OVER_TOL,
        "cut_duality_tolerance": CUT_DUALITY_TOL,
    }


def verified_new(path: Path, ident: dict) -> bool:
    if not path.exists():
        return False
    rp, pp = path / "result.json", path / "provenance.json"
    if not rp.is_file() or not pp.is_file():
        raise RuntimeError(f"Partial new result, refusing overwrite: {path}")
    r, p = frozen.read_json(rp), frozen.read_json(pp)
    valid = (
        p.get("identity") == ident
        and p.get("result_sha256") == frozen.sha256(rp)
        and r.get("validated_under_protocol") is True
        and r.get("frozen_objective_match") is True
        and r.get("certification_class") in (
            "strict_original", "independently_numerically_validated"
        )
    )
    if not valid:
        raise RuntimeError(f"Invalid/incompatible new result, refusing reuse: {path}")
    return True


def legacy_certified(size: str, seed: int, method: str, workers: int) -> bool:
    _, _, _, hashes = frozen.fetch_inputs(size, seed)
    ident = legacy.identity(size, seed, method, workers, hashes)
    return legacy.verified(legacy.destination(size, seed, method, workers), ident)


def where_result(size: str, seed: int, method: str, workers: int):
    """Return (source class, path to result) or None. Never trusts CSV alone."""
    old_path = legacy.destination(size, seed, method, workers)
    if old_path.exists() and legacy_certified(size, seed, method, workers):
        return "legacy_strict_exact", old_path / "result.json"
    if method == "v2":
        path = new_dest(size, seed, workers)
        if path.exists():
            _, _, _, hashes = frozen.fetch_inputs(size, seed)
            if verified_new(path, identity(size, seed, workers, hashes)):
                return "new_numeric_protocol", path / "result.json"
    return None


def independent_audit(instance, solved) -> dict:
    """Original per-product LP cross-check of V2 candidate and every returned cut.

    This additional audit is outside solved.total_runtime and is timed separately.
    It does not establish exact arithmetic / proof of all master bounds.
    """
    from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
    from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget

    started = perf_counter()
    x = solved.solution.x
    product_values = []
    original_worst_dual_failures = []
    original_max_strong_duality_error = 0.0
    for j in range(instance.num_products):
        problem = ProductRiskSubproblem(instance, j, 2)
        try:
            worst = problem.solve([x[i][j] for i in range(instance.num_depots)])
            product_values.append([float(w.value) for w in worst.worst_cases])
            for w in worst.worst_cases:
                if not w.cut.dual_feasible:
                    original_worst_dual_failures.append((j, w.local_gamma))
                original_max_strong_duality_error = max(
                    original_max_strong_duality_error, float(w.cut.strong_duality_error)
                )
        finally:
            problem.model.dispose()
    composition = compose_risk_budget(product_values, 2)
    independent_obj = float(solved.solution.first_stage_expenditure) + float(composition.value)
    cuts_infeasible = []
    cuts_strong_max = 0.0
    cuts_generation_max = 0.0
    cuts_over_max = 0.0
    violating_cut_indices = []
    for k, cut in enumerate(solved.cuts):
        if not cut.dual_feasible:
            cuts_infeasible.append(k)
        cuts_strong_max = max(cuts_strong_max, float(cut.strong_duality_error))
        cuts_generation_max = max(
            cuts_generation_max,
            abs(float(cut.value_at(cut.generation_x)) - float(cut.generation_value)),
        )
        j, g = int(cut.product_index), int(cut.local_gamma)
        cut_value = float(cut.value_at([x[i][j] for i in range(instance.num_depots)]))
        over = cut_value - product_values[j][g]
        cuts_over_max = max(cuts_over_max, over)
        if over > CUT_FINAL_OVER_TOL:
            violating_cut_indices.append(k)
    return {
        "independent_robust_recourse_cost": float(composition.value),
        "independent_objective_at_v2_x": independent_obj,
        "independent_recourse_minus_v2": float(composition.value) - float(solved.solution.robust_recourse_cost),
        "independent_objective_minus_v2": independent_obj - float(solved.solution.objective),
        "independent_risk_allocation": list(composition.allocation),
        "original_worst_dual_failures": original_worst_dual_failures,
        "original_max_strong_duality_error": original_max_strong_duality_error,
        "returned_cuts_count": len(solved.cuts),
        "returned_cuts_dual_infeasible_indices": cuts_infeasible,
        "returned_cuts_max_strong_duality_error": cuts_strong_max,
        "returned_cuts_max_generation_mismatch": cuts_generation_max,
        "returned_cuts_max_over_independent_recourse_at_final_x": cuts_over_max,
        "returned_cuts_over_final_x_tolerance_indices": violating_cut_indices,
        "audit_seconds_excluded_from_core": perf_counter() - started,
        "scope_note": (
            "Independent candidate recourse and cut checks at final inventory; "
            "not an exact-arithmetic proof of whole-domain cut validity or lower bound."
        ),
    }


def numerical_policy(solved, frozen_obj: float, audit: dict | None) -> dict:
    lb = float(solved.final_lower_bound)
    ub = float(solved.final_upper_bound)
    obj = float(solved.solution.objective)
    scale = max(1.0, abs(lb), abs(ub), abs(obj))
    tol = numeric_tolerance(scale)
    signed_gap = lb - ub
    positive_optimality_gap = max(0.0, ub - lb) / scale
    last_cuts = int(solved.iterations[-1].cuts_added) if solved.iterations else None
    strict = (
        solved.status == "OPTIMAL"
        and bool(solved.exact_certification_pass)
        and bool(solved.global_risk_budget_coupling_pass)
        and float(solved.final_relative_gap) <= REL_GAP_TOL
        and signed_gap <= tol
        and last_cuts == 0
    )
    # Independent audit applies only to the exceptional numerical-coupling case.
    audited = bool(audit is not None and
        not audit["original_worst_dual_failures"] and
        audit["original_max_strong_duality_error"] <= CUT_DUALITY_TOL and
        not audit["returned_cuts_dual_infeasible_indices"] and
        audit["returned_cuts_max_strong_duality_error"] <= CUT_DUALITY_TOL and
        audit["returned_cuts_max_generation_mismatch"] <= CUT_DUALITY_TOL and
        not audit["returned_cuts_over_final_x_tolerance_indices"] and
        abs(audit["independent_recourse_minus_v2"]) <= INDEPENDENT_RECOURSE_TOL and
        abs(audit["independent_objective_minus_v2"]) <= INDEPENDENT_RECOURSE_TOL and
        abs(audit["independent_objective_at_v2_x"] - frozen_obj) <= OBJECTIVE_TOL)
    numerical = (
        not strict
        and solved.status == "OPTIMAL"
        and bool(solved.exact_certification_pass)
        and not bool(solved.global_risk_budget_coupling_pass)
        and 0 <= float(solved.global_risk_budget_coupling_error) <= tol
        and 0 <= signed_gap <= tol
        and positive_optimality_gap <= REL_GAP_TOL
        and abs(obj - ub) <= INDEPENDENT_RECOURSE_TOL
        and last_cuts == 0
        and audited
    )
    return {
        "strict_original_certification": bool(strict),
        "independently_numerically_validated": bool(numerical),
        "validated_under_protocol": bool(strict or numerical),
        "certification_class": (
            "strict_original" if strict else
            "independently_numerically_validated" if numerical else "FAILED"
        ),
        "original_exact_certification_flag": bool(solved.exact_certification_pass),
        "original_global_risk_coupling_flag": bool(solved.global_risk_budget_coupling_pass),
        "original_global_risk_coupling_error": float(solved.global_risk_budget_coupling_error),
        "original_reported_gap": float(solved.final_relative_gap),
        "signed_lower_minus_upper": signed_gap,
        "absolute_lower_upper_difference": abs(signed_gap),
        "independent_positive_optimality_gap": positive_optimality_gap,
        "numerical_error_threshold_absolute": tol,
        "last_iteration_new_cuts": last_cuts,
        "independent_audit_pass": audited if audit is not None else None,
    }


def run_new_child(size: str, seed: int, workers: int) -> None:
    import gurobipy as gp
    from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import solve_accelerated_prb_benders

    instance, prep, frozen_base, hashes = frozen.fetch_inputs(size, seed)
    ident = identity(size, seed, workers, hashes)
    target = new_dest(size, seed, workers)
    if verified_new(target, ident):
        print(f"[VERIFIED NEW SKIP] v2 {size}/{seed}", flush=True)
        return
    gp.setParam("Threads", 1)
    started = perf_counter()
    solved = solve_accelerated_prb_benders(
        instance, instance.initial_inventory, float(prep["budget"]), 2, 0.05,
        relative_gap_tolerance=REL_GAP_TOL, cut_tolerance=1e-7,
        max_iterations=500, parallel_workers=workers, _oracle_backend="process",
    )
    child_solve_seconds = perf_counter() - started
    frozen_obj = float(frozen_base["final_objective"])
    audit = None
    prelim = numerical_policy(solved, frozen_obj, None)
    if not prelim["strict_original_certification"]:
        # Recompute using independent original product LPs BEFORE acceptance.
        audit = independent_audit(instance, solved)
    checks = numerical_policy(solved, frozen_obj, audit)
    delta = abs(float(solved.solution.objective) - frozen_obj)
    result = {
        "protocol": PROTOCOL,
        "method": "v2", "size": size, "seed": seed,
        "instance_hash": prep["instance_hash"], "x0_hash": prep["x0_hash"],
        "budget": prep["budget"], "Gamma": 2, "beta": 1.0, "lambda_R": 0.05,
        "objective": float(solved.solution.objective),
        "original_frozen_basic_objective": frozen_obj,
        "objective_difference_from_frozen": delta,
        "frozen_objective_match": delta <= OBJECTIVE_TOL,
        "core_time_seconds": float(solved.total_runtime),
        "child_solve_wall_seconds": child_solve_seconds,
        "master_time_seconds": float(solved.master_runtime),
        "oracle_time_seconds": float(solved.separation_runtime),
        "certification_time_seconds": float(solved.certification_runtime),
        "iterations": len(solved.iterations),
        "unique_product_cuts": int(solved.unique_product_cuts),
        "worker_count": int(solved.parallel_worker_count),
        "gurobi_threads_per_model": 1,
        "relative_gap": float(solved.final_relative_gap),
        "first_stage_solution": asdict(solved.solution),
        "cache_hits": int(solved.cache_hits),
        "product_solves_avoided": int(solved.product_solves_avoided),
        "product_model_build_seconds": float(solved.oracle_model_build_runtime),
        "audit": audit,
        **checks,
        "exact_certification": bool(checks["strict_original_certification"]),
    }
    if not result["validated_under_protocol"] or not result["frozen_objective_match"]:
        path = new_root(workers) / "failed_diagnostics" / f"{size}_{seed}_v2_{uuid4().hex}.json"
        frozen.write_json(path, {"identity": ident, "result": result})
        raise RuntimeError(f"NOT VALIDATED: v2 {size}/{seed}; see {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".tmp-{target.name}-{uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=False)
    try:
        rpath = tmp / "result.json"
        frozen.write_json(rpath, result)
        frozen.write_json(tmp / "provenance.json", {
            "identity": ident,
            "result_sha256": frozen.sha256(rpath),
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        if target.exists():
            raise FileExistsError(f"Refusing overwrite: {target}")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"[VALIDATED {checks['certification_class']}] v2 {size}/{seed}: {solved.total_runtime:.3f}s", flush=True)


def monitor_new_v2(size: str, seed: int, workers: int):
    _, _, _, hashes = frozen.fetch_inputs(size, seed)
    ident = identity(size, seed, workers, hashes)
    target = new_dest(size, seed, workers)
    if verified_new(target, ident):
        print(f"[SKIP NEW VALIDATED] v2 {size}/{seed}", flush=True)
        return
    cap = frozen.RESOURCE[size]
    available = psutil.virtual_memory().available / (2 ** 30)
    if available < cap["min_available"]:
        raise RuntimeError(f"LOW AVAILABLE MEMORY: {available:.2f} GiB on {size}")
    folder = new_root(workers) / "logs" / f"{size}_S{seed}_V2"
    attempt = 1
    while (folder / f"attempt-{attempt:03d}").exists():
        attempt += 1
    logdir = folder / f"attempt-{attempt:03d}"
    logdir.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable, str(Path(__file__).resolve()),
        "--child-v2", size, str(seed), "--workers", str(workers)
    ]
    t0, peak, reason = perf_counter(), 0.0, None
    with (logdir / "stdout.log").open("w", encoding="utf-8") as stdout, \
         (logdir / "stderr.log").open("w", encoding="utf-8") as stderr:
        proc = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while proc.poll() is None:
            peak = max(peak, frozen.tree_rss_gib(proc.pid))
            now = psutil.virtual_memory().available / (2 ** 30)
            elapsed = perf_counter() - t0
            if peak >= cap["max_tree"]:
                reason = f"PROCESS_MEMORY_CAP: {peak:.2f} >= {cap['max_tree']} GiB"
            elif now <= frozen.SYSTEM_FLOOR_GIB:
                reason = f"SYSTEM_MEMORY_FLOOR: {now:.2f} GiB"
            elif elapsed >= TIMEOUT:
                reason = "TIME_LIMIT"
            if reason:
                frozen.terminate_tree(proc.pid)
                break
            sleep(POLL)
        code = proc.poll()
    frozen.write_json(logdir / "monitor.json", {
        "size": size, "seed": seed, "method": "v2", "workers": workers,
        "exit_code": code, "stop_reason": reason,
        "preflight_available_gib": available,
        "peak_process_tree_rss_gib": peak,
        "elapsed_monitored_wall_seconds": perf_counter() - t0,
    })
    if reason or code != 0:
        raise RuntimeError(f"FAILED v2 {size}/{seed}: {reason or code}; see {logdir}")
    if not verified_new(target, ident):
        raise RuntimeError(f"No validated new result for v2 {size}/{seed}")
    print(f"[DONE NEW] v2 {size}/{seed}; peak tree memory={peak:.2f} GiB", flush=True)


def ensure_method(size: str, seed: int, method: str, workers: int):
    if where_result(size, seed, method, workers):
        print(f"[REUSE VERIFIED] {method} {size}/{seed}", flush=True)
        return
    if method == "basic":
        # A missing Basic is solved with the UNMODIFIED original paired runner.
        legacy.monitored(size, seed, "basic", workers)
    elif method == "v2":
        monitor_new_v2(size, seed, workers)
    else:
        raise ValueError(method)
    if where_result(size, seed, method, workers) is None:
        raise RuntimeError(f"Missing validated output: {method} {size}/{seed}")


def write_unified_comparison(workers: int):
    rows = []
    for size in frozen.SIZES:
        for seed in frozen.SEEDS:
            bsource = where_result(size, seed, "basic", workers)
            vsource = where_result(size, seed, "v2", workers)
            if bsource is None or vsource is None:
                continue
            b = frozen.read_json(bsource[1])
            v = frozen.read_json(vsource[1])
            diff = abs(float(b["objective"]) - float(v["objective"]))
            if diff > OBJECTIVE_TOL:
                raise RuntimeError(f"Paired objective mismatch {size}/{seed}: {diff}")
            v_class = ("legacy_strict_exact" if vsource[0] == "legacy_strict_exact"
                       else v["certification_class"])
            rows.append({
                "size": size, "seed": seed,
                "basic_core_seconds_new": b["core_time_seconds"],
                "v2_core_seconds_new": v["core_time_seconds"],
                "basic_over_v2_speedup_new": (
                    b["core_time_seconds"] / v["core_time_seconds"]
                ),
                "basic_child_wall_seconds": b["child_solve_wall_seconds"],
                "v2_child_wall_seconds": v["child_solve_wall_seconds"],
                "basic_iterations": b["iterations"], "v2_iterations": v["iterations"],
                "basic_workers": 1, "v2_workers": v["worker_count"],
                "objective_difference": diff,
                "basic_result_source": bsource[0],
                "v2_result_source": vsource[0],
                "v2_certificate_class": v_class,
                "v2_original_strict_exact": v_class in (
                    "strict_original", "legacy_strict_exact"
                ),
                "v2_independent_numeric_validation": v_class == "independently_numerically_validated",
                "both_validated_under_disclosed_protocol": True,
            })
    path = new_root(workers) / "paired_comparison_numeric_guard_v1.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp, path)
    print(f"[UNIFIED PAIRS] {len(rows)} -> {path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", nargs="+", choices=[*frozen.SIZES, "ALL"], default=["L10", "XL10"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--child-v2", nargs=2, metavar=("SIZE", "SEED"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.workers not in range(1, 9):
        parser.error("--workers must be 1..8")
    if args.seed is not None and args.seed not in frozen.SEEDS:
        parser.error("--seed must be 20260921..20260930")
    if args.child_v2:
        size, seed = args.child_v2
        if size not in frozen.SIZES or int(seed) not in frozen.SEEDS:
            parser.error("invalid child size/seed")
        run_new_child(size, int(seed), args.workers)
        return
    sizes = list(frozen.SIZES) if "ALL" in args.size else list(dict.fromkeys(args.size))
    seeds = list(frozen.SEEDS) if args.seed is None else [args.seed]
    print(f"[PROTOCOL] {PROTOCOL}; sizes={sizes}; seeds={len(seeds)}; workers={args.workers}", flush=True)
    for size in sizes:
        for seed in seeds:
            if args.dry_run:
                b = where_result(size, seed, "basic", args.workers)
                v = where_result(size, seed, "v2", args.workers)
                print(f"[CHECK] {size}/{seed}: Basic={'VERIFIED' if b else 'NEEDED'} "
                      f"V2={'VERIFIED' if v else 'NEEDED'}", flush=True)
                continue
            # Same A-B/B-A parity scheduling as the original runner.
            order = ("basic", "v2") if seed % 2 else ("v2", "basic")
            for method in order:
                ensure_method(size, seed, method, args.workers)
            write_unified_comparison(args.workers)
    if not args.dry_run:
        print("[FINISHED] Validated under recorded certificate classes. "
              "Historical results and failure records unchanged.", flush=True)


if __name__ == "__main__":
    main()
