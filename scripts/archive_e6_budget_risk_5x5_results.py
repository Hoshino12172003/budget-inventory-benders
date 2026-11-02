from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
BETA_TOKENS = ("B080", "B090", "B100", "B110", "B120")
GAMMA_TOKENS = ("G0", "G1", "G2", "G3", "G4")
REQUIRED_FILES = ("result.json", "provenance.json", "first_stage_solution.json")
ARTIFACT_TYPE = {
    "result.json": "RESULT",
    "provenance.json": "PROVENANCE",
    "first_stage_solution.json": "FIRST_STAGE_SOLUTION",
}
SUPPORT_FILES = (
    "artifacts/e6_budget_risk_5x5_reuse_map.csv",
    "artifacts/e6_budget_risk_5x5_missing_cells.json",
    "artifacts/e6_budget_risk_5x5_historical_source_audit.csv",
    "artifacts/e6_budget_risk_5x5_historical_source_audit.json",
    "artifacts/e4_per_file_hashes_for_e6_reuse_audit.csv",
    "artifacts/e6_budget_risk_5x5_frozen_execution_identity.json",
    "artifacts/e6_budget_risk_5x5_regression_classification.csv",
    "artifacts/e6_budget_risk_5x5_delivery_sha256.csv",
    "docs/e6_budget_risk_5x5_extension_audit.md",
    "docs/e6_budget_risk_5x5_frozen_execution_audit.md",
    "scripts/summarize_e6_budget_risk_5x5_results.py",
    "artifacts/e6_budget_risk_5x5_mean_ri_percent.csv",
    "artifacts/e6_budget_risk_5x5_mean_normalized_objective.csv",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_type(result: dict) -> str:
    if result.get("reused") is not True:
        return "NEW_E6_5X5_SOLVE"
    experiment = result.get("reuse_source_experiment")
    if experiment in {"E3", "E4", "E6"}:
        return f"REUSED_{experiment}"
    raise RuntimeError(f"unknown reuse source for {result.get('run_id')}: {experiment!r}")


def expected_run_ids() -> list[str]:
    return [
        f"E6-5X5-{case}-{beta}-{gamma}"
        for case in CASES
        for beta in BETA_TOKENS
        for gamma in GAMMA_TOKENS
    ]


def audit_source(source_repo: Path) -> tuple[list[dict], dict]:
    result_root = source_repo / "experiments/results/e6_budget_risk_5x5_v1"
    if not result_root.is_dir():
        raise FileNotFoundError(result_root)

    expected = set(expected_run_ids())
    directories = sorted(path for path in result_root.iterdir() if path.is_dir())
    actual = {path.name for path in directories}
    if actual != expected:
        raise RuntimeError(
            f"source cell identity mismatch: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )

    rows: list[dict] = []
    cell_types: Counter[str] = Counter()
    for directory in directories:
        names = sorted(path.name for path in directory.iterdir() if path.is_file())
        if names != sorted(REQUIRED_FILES):
            raise RuntimeError(f"unexpected file set for {directory.name}: {names}")

        result_path = directory / "result.json"
        provenance_path = directory / "provenance.json"
        solution_path = directory / "first_stage_solution.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if result.get("run_id") != directory.name:
            raise RuntimeError(f"run identity mismatch: {directory.name}")
        if result.get("status") != "OPTIMAL":
            raise RuntimeError(f"non-optimal result: {directory.name}")
        if result.get("certification_status") != "CERTIFIED_PRB_EXACT":
            raise RuntimeError(f"uncertified result: {directory.name}")
        if result.get("exact_certification_pass") is not True:
            raise RuntimeError(f"failed exact certification: {directory.name}")
        if provenance.get("result_sha256") != sha256(result_path):
            raise RuntimeError(f"result provenance mismatch: {directory.name}")
        if provenance.get("first_stage_solution_sha256") != sha256(solution_path):
            raise RuntimeError(f"solution provenance mismatch: {directory.name}")

        kind = source_type(result)
        cell_types[kind] += 1
        for filename in REQUIRED_FILES:
            path = directory / filename
            rows.append(
                {
                    "relative_path": path.relative_to(result_root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                    "artifact_type": ARTIFACT_TYPE[filename],
                    "case_id": str(result["case"]),
                    "beta": format(float(result["beta"]), ".2f"),
                    "Gamma": int(result["Gamma"]),
                    "source_type": kind,
                }
            )

    if cell_types != Counter(
        {"REUSED_E3": 16, "REUSED_E4": 16, "REUSED_E6": 72, "NEW_E6_5X5_SOLVE": 96}
    ):
        raise RuntimeError(f"unexpected source-type counts: {dict(cell_types)}")

    aggregate = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item["relative_path"]):
        aggregate.update(
            (
                f"{row['relative_path']}\0{row['size_bytes']}\0{row['sha256']}\0"
                f"{row['artifact_type']}\0{row['case_id']}\0{row['beta']}\0"
                f"{row['Gamma']}\0{row['source_type']}\n"
            ).encode("utf-8")
        )

    identity = {
        "schema": "e6_budget_risk_5x5_final_source_identity_v1",
        "completion_status": "COMPLETE",
        "source_path": source_repo.as_posix(),
        "source_result_root": result_root.as_posix(),
        "source_git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source_repo, text=True
        ).strip(),
        "historical_base_commit": "cc87b68363fa9cc444046f7823a6807412bb7ca8",
        "authorization_commit": "2fb30d2dd63c7a9d6e0135c422af09c498573169",
        "expected_cells": 200,
        "materialized_cells": 200,
        "reused_cells": 104,
        "new_solved_cells": 96,
        "missing_cells": 0,
        "failed_cells": 0,
        "interpolation_cells": 0,
        "result_json_count": 200,
        "provenance_json_count": 200,
        "first_stage_solution_json_count": 200,
        "total_file_count": len(rows),
        "source_type_counts": dict(sorted(cell_types.items())),
        "aggregate_hash_algorithm": "SHA256 over sorted UTF-8 records: relative_path\\0size_bytes\\0sha256\\0artifact_type\\0case_id\\0beta\\0Gamma\\0source_type\\n",
        "deterministic_result_tree_sha256": aggregate.hexdigest(),
        "optimization_calls": 0,
    }
    return sorted(rows, key=lambda item: item["relative_path"]), identity


def write_source_manifests(rows: list[dict], identity: dict) -> None:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    csv_path = artifacts / "e6_budget_risk_5x5_final_source_hashes.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (artifacts / "e6_budget_risk_5x5_final_source_identity.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def copy_result_tree(source_repo: Path) -> str:
    source = source_repo / "experiments/results/e6_budget_risk_5x5_v1"
    destination = ROOT / "experiments/results/e6_budget_risk_5x5_v1"
    if destination.exists():
        source_files = {path.relative_to(source).as_posix(): path for path in source.rglob("*") if path.is_file()}
        destination_files = {
            path.relative_to(destination).as_posix(): path
            for path in destination.rglob("*")
            if path.is_file()
        }
        if source_files.keys() != destination_files.keys() or any(
            sha256(path) != sha256(destination_files[name]) for name, path in source_files.items()
        ):
            raise RuntimeError("destination result tree exists and is not byte-identical")
        return "ALREADY_IDENTICAL"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    return "COPIED_BYTE_IDENTICAL"


def copy_support_files(source_repo: Path) -> None:
    for relative in SUPPORT_FILES:
        source = source_repo / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def write_copy_audit(source_repo: Path, copy_status: str) -> dict:
    source_root = source_repo / "experiments/results/e6_budget_risk_5x5_v1"
    destination_root = ROOT / "experiments/results/e6_budget_risk_5x5_v1"
    source_files = {path.relative_to(source_root).as_posix(): path for path in source_root.rglob("*") if path.is_file()}
    destination_files = {
        path.relative_to(destination_root).as_posix(): path
        for path in destination_root.rglob("*")
        if path.is_file()
    }
    names = sorted(source_files.keys() | destination_files.keys())
    rows = []
    for name in names:
        source = source_files.get(name)
        destination = destination_files.get(name)
        source_hash = sha256(source) if source else ""
        destination_hash = sha256(destination) if destination else ""
        source_size = source.stat().st_size if source else ""
        destination_size = destination.stat().st_size if destination else ""
        if source is None:
            status = "EXTRA_DESTINATION"
        elif destination is None:
            status = "MISSING_DESTINATION"
        elif source_size != destination_size or source_hash != destination_hash:
            status = "HASH_MISMATCH"
        else:
            status = "IDENTICAL"
        rows.append(
            {
                "relative_path": name,
                "source_size_bytes": source_size,
                "destination_size_bytes": destination_size,
                "source_sha256": source_hash,
                "destination_sha256": destination_hash,
                "status": status,
            }
        )

    counts = Counter(row["status"] for row in rows)
    summary = {
        "schema": "e6_budget_risk_5x5_archival_copy_audit_v1",
        "status": "PASS"
        if counts["HASH_MISMATCH"] == counts["MISSING_DESTINATION"] == counts["EXTRA_DESTINATION"] == 0
        else "FAIL",
        "copy_action": copy_status,
        "source_path": source_root.as_posix(),
        "destination_path": destination_root.as_posix(),
        "source_files": len(source_files),
        "destination_files": len(destination_files),
        "hash_mismatch": counts["HASH_MISMATCH"],
        "missing_destination": counts["MISSING_DESTINATION"],
        "extra_destination": counts["EXTRA_DESTINATION"],
        "identical_files": counts["IDENTICAL"],
        "optimization_calls": 0,
    }
    artifacts = ROOT / "artifacts"
    with (artifacts / "e6_budget_risk_5x5_archival_copy_audit.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (artifacts / "e6_budget_risk_5x5_archival_copy_audit.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    if summary["status"] != "PASS":
        raise RuntimeError(f"archival byte audit failed: {summary}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive completed E6-5X5 results without optimization")
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source_repo = args.source.resolve()
    rows, identity = audit_source(source_repo)
    write_source_manifests(rows, identity)
    copy_status = copy_result_tree(source_repo)
    copy_support_files(source_repo)
    summary = write_copy_audit(source_repo, copy_status)
    print(json.dumps({"source_identity": identity, "copy_audit": summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
