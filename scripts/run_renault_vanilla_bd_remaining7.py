"""Run the frozen remaining-seven Renault Vanilla/PRB development protocol."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[1]
PILOT_PATH = ROOT / "experiments/run_renault_vanilla_bd_pilot.py"
BASELINE_ROOT = ROOT / "experiments/results/renault_vanilla_bd_pilot_210202_development_v1"
CASES = ("210628", "210129", "210310", "210330", "210323", "210428", "210611")
BASELINE_COMMIT = "5b9e113"
BASELINE_SCRIPT_SHA256 = "e1781528f00f68f8723555fb486d6ac78952a6c4d46fc51e7013952251f09bc7"

SPEC = importlib.util.spec_from_file_location("renault_vanilla_pilot", PILOT_PATH)
assert SPEC and SPEC.loader
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_baseline() -> dict[str, Any]:
    manifest = BASELINE_ROOT / "sha256.txt"
    failures = []
    entries = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = BASELINE_ROOT / Path(relative)
        entries += 1
        if not path.is_file() or _sha256(path) != expected:
            failures.append(relative)
    summary = json.loads((BASELINE_ROOT / "summary.json").read_text(encoding="utf-8"))
    if failures or summary.get("valid_exact_pair") is not True:
        raise RuntimeError(f"210202 baseline audit failed: {failures}")
    committed_script = subprocess.check_output(
        ["git", "show", f"{BASELINE_COMMIT}:experiments/run_renault_vanilla_bd_pilot.py"],
        cwd=ROOT,
    )
    if hashlib.sha256(committed_script).hexdigest() != BASELINE_SCRIPT_SHA256:
        raise RuntimeError("210202 committed code identity mismatch")
    return {
        "commit": BASELINE_COMMIT,
        "script_sha256": BASELINE_SCRIPT_SHA256,
        "manifest_sha256": _sha256(manifest),
        "manifest_entries": entries,
        "manifest_failures": failures,
        "valid_exact_pair": True,
    }


def static_protocol_audit() -> dict[str, Any]:
    cases = {}
    for case_id in CASES:
        loaded = pilot.load_frozen_renault_case(case_id)
        instance = loaded["instance"]
        scenario_count = sum(
            math.comb(instance.num_regions * instance.num_products, size)
            for size in range(loaded["gamma"] + 1)
        )
        if scenario_count > pilot.MAX_SCENARIOS:
            raise RuntimeError(f"{case_id} exceeds scenario cap: {scenario_count}")
        cases[case_id] = {
            "dimensions": [
                instance.num_depots,
                instance.num_regions,
                instance.num_products,
            ],
            "budget": loaded["budget"],
            "Gamma": loaded["gamma"],
            "lambda_R": loaded["lambda_r"],
            "scenario_count": scenario_count,
            "identity": loaded["identity"],
        }
    return {
        "status": "PASS",
        "cases": cases,
        "fixed_limits": {
            "time_seconds_per_method": pilot.TIME_LIMIT_SECONDS,
            "process_tree_gib": pilot.PROCESS_MEMORY_GIB,
            "start_available_gib": pilot.START_AVAILABLE_MEMORY_GIB,
            "system_available_floor_gib": pilot.SYSTEM_MEMORY_FLOOR_GIB,
            "monitor_interval_seconds": pilot.MONITOR_INTERVAL_SECONDS,
            "max_scenarios": pilot.MAX_SCENARIOS,
        },
    }


def _result_row(case_id: str, method: str, result: dict[str, Any]) -> dict[str, Any]:
    certification = result.get("independent_global_certification", {})
    return {
        "case": case_id,
        "method": method,
        "status": result.get("status"),
        "objective": result.get("objective"),
        "certified_recourse": certification.get("certified_recourse"),
        "exact_certification_pass": result.get("exact_certification_pass"),
        "cut_validity_pass": result.get("cut_validity_pass"),
        "strong_duality_residual": certification.get("strong_duality_residual"),
        "algorithm_seconds": result.get("algorithm_seconds"),
        "independent_certification_seconds": result.get(
            "independent_certification_seconds"
        ),
        "total_seconds": result.get("total_seconds"),
        "oracle_seconds": result.get("oracle_seconds"),
        "iterations": result.get("iterations"),
        "cut_count": result.get("cut_count"),
        "peak_process_tree_rss_gib": result.get("peak_process_tree_rss_gib"),
        "resource_stop_reason": result.get("resource_stop_reason"),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(output_root: Path) -> dict[str, Any]:
    baseline = json.loads((BASELINE_ROOT / "summary.json").read_text(encoding="utf-8"))
    all_results = {"210202": {"vanilla": baseline["vanilla"], "prb": baseline["prb"]}}
    for case_id in CASES:
        all_results[case_id] = {
            method: json.loads(
                (output_root / case_id / f"{method}_outcome.json").read_text(encoding="utf-8")
            )
            for method in ("vanilla", "prb")
        }
    rows = [
        _result_row(case_id, method, result)
        for case_id, methods in all_results.items()
        for method, result in methods.items()
    ]
    _write_csv(output_root / "renault_vanilla_prb_8case_results.csv", rows)
    pairs = []
    for case_id, methods in all_results.items():
        vanilla, prb = methods["vanilla"], methods["prb"]
        difference = (
            abs(vanilla["objective"] - prb["objective"])
            if vanilla.get("objective") is not None and prb.get("objective") is not None
            else None
        )
        valid = bool(
            vanilla.get("exact_certification_pass") is True
            and prb.get("exact_certification_pass") is True
            and difference is not None
            and difference <= pilot.OBJECTIVE_TOLERANCE
        )
        pairs.append(
            {
                "case": case_id,
                "valid_exact_pair": valid,
                "objective_difference": difference,
                "vanilla_total_seconds": vanilla.get("total_seconds"),
                "prb_total_seconds": prb.get("total_seconds"),
                "vanilla_over_prb_speedup": (
                    vanilla["total_seconds"] / prb["total_seconds"] if valid else None
                ),
                "winner": (
                    "PRB" if valid and prb["total_seconds"] < vanilla["total_seconds"]
                    else "VANILLA" if valid and vanilla["total_seconds"] < prb["total_seconds"]
                    else "TIE" if valid else "NOT_PAIRED"
                ),
            }
        )
    _write_csv(output_root / "renault_vanilla_prb_8case_pairs.csv", pairs)
    valid_pairs = [row for row in pairs if row["valid_exact_pair"]]
    speedups = [row["vanilla_over_prb_speedup"] for row in valid_pairs]
    summary = {
        "expected_cases": 8,
        "valid_exact_pairs": len(valid_pairs),
        "prb_wins": sum(row["winner"] == "PRB" for row in valid_pairs),
        "vanilla_wins": sum(row["winner"] == "VANILLA" for row in valid_pairs),
        "ties": sum(row["winner"] == "TIE" for row in valid_pairs),
        "mean_vanilla_total_seconds": statistics.fmean(
            row["vanilla_total_seconds"] for row in valid_pairs
        ) if valid_pairs else None,
        "mean_prb_total_seconds": statistics.fmean(
            row["prb_total_seconds"] for row in valid_pairs
        ) if valid_pairs else None,
        "geometric_mean_vanilla_over_prb_speedup": (
            math.exp(statistics.fmean(math.log(value) for value in speedups))
            if speedups else None
        ),
        "pairs": pairs,
    }
    _write_json(output_root / "renault_vanilla_prb_8case_summary.json", summary)
    return summary


def _write_hashes(output_root: Path) -> None:
    files = sorted(
        path for path in output_root.rglob("*")
        if path.is_file() and path.name != "sha256.txt"
    )
    lines = [
        f"{_sha256(path)}  {path.relative_to(output_root).as_posix()}" for path in files
    ]
    (output_root / "sha256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite development batch: {output_root}")
    available = psutil.virtual_memory().available / 2**30
    if available < pilot.START_AVAILABLE_MEMORY_GIB:
        raise RuntimeError(
            f"batch preflight failed: {available:.3f} GiB < {pilot.START_AVAILABLE_MEMORY_GIB:.3f} GiB"
        )
    output_root.mkdir(parents=True)
    _write_json(output_root / "baseline_audit.json", verify_baseline())
    _write_json(output_root / "static_protocol_audit.json", static_protocol_audit())
    _write_json(
        output_root / "execution_identity.json",
        {
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "git_status_porcelain": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).splitlines(),
            "runner_sha256": _sha256(PILOT_PATH),
            "batch_sha256": _sha256(Path(__file__).resolve()),
            "python_executable": sys.executable,
        },
    )
    for case_id in CASES:
        case_root = output_root / case_id
        case_root.mkdir()
        for method in ("vanilla", "prb"):
            outcome = pilot._run_monitored(
                method, case_root, pilot.TIME_LIMIT_SECONDS, case_id
            )
            if outcome.get("resource_stop_reason") not in {
                None, "TIME_LIMIT", "RESOURCE_PROCESS_CAP", "RESOURCE_SYSTEM_CAP"
            }:
                raise RuntimeError(f"unexpected integrity failure: {case_id} {method}")
    result = summarize(output_root)
    _write_hashes(output_root)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "experiments/results/renault_vanilla_bd_remaining7_development_v1",
    )
    args = parser.parse_args()
    result = run(args.output_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
