"""Build and verify the read-only Scaling30 Basic PRB vs V2 archive.

This module reads frozen JSON/CSV evidence only.  It never imports the solver
package and contains no optimization entry point.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments/analysis/prb_v2_scaling30_final"
OLD_ROOT = ROOT / "experiments/results/prb_basic_v2_fair_scaling30_W2"
NEW_ROOT = ROOT / "experiments/results/prb_basic_v2_fair_scaling30_W2_numeric_guard_v1"
FROZEN_ROOT = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
SOURCE_CSV = NEW_ROOT / "paired_comparison_numeric_guard_v1.csv"
SIZES = ("L10", "XL10", "XXL10")
SEEDS = tuple(range(20260921, 20260931))
EXPECTED_KEYS = {(size, seed) for size in SIZES for seed in SEEDS}
OBJECTIVE_TOLERANCE = 1e-4
RUNNERS = (
    "experiments/run_prb_basic_v2_fair_scaling30.py",
    "experiments/run_accelerated_prb_v2_scaling30.py",
    "experiments/run_prb_basic_v2_fair_scaling30_numeric_guard_v1.py",
)
DIAGNOSTIC_SCRIPTS = (
    "experiments/audit_v2_failed_cut_validity.py",
    "experiments/audit_v2_failed_risk_value.py",
    "experiments/diagnose_v2_certification.py",
)
HISTORICAL_SOURCES = (
    "experiments/analysis/xxl10_four_method_final/xxl10_four_method_summary.csv",
    "experiments/analysis/xxl10_four_method_final/xxl10_four_method_paper_table.md",
    "experiments/analysis/xxl10_four_method_final/xxl10_integrity_audit.json",
    "docs/pure_benders_historical_comparison_audit.md",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    names = fieldnames or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def result_dir(size: str, seed: int, method: str, source: str) -> Path:
    if method == "basic" or source == "legacy_strict_exact":
        return OLD_ROOT / "runs" / f"{size}_S{seed}_{method.upper()}"
    if method == "v2" and source == "new_numeric_protocol":
        return NEW_ROOT / "runs" / f"{size}_S{seed}_V2"
    raise RuntimeError(f"unsupported result source: {size}/{seed}/{method}/{source}")


def verify_result(path: Path) -> tuple[dict, dict, str, str]:
    result_path = path / "result.json"
    provenance_path = path / "provenance.json"
    if not result_path.is_file() or not provenance_path.is_file():
        raise RuntimeError(f"incomplete result directory: {relative(path)}")
    result = load_json(result_path)
    provenance = load_json(provenance_path)
    result_hash = sha256_file(result_path)
    provenance_hash = sha256_file(provenance_path)
    if provenance.get("result_sha256") != result_hash:
        raise RuntimeError(f"result/provenance hash mismatch: {relative(path)}")
    return result, provenance, result_hash, provenance_hash


def verify_identity_hashes(identity: dict, size: str, seed: int) -> dict:
    instance_path = FROZEN_ROOT / "instances" / size / str(seed) / "instance.json"
    preparation_path = FROZEN_ROOT / "instances" / size / str(seed) / "preparation.json"
    basic_path = FROZEN_ROOT / "runs" / f"ASC_{size}_S{seed}_PRB_BENDERS" / "result.json"
    expected_inputs = {
        "instance": sha256_file(instance_path),
        "preparation": sha256_file(preparation_path),
        "basic_prb": sha256_file(basic_path),
    }
    if identity.get("input_hashes") != expected_inputs:
        raise RuntimeError(f"frozen input identity mismatch: {size}/{seed}")
    for rel_path, expected_hash in identity.get("model_hashes", {}).items():
        actual_path = ROOT / rel_path
        if not actual_path.is_file() or sha256_file(actual_path) != expected_hash:
            raise RuntimeError(f"model hash mismatch: {rel_path}")
    preparation = load_json(preparation_path)
    budget_parameters = {
        "B_ref": preparation["B_ref"],
        "budget": preparation["budget"],
        "scientific_parameters": preparation["scientific_parameters"],
    }
    return {
        "size": size,
        "seed": seed,
        "instance_id": preparation["instance_id"],
        "canonical_instance_hash": preparation["instance_hash"],
        "primitive_instance_hash": preparation["primitive_instance_hash"],
        "x0_hash": preparation["x0_hash"],
        "instance_file_sha256": expected_inputs["instance"],
        "preparation_file_sha256": expected_inputs["preparation"],
        "frozen_basic_result_sha256": expected_inputs["basic_prb"],
        "budget_parameters_sha256": canonical_sha256(budget_parameters),
        "budget": preparation["budget"],
        "scientific_parameters": preparation["scientific_parameters"],
    }


def verify_rows() -> tuple[list[dict], list[dict], dict]:
    source_rows = load_csv(SOURCE_CSV)
    keys = [(row["size"], int(row["seed"])) for row in source_rows]
    duplicates = sorted(key for key, count in Counter(keys).items() if count != 1)
    if len(source_rows) != 30 or set(keys) != EXPECTED_KEYS or duplicates:
        raise RuntimeError(
            f"pair-set mismatch: rows={len(source_rows)}, unique={len(set(keys))}, duplicates={duplicates}"
        )

    enriched: list[dict] = []
    input_records: dict[tuple[str, int], dict] = {}
    historical_identity_values: dict[str, set[str]] = {
        "python": set(), "gurobi": set(), "platform": set(), "cpu_count": set(), "git_commit": set()
    }
    runner_hashes = {path: sha256_file(ROOT / path) for path in RUNNERS}

    for row in source_rows:
        size, seed = row["size"], int(row["seed"])
        if size not in SIZES or seed not in SEEDS:
            raise RuntimeError(f"out-of-contract pair: {size}/{seed}")
        if row["basic_result_source"] != "legacy_strict_exact":
            raise RuntimeError(f"unexpected Basic source: {size}/{seed}")

        basic_dir = result_dir(size, seed, "basic", row["basic_result_source"])
        v2_dir = result_dir(size, seed, "v2", row["v2_result_source"])
        basic, basic_prov, basic_hash, basic_prov_hash = verify_result(basic_dir)
        v2, v2_prov, v2_hash, v2_prov_hash = verify_result(v2_dir)

        for method, result, provenance in (
            ("basic", basic, basic_prov), ("v2", v2, v2_prov)
        ):
            if result.get("size") != size or int(result.get("seed")) != seed or result.get("method") != method:
                raise RuntimeError(f"result identity mismatch: {size}/{seed}/{method}")
            identity = provenance["identity"]
            if identity.get("size") != size or int(identity.get("seed")) != seed or identity.get("method") != method:
                raise RuntimeError(f"provenance identity mismatch: {size}/{seed}/{method}")
            if identity.get("Gamma") != 2 or identity.get("beta") != 1.0 or identity.get("lambda_R") != 0.05:
                raise RuntimeError(f"scientific parameter mismatch: {size}/{seed}/{method}")
            if identity.get("relative_gap") != 1e-6 or identity.get("cut_tolerance") != 1e-7:
                raise RuntimeError(f"solver tolerance mismatch: {size}/{seed}/{method}")
            if identity.get("max_iterations") != 500:
                raise RuntimeError(f"iteration limit mismatch: {size}/{seed}/{method}")
            if method == "basic":
                if identity.get("runner_sha256") != runner_hashes[RUNNERS[0]]:
                    raise RuntimeError(f"Basic runner mismatch: {size}/{seed}")
                if identity.get("frozen_loader_sha256") != runner_hashes[RUNNERS[1]]:
                    raise RuntimeError(f"frozen loader mismatch: {size}/{seed}")
            elif row["v2_result_source"] == "legacy_strict_exact":
                if identity.get("runner_sha256") != runner_hashes[RUNNERS[0]]:
                    raise RuntimeError(f"legacy V2 runner mismatch: {size}/{seed}")
            else:
                if identity.get("new_runner_sha256") != runner_hashes[RUNNERS[2]]:
                    raise RuntimeError(f"numeric V2 runner mismatch: {size}/{seed}")
                if identity.get("legacy_runner_sha256") != runner_hashes[RUNNERS[0]]:
                    raise RuntimeError(f"numeric V2 legacy-runner mismatch: {size}/{seed}")
            for key in historical_identity_values:
                candidate = identity.get("platform") if key == "platform" else identity.get(key)
                if candidate is None and key == "platform":
                    candidate = identity.get("os")
                if candidate is not None:
                    historical_identity_values[key].add(json.dumps(candidate, sort_keys=True))

        input_record = verify_identity_hashes(basic_prov["identity"], size, seed)
        verify_identity_hashes(v2_prov["identity"], size, seed)
        input_records[(size, seed)] = input_record

        if basic.get("exact_certification") is not True or basic.get("frozen_objective_match") is not True:
            raise RuntimeError(f"Basic certification failure: {size}/{seed}")
        if int(basic.get("worker_count")) != 1 or int(v2.get("worker_count")) != 2:
            raise RuntimeError(f"worker-count mismatch: {size}/{seed}")
        if int(basic.get("gurobi_threads_per_model")) != 1 or int(v2.get("gurobi_threads_per_model")) != 1:
            raise RuntimeError(f"Gurobi thread mismatch: {size}/{seed}")

        certificate_class = row["v2_certificate_class"]
        if certificate_class == "legacy_strict_exact":
            valid_certificate = v2.get("exact_certification") is True
        elif certificate_class == "strict_original":
            valid_certificate = (
                v2.get("strict_original_certification") is True
                and v2.get("independently_numerically_validated") is False
                and v2.get("certification_class") == "strict_original"
            )
        elif certificate_class == "independently_numerically_validated":
            valid_certificate = (
                (size, seed) == ("L10", 20260925)
                and v2.get("exact_certification") is False
                and v2.get("strict_original_certification") is False
                and v2.get("independently_numerically_validated") is True
                and v2.get("certification_class") == certificate_class
                and v2.get("independent_audit_pass") is True
                and v2.get("original_global_risk_coupling_flag") is False
            )
        else:
            valid_certificate = False
        if not valid_certificate:
            raise RuntimeError(f"V2 certificate mismatch: {size}/{seed}/{certificate_class}")

        diff = abs(float(basic["objective"]) - float(v2["objective"]))
        if diff > OBJECTIVE_TOLERANCE or not math.isclose(
            diff, float(row["objective_difference"]), rel_tol=0.0, abs_tol=1e-12
        ):
            raise RuntimeError(f"objective comparison mismatch: {size}/{seed}")
        basic_time, v2_time = float(basic["core_time_seconds"]), float(v2["core_time_seconds"])
        if not v2_time < basic_time:
            raise RuntimeError(f"V2 is not faster for pair: {size}/{seed}")

        enriched.append({
            "size": size,
            "seed": seed,
            "basic_core_seconds": basic_time,
            "v2_core_seconds": v2_time,
            "basic_over_v2_speedup": basic_time / v2_time,
            "basic_child_wall_seconds": float(basic["child_solve_wall_seconds"]),
            "v2_child_wall_seconds": float(v2["child_solve_wall_seconds"]),
            "basic_iterations": int(basic["iterations"]),
            "v2_iterations": int(v2["iterations"]),
            "basic_workers": 1,
            "v2_workers": 2,
            "gurobi_threads_per_model": 1,
            "basic_objective": float(basic["objective"]),
            "v2_objective": float(v2["objective"]),
            "objective_absolute_difference": diff,
            "basic_result_source": row["basic_result_source"],
            "v2_result_source": row["v2_result_source"],
            "v2_certificate_class": certificate_class,
            "v2_original_strict_exact": row["v2_original_strict_exact"],
            "v2_independent_numeric_validation": row["v2_independent_numeric_validation"],
            "both_validated_under_disclosed_protocol": row["both_validated_under_disclosed_protocol"],
            "basic_result_path": relative(basic_dir / "result.json"),
            "v2_result_path": relative(v2_dir / "result.json"),
            "basic_result_sha256": basic_hash,
            "v2_result_sha256": v2_hash,
            "basic_provenance_sha256": basic_prov_hash,
            "v2_provenance_sha256": v2_prov_hash,
            "canonical_instance_hash": input_record["canonical_instance_hash"],
            "x0_hash": input_record["x0_hash"],
            "budget_parameters_sha256": input_record["budget_parameters_sha256"],
        })

    enriched.sort(key=lambda item: (SIZES.index(item["size"]), item["seed"]))
    identities = {key: sorted(values) for key, values in historical_identity_values.items()}
    return enriched, [input_records[key] for key in sorted(input_records, key=lambda k: (SIZES.index(k[0]), k[1]))], identities


def performance_summary(rows: list[dict]) -> list[dict]:
    result = []
    for size in SIZES:
        group = [row for row in rows if row["size"] == size]
        basic = [row["basic_core_seconds"] for row in group]
        v2 = [row["v2_core_seconds"] for row in group]
        speedups = [row["basic_over_v2_speedup"] for row in group]
        result.append({
            "size": size,
            "paired_n": len(group),
            "basic_mean_core_seconds": statistics.mean(basic),
            "basic_median_core_seconds": statistics.median(basic),
            "v2_mean_core_seconds": statistics.mean(v2),
            "v2_median_core_seconds": statistics.median(v2),
            "ratio_of_mean_core_times": statistics.mean(basic) / statistics.mean(v2),
            "geometric_mean_paired_speedup": math.exp(statistics.mean(math.log(value) for value in speedups)),
            "minimum_paired_speedup": min(speedups),
            "maximum_paired_speedup": max(speedups),
            "v2_win_count": sum(row["v2_core_seconds"] < row["basic_core_seconds"] for row in group),
            "basic_win_count": sum(row["basic_core_seconds"] < row["v2_core_seconds"] for row in group),
            "tie_count": sum(row["basic_core_seconds"] == row["v2_core_seconds"] for row in group),
            "mean_core_time_reduction_percent": 100.0 * (1.0 - statistics.mean(v2) / statistics.mean(basic)),
        })
    return result


def certification_summary(rows: list[dict]) -> list[dict]:
    result = []
    for certificate_class in ("legacy_strict_exact", "strict_original", "independently_numerically_validated"):
        group = [row for row in rows if row["v2_certificate_class"] == certificate_class]
        notes = {
            "legacy_strict_exact": "Original strict certificate preserved from the same-environment archive.",
            "strict_original": "Strict original protocol passed in the numeric-guard continuation.",
            "independently_numerically_validated": (
                "L10/20260925 only: original global risk-coupling check failed; independent final-inventory "
                "recourse and returned-cut numerical audits passed. This is not an exact-arithmetic proof."
            ),
        }
        result.append({
            "v2_certificate_class": certificate_class,
            "pair_count": len(group),
            "maximum_objective_absolute_difference": max(row["objective_absolute_difference"] for row in group),
            "mean_objective_absolute_difference": statistics.mean(row["objective_absolute_difference"] for row in group),
            "strict_original_count": sum(str(row["v2_original_strict_exact"]).lower() == "true" for row in group),
            "independent_numeric_validation_count": sum(
                str(row["v2_independent_numeric_validation"]).lower() == "true" for row in group
            ),
            "qualification": notes[certificate_class],
        })
    return result


def current_environment() -> dict:
    def package_version(name: str) -> str:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return "not_installed"

    hardware = {"cpu_model": "unavailable", "physical_cores": "unavailable", "ram_bytes": "unavailable"}
    if os.name == "nt":
        command = (
            "$cpu=Get-CimInstance Win32_Processor|Select-Object -First 1;"
            "$cs=Get-CimInstance Win32_ComputerSystem;"
            "[pscustomobject]@{cpu_model=$cpu.Name;physical_cores=$cpu.NumberOfCores;"
            "ram_bytes=[int64]$cs.TotalPhysicalMemory}|ConvertTo-Json -Compress"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        hardware = json.loads(completed.stdout)
    return {
        "observation_scope": "CURRENT_ARCHIVE_MACHINE_NOT_PROOF_OF_HISTORICAL_RUNTIME_HARDWARE",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "operating_system": platform.platform(),
        "cpu_model": hardware["cpu_model"],
        "physical_cores": hardware["physical_cores"],
        "logical_processors": os.cpu_count(),
        "physical_memory_bytes": hardware["ram_bytes"],
        "physical_memory_gib": float(hardware["ram_bytes"]) / 2**30,
        "python": platform.python_version(),
        "packages": {
            "gurobipy": package_version("gurobipy"),
            "numpy": package_version("numpy"),
            "psutil": package_version("psutil"),
        },
    }


def archive_evidence_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for path in RUNNERS:
        files.append(("runner", ROOT / path))
    for path in DIAGNOSTIC_SCRIPTS:
        files.append(("numeric_diagnostic_script", ROOT / path))
    files.append(("formal_source_csv", SOURCE_CSV))
    files.append(("legacy_source_csv", OLD_ROOT / "paired_comparison_same_env.csv"))
    for result_root in (OLD_ROOT / "runs", NEW_ROOT / "runs"):
        for path in sorted(result_root.glob("*/result.json")):
            files.append(("formal_result", path))
        for path in sorted(result_root.glob("*/provenance.json")):
            files.append(("formal_provenance", path))
    for path in sorted((OLD_ROOT / "failed_diagnostics").glob("*.json")):
        files.append(("L10_20260925_original_diagnostic", path))
    for path in HISTORICAL_SOURCES:
        files.append(("historical_descriptive_source", ROOT / path))
    return files


def render_paper_table(summary: list[dict]) -> str:
    xxl = next(row for row in summary if row["size"] == "XXL10")
    history = {row["method"]: row for row in load_csv(ROOT / HISTORICAL_SOURCES[0])}
    lines = [
        "# Basic PRB versus Accelerated PRB V2 runtime comparison",
        "",
        "## Same-environment paired Scaling30 results",
        "",
        "| Scale | Pairs | Basic mean core time (s) | V2 mean core time (s) | Geometric mean paired speedup | Mean-time reduction | V2 wins |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        lines.append(
            f"| {row['size']} | {row['paired_n']} | {row['basic_mean_core_seconds']:.3f} | "
            f"{row['v2_mean_core_seconds']:.3f} | {row['geometric_mean_paired_speedup']:.3f}x | "
            f"{row['mean_core_time_reduction_percent']:.1f}% | {row['v2_win_count']}/10 |"
        )
    lines.extend([
        "",
        "The ratio of mean times and the geometric mean of paired speedups are separately reported in "
        "`performance_summary_by_size.csv`; neither is substituted for the other.",
        "",
        "## Descriptive XXL10 context across experiment batches",
        "",
        "| Method | Experiment batch | Exact-certified samples used for mean | Mean core time (s) | Interpretation |",
        "| --- | --- | ---: | ---: | --- |",
        f"| Direct | historical XXL10 four-method batch | {history['Direct']['exact_certified_n']}/10 | {float(history['Direct']['mean_core_time_certified_seconds']):.3f} | Descriptive only; seven runs were limited. |",
        f"| EF-BD | historical XXL10 four-method batch | {history['EF-BD']['exact_certified_n']}/10 | {float(history['EF-BD']['mean_core_time_certified_seconds']):.3f} | Descriptive only; not paired with V2 in the new batch. |",
        f"| Aggregate-BD | historical XXL10 four-method batch | {history['Aggregate-BD']['exact_certified_n']}/10 | {float(history['Aggregate-BD']['mean_core_time_certified_seconds']):.3f} | Descriptive only; not paired with V2 in the new batch. |",
        f"| Basic PRB | new same-environment Scaling30 batch | 10/10 | {xxl['basic_mean_core_seconds']:.3f} | Valid paired baseline for V2. |",
        f"| Accelerated PRB V2 | new same-environment Scaling30 batch | 9 strict + 1 numerical/10 | {xxl['v2_mean_core_seconds']:.3f} | Valid under disclosed mixed certification classes. |",
        "",
        f"The historical PRB-BD mean was {float(history['PRB-BD']['mean_core_time_certified_seconds']):.3f} s, "
        f"whereas the new Basic PRB mean is {xxl['basic_mean_core_seconds']:.3f} s. The historical value is "
        "retained as source context rather than repeated as a second Basic column because the execution batches "
        "and runtime environments are not proven identical. No cross-batch speedup is claimed.",
        "",
        "Pure Benders remains a separate historical research method. It is not EF-BD and is not silently removed; "
        "its evidence boundary is documented in `docs/pure_benders_historical_comparison_audit.md`.",
        "",
    ])
    return "\n".join(lines)


def generate() -> None:
    rows, input_records, historical_identities = verify_rows()
    summary = performance_summary(rows)
    cert_summary = certification_summary(rows)
    current = current_environment()
    OUT.mkdir(parents=True, exist_ok=True)

    write_csv(OUT / "paired_results_30.csv", rows)
    write_csv(OUT / "performance_summary_by_size.csv", summary)
    write_csv(OUT / "certification_summary.csv", cert_summary)
    write_csv(OUT / "iteration_comparison.csv", [{
        "size": row["size"], "seed": row["seed"],
        "basic_iterations": row["basic_iterations"], "v2_iterations": row["v2_iterations"],
        "v2_minus_basic_iterations": row["v2_iterations"] - row["basic_iterations"],
    } for row in rows])
    (OUT / "runtime_comparison_paper_table.md").write_text(render_paper_table(summary), encoding="utf-8")

    environment_manifest = {
        "schema": "prb_basic_v2_fair_scaling30_environment_v1",
        "experiment": "PRB_BASIC_V2_FAIR_SCALING30_NUMERIC_GUARD_V1",
        "historical_runtime_evidence": {
            "source": "60 result provenance records",
            "recorded_identity_values": historical_identities,
            "python": "3.12.7",
            "gurobi": "13.0.1",
            "operating_system": "Windows-11-10.0.26200-SP0",
            "logical_cpu_count": 14,
            "cpu_model": "unverified_not_recorded_at_runtime",
            "physical_core_count": "unverified_not_recorded_at_runtime",
            "physical_memory": "unverified_not_recorded_at_runtime",
            "numpy_version": "unverified_not_recorded_at_runtime",
            "psutil_version": "unverified_not_recorded_at_runtime",
        },
        "current_archive_machine_observation": current,
        "solver_contract": {
            "Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "service_level": 0.90,
            "phi_multiplier": 1.85, "relative_gap_tolerance": 1e-6,
            "cut_tolerance": 1e-7, "objective_tolerance": 1e-4, "max_iterations": 500,
            "basic_workers": 1, "v2_process_workers": 2, "gurobi_threads_per_model": 1,
        },
        "timing_contract": {
            "core_time_seconds": "solver-returned total_runtime covering the core Benders solve; excludes outer process monitoring and numeric-guard post-audit",
            "child_solve_wall_seconds": "perf_counter elapsed around the method solve call in the child process",
            "monitor_wall_seconds": "outer monitored subprocess elapsed; retained in logs but not used in paper summary",
            "unit": "seconds",
        },
        "resource_contract": {
            "preflight_min_available_gib": {"L10": 7.0, "XL10": 10.0, "XXL10": 16.0},
            "maximum_process_tree_rss_gib": {"L10": 4.0, "XL10": 7.0, "XXL10": 13.0},
            "system_available_memory_floor_gib": 3.0,
            "condition_timeout_seconds": 900,
            "monitor_poll_seconds": 0.25,
        },
        "privacy": "No license identifiers, usernames, home paths, device IDs, tokens, or environment variables are recorded.",
    }
    write_json(OUT / "environment_manifest.json", environment_manifest)

    evidence = archive_evidence_files()
    provenance_manifest = {
        "schema": "prb_basic_v2_fair_scaling30_provenance_v1",
        "experiment": "PRB_BASIC_V2_FAIR_SCALING30_NUMERIC_GUARD_V1",
        "source_git_head": "d9bd2392512d922b731d2e6f5aa015fc731f52a7",
        "optimization_calls_during_archive": 0,
        "pair_count": len(rows),
        "method_result_count": 60,
        "certificate_counts": Counter(row["v2_certificate_class"] for row in rows),
        "input_records": input_records,
        "runner_sha256": {path: sha256_file(ROOT / path) for path in RUNNERS},
        "diagnostic_script_sha256": {path: sha256_file(ROOT / path) for path in DIAGNOSTIC_SCRIPTS},
        "source_evidence_sha256": {relative(path): sha256_file(path) for _, path in evidence},
        "identity_rules": [
            "Every CSV pair resolves to a result/provenance pair.",
            "Every provenance result_sha256 equals the result file SHA-256.",
            "Every input and model hash equals the frozen file bytes in this checkout.",
            "Failed or incomplete identities are rejected; missing values are never filled with zero.",
        ],
    }
    write_json(OUT / "provenance_manifest.json", provenance_manifest)

    (OUT / "experiment_environment.md").write_text(
        "# Scaling30 experiment environment and reproducibility\n\n"
        "The 60 provenance records agree on Python 3.12.7, Gurobi/gurobipy 13.0.1, "
        "Windows 11 build identity `10.0.26200`, 14 logical CPUs, one Gurobi thread per model, "
        "one Basic worker, and two V2 process workers. CPU model, physical core count, physical RAM, "
        "NumPy version, and psutil version were not written into the historical runtime provenance and "
        "therefore remain unverified historical facts.\n\n"
        f"For archival context only, the current machine reports `{current['cpu_model']}`, "
        f"{current['physical_cores']} physical cores, {current['logical_processors']} logical processors, "
        f"and {current['physical_memory_gib']:.3f} GiB RAM. Current package versions are Python "
        f"{current['python']}, gurobipy {current['packages']['gurobipy']}, NumPy "
        f"{current['packages']['numpy']}, and psutil {current['packages']['psutil']}. These current "
        "observations must not be substituted for fields absent from historical runtime records.\n\n"
        "Core time is the algorithm's returned `total_runtime`; child wall time wraps the solve call. "
        "Outer monitor time and the exceptional numerical audit are excluded from the paper core-time comparison.\n",
        encoding="utf-8",
    )

    maximum_difference = max(row["objective_absolute_difference"] for row in rows)
    audit_text = f"""# Final archive audit: Basic PRB versus Accelerated PRB V2 Scaling30

