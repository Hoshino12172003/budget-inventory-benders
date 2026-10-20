from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean


ROOT = Path(__file__).resolve().parents[1]
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
METHODS = ("PRB-BD", "PRB-SG", "A-PRB", "A-PRB-SG")
OUTPUT = ROOT / "artifacts/renault_prb_ablation_continuation_v1"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_prb(case: str) -> tuple[dict, Path]:
    if case == "210202":
        path = ROOT / "experiments/results/renault_vanilla_bd_pilot_210202_development_v1/prb_outcome.json"
    else:
        path = ROOT / f"experiments/results/renault_vanilla_bd_remaining7_development_v1/{case}/prb_outcome.json"
    raw = read_json(path)
    coupling = ""
    if case == "210330":
        audit = read_json(ROOT / "artifacts/e1_210330_global_coupling_audit.json")
        coupling = audit["persisted_primary_state"]["original_residual_reconstructed_from_persisted_lb_minus_ub"]
    row = {
        "case": case,
        "method": "PRB-BD",
        "status": "PASS" if raw["exact_certification_pass"] else "NUMERICAL_CERTIFICATION_FAIL",
        "exact_certification": raw["exact_certification_pass"],
        "cut_validity": raw.get("cut_validity_pass", raw["exact_certification_pass"]),
        "objective": raw["objective"],
        "lower_bound": "",
        "upper_bound": "",
        "gap": "",
        "coupling_residual": coupling,
        "core_time_seconds": raw["algorithm_seconds"],
        "oracle_time_seconds": raw["oracle_seconds"],
        "master_time_seconds": "",
        "iterations": raw["iterations"],
        "candidate_cuts": "",
        "cuts_added": raw["cut_count"],
        "scenario_lp_solves": "",
        "pruning_fraction": "",
        "peak_process_tree_rss_gib": raw["peak_process_tree_rss_gib"],
        "source": path.relative_to(ROOT).as_posix(),
        "result_sha256": sha256(path),
    }
    return row, path


