"""Paired, same-environment Basic PRB vs Accelerated PRB V2 benchmark.

Place this file AND run_accelerated_prb_v2_scaling30.py in experiments/ inside
Hoshino12172003/budget-inventory-benders, branch
experiment/xxl10-four-method-final-archive.

This does not alter historical Scaling/E2-E7 results. It reads the exact
frozen 30 instances and uses a dedicated results directory.

Usage:
  python experiments/run_prb_basic_v2_fair_scaling30.py --dry-run
  python experiments/run_prb_basic_v2_fair_scaling30.py --size L10 --seed 20260921 --workers 2
  python experiments/run_prb_basic_v2_fair_scaling30.py --size ALL --workers 2

Basic and V2 are run as isolated processes on the same machine, under the
same solver-native profile, same frozen data, same memory/time guardrails,
and with Gurobi Threads=1 per model. V2's 2 workers are intentionally a
parallel implementation feature and must be disclosed as such.
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
sys.path.insert(0, str(ROOT / 'src'))
# The checked, read-only frozen-input loader from the earlier V2 runner.
import run_accelerated_prb_v2_scaling30 as frozen

METHODS = ('basic', 'v2')
TIMEOUT = 900
POLL = 0.25


def root_for(workers: int) -> Path:
    return ROOT / f'experiments/results/prb_basic_v2_fair_scaling30_W{workers}'


def identity(size: str, seed: int, method: str, workers: int, source_hashes: dict) -> dict:
    import gurobipy as gp
    return {
        'experiment': 'PRB_BASIC_V2_SAME_ENV_SCALING30',
        'size': size, 'seed': seed, 'method': method,
        'v2_workers': workers, 'gurobi_threads_per_model': 1,
        'python': platform.python_version(),
        'gurobi': list(gp.gurobi.version()),
        'os': platform.platform(), 'cpu_count': os.cpu_count(),
        'git_commit': frozen.commit(),
        'runner_sha256': frozen.sha256(Path(__file__)),
        'frozen_loader_sha256': frozen.sha256(Path(frozen.__file__)),
        'model_hashes': frozen.code_hashes(),
        'input_hashes': source_hashes,
        'Gamma': 2, 'beta': 1.0, 'lambda_R': 0.05,
        'relative_gap': 1e-6, 'cut_tolerance': 1e-7,
        'objective_tolerance': 1e-4, 'max_iterations': 500,
    }


def destination(size: str, seed: int, method: str, workers: int) -> Path:
    return root_for(workers) / 'runs' / f'{size}_S{seed}_{method.upper()}'


def verified(path: Path, ident: dict) -> bool:
    if not path.exists():
        return False
    result_path, prov_path = path / 'result.json', path / 'provenance.json'
    if not result_path.is_file() or not prov_path.is_file():
        raise RuntimeError(f'Incomplete result, refusing overwrite: {path}')
    result = frozen.read_json(result_path)
    prov = frozen.read_json(prov_path)
    if (prov.get('identity') != ident or
        prov.get('result_sha256') != frozen.sha256(result_path) or
        result.get('exact_certification') is not True or
        result.get('frozen_objective_match') is not True):
        raise RuntimeError(f'Invalid/stale result, refusing reuse: {path}')
    return True


def run_child(size: str, seed: int, method: str, workers: int) -> None:
    import gurobipy as gp
    from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
    from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import solve_accelerated_prb_benders

    instance, prep, frozen_base, hashes = frozen.fetch_inputs(size, seed)
    ident = identity(size, seed, method, workers, hashes)
    path = destination(size, seed, method, workers)
    if verified(path, ident):
        print(f'[VERIFIED SKIP] {method} {size}/{seed}', flush=True)
        return

    # Apply common Gurobi default-Env thread budget; V2 worker Env additionally
    # sets Threads=1 itself. This keeps the LP/MIP native solver profile aligned.
    gp.setParam('Threads', 1)
    args = (instance, instance.initial_inventory, float(prep['budget']), 2, 0.05)
    common = dict(relative_gap_tolerance=1e-6, cut_tolerance=1e-7, max_iterations=500)
    started = perf_counter()
    if method == 'basic':
        solved = solve_prb_benders(*args, **common)
        worker_count = 1
    elif method == 'v2':
        solved = solve_accelerated_prb_benders(*args, parallel_workers=workers,
                                               _oracle_backend='process', **common)
        worker_count = int(solved.parallel_worker_count)
    else:
        raise ValueError(method)
    child_elapsed = perf_counter() - started
    exact = (solved.status == 'OPTIMAL' and
             solved.exact_certification_pass and
             solved.global_risk_budget_coupling_pass and
             solved.final_relative_gap <= 1e-6)
    delta_frozen = abs(float(solved.solution.objective) - float(frozen_base['final_objective']))
    result = {
        'method': method, 'size': size, 'seed': seed,
        'instance_hash': prep['instance_hash'], 'x0_hash': prep['x0_hash'],
        'budget': prep['budget'], 'Gamma': 2, 'beta': 1.0, 'lambda_R': 0.05,
        'objective': float(solved.solution.objective),
        'original_frozen_basic_objective': float(frozen_base['final_objective']),
        'objective_difference_from_frozen': delta_frozen,
        'frozen_objective_match': delta_frozen <= 1e-4,
        'exact_certification': bool(exact),
        'core_time_seconds': float(solved.total_runtime),
        'child_solve_wall_seconds': child_elapsed,
        'master_time_seconds': float(solved.master_runtime),
        'oracle_time_seconds': float(solved.separation_runtime),
        'certification_time_seconds': float(solved.certification_runtime),
        'iterations': len(solved.iterations),
        'unique_product_cuts': solved.unique_product_cuts,
        'worker_count': worker_count, 'gurobi_threads_per_model': 1,
        'relative_gap': float(solved.final_relative_gap),
        'first_stage_solution': asdict(solved.solution),
    }
    if method == 'v2':
        result['cache_hits'] = solved.cache_hits
        result['product_solves_avoided'] = solved.product_solves_avoided
        result['product_model_build_seconds'] = solved.oracle_model_build_runtime
    if not exact or delta_frozen > 1e-4:
        fail = root_for(workers) / 'failed_diagnostics' / f'{size}_{seed}_{method}_{uuid4().hex}.json'
        frozen.write_json(fail, {'result': result, 'identity': ident})
        raise RuntimeError(f'NOT CERTIFIED: {method} {size}/{seed}: exact={exact}, delta={delta_frozen}')

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f'.tmp-{path.name}-{uuid4().hex}'
    temp.mkdir(parents=True)
    try:
        rpath = temp / 'result.json'
        frozen.write_json(rpath, result)
        frozen.write_json(temp / 'provenance.json', {
            'identity': ident, 'result_sha256': frozen.sha256(rpath),
            'saved_at_utc': datetime.now(timezone.utc).isoformat(),
        })
        if path.exists():
            raise FileExistsError(f'Will not overwrite: {path}')
        os.replace(temp, path)
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
    print(f'[CERTIFIED] {method} {size}/{seed}: {solved.total_runtime:.3f} s', flush=True)


def monitored(size: str, seed: int, method: str, workers: int) -> None:
    _, _, _, hashes = frozen.fetch_inputs(size, seed)
    ident = identity(size, seed, method, workers, hashes)
    target = destination(size, seed, method, workers)
    if verified(target, ident):
        print(f'[SKIP CERTIFIED] {method} {size}/{seed}', flush=True)
        return
    cap = frozen.RESOURCE[size]
    before = psutil.virtual_memory().available / 2**30
    if before < cap['min_available']:
        raise RuntimeError(f'LOW AVAILABLE MEMORY: {before:.2f} GiB on {size}')
    logdir = root_for(workers) / 'logs' / f'{size}_S{seed}_{method.upper()}'
    attempt = 1
    while (logdir / f'attempt-{attempt:03d}').exists():
        attempt += 1
    logdir = logdir / f'attempt-{attempt:03d}'
    logdir.mkdir(parents=True)
    command = [sys.executable, str(Path(__file__).resolve()), '--worker-condition',
               size, str(seed), method, '--workers', str(workers)]
    t0, peak, reason = perf_counter(), 0.0, None
    with (logdir / 'stdout.log').open('w', encoding='utf-8') as stdout, \
         (logdir / 'stderr.log').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            peak = max(peak, frozen.tree_rss_gib(process.pid))
            available = psutil.virtual_memory().available / 2**30
            elapsed = perf_counter() - t0
            if peak >= cap['max_tree']:
                reason = f'PROCESS_MEMORY_CAP: {peak:.2f} >= {cap["max_tree"]} GiB'
            elif available <= frozen.SYSTEM_FLOOR_GIB:
                reason = f'SYSTEM_MEMORY_FLOOR: {available:.2f} GiB'
            elif elapsed >= TIMEOUT:
                reason = 'TIME_LIMIT'
            if reason:
                frozen.terminate_tree(process.pid)
                break
            sleep(POLL)
        code = process.poll()
    record = {'method': method, 'size': size, 'seed': seed,
              'exit_code': code, 'stop_reason': reason,
              'preflight_available_gib': before, 'peak_process_tree_rss_gib': peak,
              'elapsed_monitored_wall_seconds': perf_counter() - t0,
              'workers': 1 if method == 'basic' else workers}
    frozen.write_json(logdir / 'monitor.json', record)
    if reason or code != 0:
        raise RuntimeError(f'FAILED {method} {size}/{seed}: {reason or code}; see {logdir}')
    if not verified(target, ident):
        raise RuntimeError(f'No certified result for {method} {size}/{seed}')
    print(f'[DONE] {method} {size}/{seed}; peak tree memory={peak:.2f} GiB', flush=True)


def write_comparison(sizes, seeds, workers):
    rows = []
    for size in sizes:
        for seed in seeds:
            bpath = destination(size, seed, 'basic', workers) / 'result.json'
            vpath = destination(size, seed, 'v2', workers) / 'result.json'
            if not bpath.is_file() or not vpath.is_file():
                continue
            b, v = frozen.read_json(bpath), frozen.read_json(vpath)
            difference = abs(b['objective'] - v['objective'])
            if difference > 1e-4 or not (b['exact_certification'] and v['exact_certification']):
                raise RuntimeError(f'Paired mismatch {size}/{seed}: {difference}')
            rows.append({
                'size': size, 'seed': seed,
                'basic_core_seconds_new': b['core_time_seconds'],
                'v2_core_seconds_new': v['core_time_seconds'],
                'basic_over_v2_speedup_new': b['core_time_seconds'] / v['core_time_seconds'],
                'basic_child_wall_seconds': b['child_solve_wall_seconds'],
                'v2_child_wall_seconds': v['child_solve_wall_seconds'],
                'basic_iterations': b['iterations'], 'v2_iterations': v['iterations'],
                'basic_workers': 1, 'v2_workers': v['worker_count'],
                'objective_difference': difference,
                'both_certified': True,
            })
    root = root_for(workers)
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'paired_comparison_same_env.csv'
    if rows:
        with path.open('w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(f'[PAIRS] {len(rows)}; {path}', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--size', choices=[*frozen.SIZES, 'ALL'], default='ALL')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--workers', type=int, default=2, help='V2 workers (1-8); Basic is serial')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--worker-condition', nargs=3, metavar=('SIZE', 'SEED', 'METHOD'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.workers not in range(1, 9):
        parser.error('--workers must be 1..8')
    if args.seed is not None and args.seed not in frozen.SEEDS:
        parser.error('--seed must be 20260921..20260930')
    if args.worker_condition:
        size, seed, method = args.worker_condition
        if size not in frozen.SIZES or int(seed) not in frozen.SEEDS or method not in METHODS:
            parser.error('bad worker condition')
        run_child(size, int(seed), method, args.workers)
        return
    sizes = tuple(frozen.SIZES) if args.size == 'ALL' else (args.size,)
    seeds = tuple(frozen.SEEDS) if args.seed is None else (args.seed,)
    print(f'Pair-run same-env: sizes={sizes}, seed count={len(seeds)}, V2 workers={args.workers}', flush=True)
    for size in sizes:
        for seed in seeds:
            _, _, _, hashes = frozen.fetch_inputs(size, seed)
            if args.dry_run:
                print(f'[READY] {size}/{seed} frozen={hashes["instance"][:12]}', flush=True)
                continue
            # Alternate A-B / B-A ordering to reduce systematic execution-order bias.
            ordering = METHODS if seed % 2 else METHODS[::-1]
            for method in ordering:
                monitored(size, seed, method, args.workers)
            write_comparison(sizes, seeds, args.workers)
    if not args.dry_run:
        print('[FINISHED] All requested paired methods exact-certified, no old archive modified.', flush=True)


if __name__ == '__main__':
    main()