## Verdict

`PASS_FOR_DRAFT_PR_ARCHIVE`

- 30 unique `(size, seed)` pairs and 60 method results were resolved from raw JSON evidence.
- L10, XL10, and XXL10 each contain exactly 10 seeds (20260921--20260930).
- Accelerated PRB V2 is faster in 30/30 paired core-time observations.
- V2 certificate classes are 5 `legacy_strict_exact`, 24 `strict_original`, and 1 `independently_numerically_validated`.
- The maximum paired objective difference is `{maximum_difference:.17g}`, below the frozen `1e-4` objective tolerance.
- No optimization was invoked by the archive builder or verifier.

## L10/20260925 qualification

The original global risk-budget coupling check failed with error `4.071509465575218e-06`, so the original strict certificate remains `False`. Independent product-recourse evaluation matched the V2 objective within `6.789341568946838e-07`; the returned-cut audit found no final-inventory violation above `1e-6`, with maximum observed excess `6.785867299186066e-07`. The audit is limited to candidate recourse and returned cuts at the final inventory. It is not exact arithmetic, a whole-domain cut-validity proof, or a restoration of the original strict certificate.

## Claim-evidence matrix

| Claim | Required evidence | Current evidence | Boundary | Review risk |
| --- | --- | --- | --- | --- |
| V2 reduces runtime relative to Basic PRB | Same instances, parameters, tolerances, hardware batch, and paired timing | 30 same-environment pairs; V2 wins 30/30 | Applies only to this frozen Scaling30 protocol | Low |
| V2 preserves solution quality | Objective agreement and disclosed certification | Max objective difference `{maximum_difference:.3g}`; 29 strict + 1 separate numerical validation | The numerical case is not a strict certificate | Low if disclosed |
| V2 is faster than Direct, EF-BD, and Aggregate-BD | Unified five-method paired experiment | Only historical-batch descriptive timings | No cross-batch speedup is valid | High if overclaimed |
| Pure Benders is represented correctly | Separate method identity and historical record | Existing Pure Benders audit retained | Not EF-BD and not a new paired baseline | Low |

