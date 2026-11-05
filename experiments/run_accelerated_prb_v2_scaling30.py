"""Non-destructive, monitored Accelerated PRB V2 evaluation on frozen Scaling30.

Place at experiments/run_accelerated_prb_v2_scaling30.py in the repository
Hoshino12172003/budget-inventory-benders, branch experiment/xxl10-four-method-final-archive.

Usage:
 python experiments/run_accelerated_prb_v2_scaling30.py --dry-run --workers 2
 python experiments/run_accelerated_prb_v2_scaling30.py --size L10 --seed 20260921 --workers 2
 python experiments/run_accelerated_prb_v2_scaling30.py --size ALL --workers 2
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
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

from robust_inventory_reconfiguration.algorithm_scaling import (
    GAMMA, BETA, LAMBDA_R, SERVICE_LEVEL, PHI_MULTIPLIER,
    canonical_hash, validate_scientific_parameters,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import (
    solve_accelerated_prb_benders,
)

SIZES = {"L10": (25, 24, 12), "XL10": (30, 30, 14), "XXL10": (36, 36, 16)}
SEEDS = range(20260921, 20260931)
FROZEN_ROOT = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
CODE_PATHS = [
    "experiments/run_accelerated_prb_v2_scaling30.py",
    "src/robust_inventory_reconfiguration/algorithm_scaling.py",
    "src/robust_inventory_reconfiguration/instance.py",
    "src/robust_inventory_reconfiguration/accelerated_product_risk_budget_benders.py",
    "src/robust_inventory_reconfiguration/accelerated_product_risk_subproblem.py",
    "src/robust_inventory_reconfiguration/product_risk_budget_benders.py",
    "src/robust_inventory_reconfiguration/product_risk_subproblem.py",
    "src/robust_inventory_reconfiguration/risk_budget_composition.py",
    "src/robust_inventory_reconfiguration/reconfiguration_model.py",
    "src/robust_inventory_reconfiguration/solver_profile.py",
]
# Conservative borrowed safety caps from frozen serial Scaling protocol.
# V2's multicore resource usage differs; treat these as guardrails, not proof of safety.
RESOURCE = {
    "L10": {"min_available": 7.0, "max_tree": 4.0},
    "XL10": {"min_available": 10.0, "max_tree": 7.0},
    "XXL10": {"min_available": 16.0, "max_tree": 13.0},
}
SYSTEM_FLOOR_GIB = 3.0
CONDITION_TIMEOUT_SECONDS = 900
POLL_SECONDS = 0.25


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def code_hashes():
    return {p: sha256(ROOT / p) for p in CODE_PATHS}


def output_root(workers):
    return ROOT / f"experiments/results/prb_accelerated_v2_scaling30_W{workers}"


def cond_id(size, seed):
    return f"ACCEL_PRB_V2_{size}_S{seed}_W{{workers}}"


def fetch_inputs(size, seed):
    dirname = FROZEN_ROOT / "instances" / size / str(seed)
    instance_path, prep_path = dirname / "instance.json", dirname / "preparation.json"
    base_path = FROZEN_ROOT / "runs" / f"ASC_{size}_S{seed}_PRB_BENDERS" / "result.json"
    for p in (instance_path, prep_path, base_path):
        if not p.is_file():
            raise FileNotFoundError(f"Frozen input missing: {p}")
    instance = load_instance(instance_path)
    prep, base = read_json(prep_path), read_json(base_path)
    checks = {
        "dimensions": (instance.num_depots, instance.num_regions, instance.num_products) == SIZES[size],
        "instance_hash": canonical_hash(instance.to_dict()) == prep.get("instance_hash") == base.get("instance_hash"),
        "x0_hash": instance.initial_inventory is not None and canonical_hash(instance.initial_inventory) == prep.get("x0_hash"),
        "size_seed": prep.get("size") == base.get("size") == size and prep.get("seed") == base.get("seed") == seed,
        "sciences": validate_scientific_parameters(instance).get("pass") is True,
        "fixed_params": (GAMMA, BETA, LAMBDA_R, SERVICE_LEVEL, PHI_MULTIPLIER) == (2, 1.0, 0.05, 0.90, 1.85),
        "frozen_params": prep.get("scientific_parameters") == {
            "Gamma": 2, "SL": 0.9, "beta": 1.0, "lambda_R": 0.05,
            "phi_definition": "phi_j = phi_multiplier * max_r p_rj", "phi_multiplier": 1.85,
            "service_constraint": "soft SLA",
        },
        "baseline_certified": base.get("solver_status") == "OPTIMAL" and base.get("exact_certification") is True,
        "budget": abs(float(prep["budget"]) - float(prep["B_ref"])) <= 1e-6,
    }
    bad = [k for k, v in checks.items() if not v]
    if bad:
        raise RuntimeError(f"Frozen identity or science mismatch {size}/{seed}: {bad}")
    return instance, prep, base, {"instance":sha256(instance_path), "preparation":sha256(prep_path), "basic_prb":sha256(base_path)}


def identity(size, seed, workers, hashes):
    return {
        "experiment": "PRB_ACCELERATED_V2_SCALING30_INDEPENDENT",
        "size": size, "seed": seed, "workers": workers,
        "Gamma": GAMMA, "beta": BETA, "lambda_R": LAMBDA_R,
        "relative_gap": 1e-6, "cut_tolerance": 1e-7, "max_iterations": 500,
        "backend": "process", "per_worker_gurobi_threads": 1,
        "git_commit": commit(), "code_sha256": code_hashes(), "inputs_sha256": hashes,
    }


def verify_existing(out_dir: Path, ident: dict) -> bool:
    if not out_dir.exists():
        return False
    result_file = out_dir / "result.json"
    provenance_file = out_dir / "provenance.json"
    if not result_file.is_file() or not provenance_file.is_file():
        raise RuntimeError(f"Partial existing output, refusing overwrite: {out_dir}")
    result, prov = read_json(result_file), read_json(provenance_file)
    if (prov.get("identity") != ident or prov.get("result_sha256") != sha256(result_file)
        or result.get("exact_certification") is not True
        or result.get("objective_pair_certified") is not True):
        raise RuntimeError(f"Existing run has incompatible identity or failed certification: {out_dir}")
    return True


def child(size: str, seed: int, workers: int):
    import gurobipy as gp
    instance, prep, base, hashes = fetch_inputs(size, seed)
    ident = identity(size, seed, workers, hashes)
    cid = cond_id(size,seed).format(workers=workers)
    output = output_root(workers) / "runs" / cid
    if verify_existing(output, ident):
        print(f"[VERIFIED SKIP] {cid}", flush=True)
        return
    started = perf_counter()
    solved = solve_accelerated_prb_benders(
        instance, instance.initial_inventory, float(prep["budget"]), GAMMA, LAMBDA_R,
        relative_gap_tolerance=1e-6, cut_tolerance=1e-7,
        max_iterations=500, parallel_workers=workers, _oracle_backend="process",
    )
    elapsed = perf_counter() - started
    obj = float(solved.solution.objective)
    ref_obj = float(base["final_objective"])
    delta = abs(obj - ref_obj)
    certified = (solved.status == "OPTIMAL"
                 and bool(solved.exact_certification_pass)
                 and bool(solved.global_risk_budget_coupling_pass)
                 and float(solved.final_relative_gap) <= 1e-6)
    paired = delta <= 1e-4
    result = {
        "condition_id": cid,
        "method": "accelerated_prb_v2", "size": size, "seed": seed,
        "exact_certification": certified, "objective_pair_certified": paired,
        "objective": obj, "basic_prb_objective": ref_obj, "objective_absolute_difference": delta,
        "basic_prb_core_seconds": base["total_core_solve_time"],
        "accelerated_v2_core_seconds": float(solved.total_runtime),
        "accelerated_v2_child_wall_seconds": elapsed,
        "speedup_basic_over_v2": float(base["total_core_solve_time"]) / float(solved.total_runtime),
        "iterations": len(solved.iterations),
        "master_runtime": float(solved.master_runtime),
        "oracle_runtime": float(solved.separation_runtime),
        "certification_runtime": float(solved.certification_runtime),
        "model_build_runtime": float(solved.oracle_model_build_runtime),
        "parallel_worker_count": int(solved.parallel_worker_count),
        "cut_count": int(solved.unique_product_cuts),
        "cache_hits": int(solved.cache_hits),
        "product_solves_avoided": int(solved.product_solves_avoided),
        "final_relative_gap": float(solved.final_relative_gap),
        "gurobi_version": ".".join(str(n) for n in gp.gurobi.version()),
        "python_version": platform.python_version(),
        "first_stage_solution": asdict(solved.solution),
    }
    if not certified or not paired:
        # Store diagnostic only in isolated attempt logs; never mark this condition complete.
        fail = output_root(workers) / "failed_diagnostics" / f"{cid}.{uuid4().hex}.json"
        write_json(fail, {"result":result,"identity":ident})
        raise RuntimeError(f"CERTIFICATION FAILED for {cid}: exact={certified}, objective_delta={delta}")
    temp = output.parent / f".tmp-{cid}-{uuid4().hex}"
    temp.mkdir(parents=True, exist_ok=False)
    try:
        result_file = temp / "result.json"
        write_json(result_file, result)
        write_json(temp / "provenance.json", {
            "identity": ident, "result_sha256": sha256(result_file),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(f"Refuse overwrite: {output}")
        os.replace(temp, output)
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
    print(f"[CERTIFIED] {cid}: {solved.total_runtime:.3f}s; speedup={result['speedup_basic_over_v2']:.2f}x", flush=True)


def tree_rss_gib(pid: int):
    try:
        proc = psutil.Process(pid)
        group = [proc, *proc.children(recursive=True)]
    except psutil.Error:
        return 0.0
    total = 0
    for p in group:
        try:
            total += p.memory_info().rss
        except psutil.Error:
            continue
    return total / 2**30


def terminate_tree(pid: int):
    try:
        p = psutil.Process(pid)
        group = [*p.children(recursive=True), p]
    except psutil.Error:
        return
    for member in group:
        try: member.terminate()
        except psutil.Error: pass
    _, alive = psutil.wait_procs(group, timeout=3)
    for member in alive:
        try: member.kill()
        except psutil.Error: pass


def monitored_run(size: str, seed: int, workers: int):
    instance, prep, base, hashes = fetch_inputs(size,seed)
    ident = identity(size,seed,workers,hashes)
    cid = cond_id(size,seed).format(workers=workers)
    target = output_root(workers) / "runs" / cid
    if verify_existing(target, ident):
        print(f"[VERIFIED SKIP] {cid}", flush=True)
        return
    caps = RESOURCE[size]
    available = psutil.virtual_memory().available / 2**30
    if available < caps["min_available"]:
        raise RuntimeError(f"PREFLIGHT BLOCKED: {size}, available={available:.2f} GiB < {caps['min_available']} GiB")
    log_parent = output_root(workers) / "worker_logs" / cid
    attempt = 1
    while (log_parent / f"attempt-{attempt:03d}").exists():
        attempt += 1
    log_dir = log_parent / f"attempt-{attempt:03d}"
    log_dir.mkdir(parents=True, exist_ok=False)
    cmd = [sys.executable,str(Path(__file__).resolve()),"--worker-condition",size,str(seed),"--workers",str(workers)]
    peak = 0.0
    start = perf_counter()
    reason = None
    with (log_dir / "stdout.log").open("w",encoding="utf-8") as stdout, (log_dir / "stderr.log").open("w",encoding="utf-8") as stderr:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=stdout, stderr=stderr)
        while proc.poll() is None:
            peak = max(peak, tree_rss_gib(proc.pid))
            avail_now = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - start
            if peak >= caps["max_tree"]:
                reason = f"PROCESS_MEMORY_CAP {peak:.2f} GiB >= {caps['max_tree']} GiB"
            elif avail_now <= SYSTEM_FLOOR_GIB:
                reason = f"SYSTEM_MEMORY_FLOOR {avail_now:.2f} GiB"
            elif elapsed >= CONDITION_TIMEOUT_SECONDS:
                reason = "TIME_LIMIT"
            if reason:
                terminate_tree(proc.pid)
                break
            sleep(POLL_SECONDS)
        return_code = proc.poll()
    monitor = {"condition_id":cid,"attempt":attempt,"peak_tree_rss_gib":peak,
               "elapsed_wall_seconds":perf_counter()-start,"stop_reason":reason,
               "return_code":return_code,"workers":workers,"available_memory_before_gib":available}
    write_json(log_dir / "monitor.json", monitor)
    if reason or return_code != 0:
        raise RuntimeError(f"{cid} failed: {reason or return_code}; see {log_dir}")
    if not verify_existing(target, ident):
        raise RuntimeError(f"No certified output after worker exit: {cid}")
    print(f"[DONE] {cid} | peak RSS {peak:.2f} GiB", flush=True)


def main():
    parser=argparse.ArgumentParser(description="Independent monitored V2 on 30 frozen Scaling instances")
    parser.add_argument("--size", choices=["L10","XL10","XXL10","ALL"], default="ALL")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--worker-condition", nargs=2, metavar=("SIZE","SEED"), help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not (1 <= args.workers <= 8):
        parser.error("--workers must be between 1 and 8")
    if args.seed is not None and args.seed not in SEEDS:
        parser.error("--seed must be one of 20260921..20260930")
    if args.worker_condition:
        child(args.worker_condition[0],int(args.worker_condition[1]),args.workers)
        return
    if not (FROZEN_ROOT / "instances").is_dir():
        raise FileNotFoundError(f"Frozen Scaling instances not present: {FROZEN_ROOT}")
    sizes = tuple(SIZES) if args.size == "ALL" else (args.size,)
    seeds = (args.seed,) if args.seed is not None else tuple(SEEDS)
    print(f"Git {commit()} | sizes={sizes} | seeds={len(seeds)} | workers={args.workers} | output={output_root(args.workers)}",flush=True)
    for size in sizes:
        for seed in seeds:
            if args.dry_run:
                _,_,_,hashes = fetch_inputs(size,seed)
                print(f"[READY] {size}/{seed} : {hashes['instance'][:12]}")
            else:
                monitored_run(size,seed,args.workers)
    if not args.dry_run and args.size == "ALL" and args.seed is None:
        rows = []
        for size in SIZES:
            for seed in SEEDS:
                cid = cond_id(size, seed).format(workers=args.workers)
                result_path = output_root(args.workers) / "runs" / cid / "result.json"
                r = read_json(result_path)
                rows.append({key:r[key] for key in (
                    "size", "seed", "basic_prb_core_seconds", "accelerated_v2_core_seconds",
                    "speedup_basic_over_v2", "objective_absolute_difference", "iterations",
                    "parallel_worker_count", "exact_certification", "objective_pair_certified"
                )})
        summary_path = output_root(args.workers) / "comparison.csv"
        with summary_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"[SUMMARY] {summary_path}",flush=True)
    print("[FINISHED] all requested V2 conditions completed or verified",flush=True)


if __name__ == "__main__":
    main()
