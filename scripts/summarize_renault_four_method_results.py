from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
PURE_ROOT = ROOT / "experiments/results/e1b_pure_benders_v1"
STANDARD_ROOT = ROOT / "experiments/results/e1b_standard_vs_prb_v1"
PURE_AUTH = ROOT / "experiments/configs/formal/e1b_pure_benders_authorization.json"
STANDARD_AUTH = ROOT / "experiments/configs/formal/e1b_standard_vs_prb_authorization.json"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
EMPIRICAL_TABLE = ROOT / "table_e1_empirical_performance.csv"
E1C_AUDIT = ROOT / "artifacts/e1c_pure_benders_mechanism_audit.json"
OUTPUT_TABLE = ROOT / "artifacts/table_1_renault_four_method_comparison.csv"
OUTPUT_AUDIT = ROOT / "artifacts/renault_e1b_recovery_audit.json"
OUTPUT_MANIFEST = ROOT / "artifacts/renault_e1b_recovery_manifest.csv"
OUTPUT_REPORT = ROOT / "docs/renault_e1b_recovery_report.md"

METHODS = {
    "pure": {
        "root": PURE_ROOT,
        "run": "E1B-{case}-PURE",
        "files": (
            "result.json",
            "provenance.json",
            "solver.log",
            "iteration_log.json",
            "first_stage_solution.json",
        ),
        "authorization": PURE_AUTH,
        "certification": "CERTIFIED_PURE_BENDERS_EXACT",
    },
    "aggregate_structured": {
        "root": STANDARD_ROOT,
        "run": "E1B-{case}-STANDARD",
        "files": (
            "result.json",
            "provenance.json",
            "solver.log",
            "iteration_log.json",
            "first_stage_solution.json",
            "aggregate_cuts.json",
        ),
        "authorization": STANDARD_AUTH,
        "certification": "CERTIFIED_STANDARD_BENDERS_EXACT",
    },
}

SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]+"),
    "gurobi_wls_secret": re.compile(r"(?:WLSSECRET|GRB_WLSSECRET)\s*[=:]", re.IGNORECASE),
    "generic_secret": re.compile(r"(?:password|access[_-]?token|secret[_-]?key)\s*[=:]", re.IGNORECASE),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha256(commit: str, path: Path, root: Path = ROOT) -> str:
    relative = path.relative_to(root).as_posix()
    content = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=root)
    return hashlib.sha256(content).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def geometric_mean(values: list[float]) -> float:
    return math.exp(sum(math.log(value) for value in values) / len(values))


def _result_paths(method: str, case: str, root: Path = ROOT) -> tuple[Path, Path]:
    spec = METHODS[method]
    relative_root = spec["root"].relative_to(ROOT)
    run_root = root / relative_root / spec["run"].format(case=case)
    return run_root, run_root / "result.json"