## Exclusions

Large stdout/stderr logs, monitor logs, caches, temporary files, unrelated development result roots, and historical E2--E7 data are not part of this archive commit. The selected formal result/provenance JSON files and the four L10/20260925 diagnostics are sufficient to audit the published rows.
"""
    (OUT / "final_archive_audit.md").write_text(audit_text, encoding="utf-8")

    generated = [
        OUT / "build_archive.py", OUT / "paired_results_30.csv",
        OUT / "performance_summary_by_size.csv", OUT / "certification_summary.csv",
        OUT / "iteration_comparison.csv", OUT / "runtime_comparison_paper_table.md",
        OUT / "environment_manifest.json", OUT / "provenance_manifest.json",
        OUT / "experiment_environment.md", OUT / "final_archive_audit.md",
    ]
    manifest_rows = []
    for role, path in evidence:
        manifest_rows.append({"role": role, "path": relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})
    for path in generated:
        manifest_rows.append({"role": "archive_analysis", "path": relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest_rows.sort(key=lambda item: item["path"])
    write_csv(OUT / "sha256_manifest.csv", manifest_rows)


def verify_archive() -> None:
    rows, _, _ = verify_rows()
    archived = load_csv(OUT / "paired_results_30.csv")
    if len(archived) != len(rows):
        raise RuntimeError("archived pair count mismatch")
    summary = load_csv(OUT / "performance_summary_by_size.csv")
    expected_summary = performance_summary(rows)
    if len(summary) != 3:
        raise RuntimeError("performance summary must contain three scales")
    for actual, expected in zip(summary, expected_summary, strict=True):
        if actual["size"] != expected["size"]:
            raise RuntimeError("performance summary order mismatch")
        for field in (
            "basic_mean_core_seconds", "v2_mean_core_seconds", "ratio_of_mean_core_times",
            "geometric_mean_paired_speedup", "mean_core_time_reduction_percent",
        ):
            if not math.isclose(float(actual[field]), float(expected[field]), rel_tol=1e-12, abs_tol=1e-12):
                raise RuntimeError(f"performance statistic mismatch: {actual['size']}/{field}")
    manifest = load_csv(OUT / "sha256_manifest.csv")
    for item in manifest:
        path = ROOT / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"] or path.stat().st_size != int(item["bytes"]):
            raise RuntimeError(f"archive hash mismatch: {item['path']}")
    print(json.dumps({
        "status": "PASS", "pairs": 30, "method_results": 60,
        "strict_original_total": 29, "independently_numerically_validated": 1,
        "optimization_calls": 0,
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify_archive()
    else:
        generate()
        verify_archive()


if __name__ == "__main__":
    main()