def new_result(method: str, case: str) -> tuple[dict, Path]:
    spec = {
        "PRB-SG": ("renault_prb_sg_development_v1", "PRB_SG_RENAULT_"),
        "A-PRB": ("renault_a_prb_development_v1", "A_PRB_RENAULT_"),
        "A-PRB-SG": ("renault_a_prb_sg_development_v1", "A_PRB_SG_RENAULT_"),
    }[method]
    base = ROOT / "experiments/results" / spec[0]
    cid = spec[1] + case
    canonical = base / "runs" / cid / "result.json"
    path = canonical if canonical.is_file() else base / "worker_logs" / cid / "attempt-001/result.json"
    raw = read_json(path)
    exact = bool(raw["exact_certification"])
    coupling_only = (
        not exact
        and raw.get("internal_exact_certification") is True
        and raw.get("independent_certification", {}).get("pass") is True
        and raw.get("cut_validity") is True
        and raw.get("global_risk_budget_coupling_pass") is False
        and raw.get("direct_objective_residual", math.inf) <= 1e-4
    )
    monitor = read_json(path.with_name("resource_monitor.json"))
    row = {
        "case": case,
        "method": method,
        "status": "PASS" if exact else ("NUMERICAL_CERTIFICATION_FAIL" if coupling_only else "FAIL"),
        "exact_certification": exact,
        "cut_validity": raw["cut_validity"],
        "objective": raw["objective"],
        "lower_bound": raw["final_lower_bound"],
        "upper_bound": raw["final_upper_bound"],
        "gap": raw["final_gap"],
        "coupling_residual": raw["global_risk_budget_coupling_error"],
        "core_time_seconds": raw["algorithm_core_time_seconds"],
        "oracle_time_seconds": raw["oracle_time_seconds"],
        "master_time_seconds": raw["master_time_seconds"],
        "iterations": raw["iterations"],
        "candidate_cuts": raw["candidate_cuts"],
        "cuts_added": raw["cuts_added"],
        "scenario_lp_solves": raw["scenario_lp_solves"],
        "pruning_fraction": raw["pruning_fraction"],
        "peak_process_tree_rss_gib": monitor["peak_process_tree_rss_gib"],
        "source": path.relative_to(ROOT).as_posix(),
        "result_sha256": sha256(path),
    }
    return row, path


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def gmean(values: list[float]) -> float:
    return math.exp(fmean(math.log(value) for value in values))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    source_paths: set[Path] = set()
    for case in CASES:
        row, path = historical_prb(case)
        rows.append(row)
        source_paths.add(path)
        for method in METHODS[1:]:
            row, path = new_result(method, case)
            rows.append(row)
            source_paths.add(path)
            source_paths.update(path.parent.glob("*"))
    write_csv(OUTPUT / "prb_ablation_by_case.csv", rows)

    summary = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        passed = [row for row in selected if row["status"] == "PASS"]
        summary.append({
            "method": method,
            "fixed_denominator": 8,
            "certified": len(passed),
            "failed": 8 - len(passed),
            "certification_rate": len(passed) / 8,
            "mean_core_time_certified_seconds": fmean(float(row["core_time_seconds"]) for row in passed),
            "mean_oracle_time_certified_seconds": fmean(float(row["oracle_time_seconds"]) for row in passed),
            "mean_iterations_certified": fmean(float(row["iterations"]) for row in passed),
            "mean_cuts_added_certified": fmean(float(row["cuts_added"]) for row in passed),
            "mean_pruning_fraction_certified": (
                fmean(float(row["pruning_fraction"]) for row in passed)
                if method in {"PRB-SG", "A-PRB-SG"} else 0.0
            ),
        })
    write_csv(OUTPUT / "prb_ablation_summary.csv", summary)

    by_key = {(row["method"], row["case"]): row for row in rows}
    comparisons = (("PRB-BD", "PRB-SG"), ("PRB-BD", "A-PRB"), ("PRB-SG", "A-PRB-SG"), ("A-PRB", "A-PRB-SG"))
    pairs = []
    for baseline, enhanced in comparisons:
        cases = [case for case in CASES if by_key[(baseline, case)]["status"] == by_key[(enhanced, case)]["status"] == "PASS"]
        ratios = [float(by_key[(baseline, case)]["core_time_seconds"]) / float(by_key[(enhanced, case)]["core_time_seconds"]) for case in cases]
        pairs.append({
            "baseline": baseline,
            "enhanced": enhanced,
            "paired_n": len(cases),
            "paired_cases": ";".join(cases),
            "geometric_mean_speedup": gmean(ratios),
            "enhanced_wins": sum(value > 1 for value in ratios),
            "baseline_wins": sum(value < 1 for value in ratios),
            "ties": sum(value == 1 for value in ratios),
        })
    write_csv(OUTPUT / "prb_ablation_pairwise.csv", pairs)

    failures = [row for row in rows if row["status"] != "PASS"]
    write_csv(OUTPUT / "prb_ablation_failures.csv", failures)

    audit = {
        "schema": "renault_prb_ablation_certification_audit_v1",
        "fixed_denominator": 8,
        "methods": {
            method: {
                "pass": sum(row["status"] == "PASS" for row in rows if row["method"] == method),
                "fail": sum(row["status"] != "PASS" for row in rows if row["method"] == method),
                "cases": {
                    row["case"]: {
                        "status": row["status"],
                        "exact_certification": row["exact_certification"],
                        "cut_validity": row["cut_validity"],
                        "coupling_residual": row["coupling_residual"],
                        "source": row["source"],
                        "result_sha256": row["result_sha256"],
                    }
                    for row in rows if row["method"] == method
                },
            }
            for method in METHODS
        },
    }
    (OUTPUT / "prb_ablation_certification_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = []
    for path in sorted(p for p in source_paths if p.is_file()):
        manifest.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size})
    write_csv(OUTPUT / "prb_ablation_sha256_manifest.csv", manifest)

    summaries = {row["method"]: row for row in summary}
    pair_map = {(row["baseline"], row["enhanced"]): row for row in pairs}
    synergy_cases = [case for case in CASES if all(by_key[(method, case)]["status"] == "PASS" for method in METHODS)]
    synergy = gmean([
        float(by_key[("PRB-SG", case)]["core_time_seconds"]) * float(by_key[("A-PRB", case)]["core_time_seconds"])
        / (float(by_key[("PRB-BD", case)]["core_time_seconds"]) * float(by_key[("A-PRB-SG", case)]["core_time_seconds"]))
        for case in synergy_cases
    ])
    report = [
        "# Renault PRB 2x2 ablation continuation",
        "",
        "All rates use the fixed denominator of eight. Timing comparisons use only pairs certified by both methods. The frozen PRB-BD and PRB-SG 210330 failures remain failures.",
        "",
        "| Method | Certified | Failed | Mean core time (certified, s) | Mean oracle time (s) | Mean iterations | Mean added cuts | Mean pruning |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        item = summaries[method]
        report.append(f"| {method} | {item['certified']}/8 | {item['failed']} | {item['mean_core_time_certified_seconds']:.6f} | {item['mean_oracle_time_certified_seconds']:.6f} | {item['mean_iterations_certified']:.3f} | {item['mean_cuts_added_certified']:.3f} | {item['mean_pruning_fraction_certified']:.3%} |")
    report.extend(["", "## Strict paired effects", ""])
    for key, item in pair_map.items():
        report.append(f"- {key[1]} versus {key[0]}: N={item['paired_n']}, geometric mean speedup={item['geometric_mean_speedup']:.3f}x, wins={item['enhanced_wins']}, losses={item['baseline_wins']}, ties={item['ties']}.")
    report.extend([
        "",
        f"The multiplicative interaction factor on the {len(synergy_cases)} fully certified common cases is {synergy:.3f}; values above 1 indicate positive runtime synergy beyond independent multiplicative effects.",
        "",
        "## Interpretation",
        "",
        "- Safe screening cut mean Oracle time sharply, but PRB-SG was slightly slower overall than frozen PRB-BD on the seven strict pairs (0.956x speedup).",
        "- Adaptive selection alone was slower on every strict pair and increased the mean iteration count; it did not add a practical benefit in this Renault study.",
        "- Screening strongly recovered the adaptive variant (A-PRB-SG was 2.519x faster than A-PRB), but A-PRB-SG still lost all seven strict pairs against PRB-SG.",
        "- Therefore A-PRB-SG is not recommended as the paper's main algorithm and is not recommended for L10 expansion without redesigning the adaptive rule.",
        "",
        "The runs were produced in separate frozen batches. Cross-batch timing is descriptive, not a claim of simultaneous benchmarking.",
    ])
    (OUTPUT / "prb_ablation_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