def audit_recovered_results(root: Path = ROOT) -> dict:
    identity_hash = sha256(root / IDENTITY_TABLE.relative_to(ROOT))
    empirical = {row["case"]: row for row in read_csv(root / EMPIRICAL_TABLE.relative_to(ROOT))}
    e1c = load_json(root / E1C_AUDIT.relative_to(ROOT))
    standard_authorization = load_json(root / STANDARD_AUTH.relative_to(ROOT))
    e1c_cases = {row["case"]: row for row in e1c["empirical_objective_consistency"]["cases"]}
    runs: list[dict] = []
    sensitive_matches: list[dict] = []

    for method, spec in METHODS.items():
        for case in CASES:
            run_root, result_path = _result_paths(method, case, root)
            expected_files = set(spec["files"])
            actual_files = {path.name for path in run_root.iterdir() if path.is_file()}
            if actual_files != expected_files:
                raise RuntimeError(f"unexpected artifact set for {run_root}: {actual_files}")
            result = load_json(result_path)
            provenance = load_json(run_root / "provenance.json")
            historical_commit = result["git_commit"]
            authorization_path = root / spec["authorization"].relative_to(ROOT)
            checks = {
                "case": result.get("case") == case,
                "run_id": result.get("run_id") == spec["run"].format(case=case),
                "status": result.get("status") == "OPTIMAL",
                "certification": result.get("exact_certification_status") == spec["certification"],
                "cut_validity": result.get("cut_validity_pass") is True,
                "solver_result": result.get("solver_version") == "13.0.2",
                "solver_log": "Gurobi 13.0.2" in (run_root / "solver.log").read_text(encoding="utf-8"),
                "authorization": provenance.get("formal_run_authorized") is True,
                "authorization_hash": provenance.get("authorization_sha256") == git_blob_sha256(historical_commit, authorization_path, root),
                "identity_hash": provenance.get("identity_table_sha256") == identity_hash,
                "iteration_hash": provenance.get("iteration_log_sha256") == sha256(run_root / "iteration_log.json"),
                "first_stage_hash": provenance.get("first_stage_solution_sha256") == sha256(run_root / "first_stage_solution.json"),
                "instance_hash": result.get("instance_hash") == empirical[case]["instance_hash"],
                "x0_hash": result.get("x0_hash") == empirical[case]["x0_hash"],
            }
            if method == "pure":
                checks["e1c_objective"] = abs(float(result["objective"]) - float(e1c_cases[case]["pure"])) <= 1e-9
            else:
                checks["cuts_hash"] = provenance.get("aggregate_cuts_sha256") == sha256(run_root / "aggregate_cuts.json")
                prb_path = root / result["prb_e1a_result_path"]
                authorized_prb_hash = standard_authorization["prb_e1a_references"][case]["result_sha256"]
                checks["prb_reference_manifest_hash"] = provenance.get("prb_e1a_result_sha256") == authorized_prb_hash
                if prb_path.is_file():
                    checks["prb_reference_file_hash"] = provenance.get("prb_e1a_result_sha256") == sha256(prb_path)
                checks["objective_consistency"] = result.get("objective_consistency_pass") is True
            if not all(checks.values()):
                raise RuntimeError(f"recovered E1b identity failure {case}/{method}: {checks}")

            for path in run_root.iterdir():
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for label, pattern in SECRET_PATTERNS.items():
                    if pattern.search(text):
                        sensitive_matches.append({"path": str(path.relative_to(root)), "pattern": label})

            runs.append({
                "case": case,
                "method": method,
                "run_id": result["run_id"],
                "git_commit": result["git_commit"],
                "solver_version": result["solver_version"],
                "status": result["status"],
                "certification": result["exact_certification_status"],
                "objective": result["objective"],
                "core_runtime_seconds": result["core_runtime_seconds"],
                "absolute_gap": result["absolute_gap"],
                "instance_hash": result["instance_hash"],
                "x0_hash": result["x0_hash"],
                "checks": checks,
            })

    pure_mean = geometric_mean([float(row["core_runtime_seconds"]) for row in runs if row["method"] == "pure"])
    aggregate_mean = geometric_mean([float(row["core_runtime_seconds"]) for row in runs if row["method"] == "aggregate_structured"])
    timing_checks = {
        "pure_geometric_mean": abs(pure_mean - float(e1c["timing"]["empirical_geometric_mean_seconds"]["pure"])) <= 1e-12,
        "aggregate_geometric_mean": abs(aggregate_mean - float(e1c["timing"]["empirical_geometric_mean_seconds"]["aggregate"])) <= 1e-12,
    }
    if not all(timing_checks.values()):
        raise RuntimeError(f"recovered E1b timing differs from E1c audit: {timing_checks}")
    if sensitive_matches:
        raise RuntimeError(f"sensitive material found in recovered artifacts: {sensitive_matches}")

    return {
        "schema": "renault_e1b_recovery_audit_v1",
        "status": "PASS",
        "historical_recovery_not_rerun": True,
        "file_count": sum(len(spec["files"]) * len(CASES) for spec in METHODS.values()),
        "run_count": len(runs),
        "exact_certified_count": sum(row["certification"].startswith("CERTIFIED_") for row in runs),
        "solver_version": "13.0.2",
        "sensitive_match_count": 0,
        "timing_cross_check": timing_checks,
        "runs": runs,
    }


def build_table_rows(audit: dict) -> list[dict]:
    empirical = {row["case"]: row for row in read_csv(EMPIRICAL_TABLE)}
    recovered = {(row["case"], row["method"]): row for row in audit["runs"]}
    rows = []
    for case in CASES:
        base = empirical[case]
        pure = recovered[(case, "pure")]
        aggregate = recovered[(case, "aggregate_structured")]
        objectives = [
            float(base["direct_objective"]),
            float(pure["objective"]),
            float(aggregate["objective"]),
            float(base["prb_objective"]),
        ]
        spread = max(objectives) - min(objectives)
        rows.append({
            "Case": case,
            "Direct core time": base["direct_runtime_seconds"],
            "Pure Benders core time": pure["core_runtime_seconds"],
            "Aggregate+Structured core time": aggregate["core_runtime_seconds"],
            "PRB core time": base["prb_runtime_seconds"],
            "Direct objective": base["direct_objective"],
            "Pure objective": pure["objective"],
            "Aggregate+Structured objective": aggregate["objective"],
            "PRB objective": base["prb_objective"],
            "Objective max abs difference": spread,
            "Objective consistency": "PASS_ALL_FOUR" if spread <= 1e-4 else "FAIL",
            "Direct certification": base["direct_optimality_status"],
            "Pure certification": pure["certification"],
            "Aggregate+Structured certification": aggregate["certification"],
            "PRB certification": base["prb_certification_status"],
        })
    return rows


def verify_historical_zip(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        matches = []
        for name in names:
            destination = STANDARD_ROOT / Path(name)
            matches.append(destination.is_file() and hashlib.sha256(archive.read(name)).hexdigest() == sha256(destination))
    return {
        "path": str(zip_path),
        "sha256": sha256(zip_path),
        "file_count": len(names),
        "matching_files": sum(matches),
        "status": "PASS" if len(names) == 48 and all(matches) else "FAIL",
    }


def build_recovery_manifest(source_root: Path, staging_root: Path, recovery_date: str) -> list[dict]:
    rows = []
    for method, spec in METHODS.items():
        source_method = source_root / spec["root"].relative_to(ROOT)
        staging_method = staging_root / spec["root"].name
        for case in CASES:
            destination_run, result_path = _result_paths(method, case)
            source_run = source_method / spec["run"].format(case=case)
            staging_run = staging_method / spec["run"].format(case=case)
            commit = load_json(result_path)["git_commit"]
            if method == "aggregate_structured":
                source_result = load_json(source_run / "result.json")
                source_provenance = load_json(source_run / "provenance.json")
                source_prb = source_root / source_result["prb_e1a_result_path"]
                if source_provenance["prb_e1a_result_sha256"] != sha256(source_prb):
                    raise RuntimeError(f"source PRB reference hash mismatch: {source_prb}")
            for name in spec["files"]:
                source = source_run / name
                staging = staging_run / name
                destination = destination_run / name
                source_hash = sha256(source)
                staging_hash = sha256(staging)
                destination_hash = sha256(destination)
                sizes = {source.stat().st_size, staging.stat().st_size, destination.stat().st_size}
                if len({source_hash, staging_hash, destination_hash}) != 1 or len(sizes) != 1:
                    raise RuntimeError(f"three-way copy mismatch: {source} -> {staging} -> {destination}")
                rows.append({
                    "method": method,
                    "case": case,
                    "source_path": str(source),
                    "staging_path": str(staging),
                    "target_path": str(destination.relative_to(ROOT)),
                    "source_sha256": source_hash,
                    "staging_sha256": staging_hash,
                    "target_sha256": destination_hash,
                    "size_bytes": source.stat().st_size,
                    "source_mtime_utc": datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
                    "historical_run_commit": commit,
                    "recovery_date": recovery_date,
                    "recovery_classification": "HISTORICAL_EXPERIMENT_FILE_ARCHIVE_NOT_A_RERUN",
                })
    return rows


def write_report(audit: dict, zip_audit: dict) -> None:
    OUTPUT_REPORT.write_text(
        "\n".join([
            "# Renault E1b formal evidence recovery",
            "",
            "## Decision",
            "",
            "`RECOVERY_AUDIT_PASS`",
            "",
            "The 88 files are byte-identical copies of the historical formal-run artifacts. No optimization was run and no result, timing, status, or provenance field was changed.",
            "",
            "- Pure Benders: 8 runs, 40 files, 8 exact-certified.",
            "- Aggregate Benders + Structured Oracle: 8 runs, 48 files, 8 exact-certified.",
            f"- Historical Aggregate ZIP SHA-256: `{zip_audit['sha256']}`.",
            f"- Historical Aggregate ZIP comparison: {zip_audit['matching_files']}/{zip_audit['file_count']} byte-identical (`{zip_audit['status']}`).",
            "- Result/provenance/reference-hash checks: 16/16 PASS.",
            "- Sensitive-key/token scan: 0 matches. Solver logs retain only ordinary Gurobi username/license-identification banner data, not license keys.",
            "- Recovered Renault solver version: Gurobi 13.0.2, independently present in result files and solver logs.",
            "",
            "The Pure recovery is committed as its original 40 files. No historical Pure ZIP was found, so no ZIP is represented as an original-run archive.",
            "",
            f"Recovery manifest: `{OUTPUT_MANIFEST.relative_to(ROOT).as_posix()}`.",
        ]) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit recovered Renault E1b evidence and rebuild the four-method table without optimization.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--aggregate-zip", type=Path)
    parser.add_argument("--recovery-date", default=date.today().isoformat())
    args = parser.parse_args()

    audit = audit_recovered_results()
    rows = build_table_rows(audit)
    zip_audit = verify_historical_zip(args.aggregate_zip) if args.aggregate_zip else None
    if zip_audit and zip_audit["status"] != "PASS":
        raise RuntimeError(f"historical Aggregate ZIP mismatch: {zip_audit}")
    if args.write:
        if args.source_root is None or args.staging_root is None or args.aggregate_zip is None:
            parser.error("--write requires --source-root, --staging-root, and --aggregate-zip")
        manifest = build_recovery_manifest(args.source_root, args.staging_root, args.recovery_date)
        write_csv(OUTPUT_MANIFEST, manifest, list(manifest[0]))
        audit["historical_aggregate_zip"] = zip_audit
        audit["source_prb_reference_files_verified"] = 8
        audit["recovery_manifest_sha256"] = sha256(OUTPUT_MANIFEST)
        OUTPUT_AUDIT.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        write_csv(OUTPUT_TABLE, rows, list(rows[0]))
        write_report(audit, zip_audit)
    print(json.dumps({
        "status": audit["status"],
        "files": audit["file_count"],
        "runs": audit["run_count"],
        "exact_certified": audit["exact_certified_count"],
        "table_rows": len(rows),
        "zip": zip_audit,
        "optimization_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
