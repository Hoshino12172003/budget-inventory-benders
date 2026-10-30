from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
EXPERIMENTS = {
    "E3": {
        "root": "experiments/results/e3_budget_sensitivity_v1",
        "runner": "experiments/run_e3_budget_local.py",
        "manifest": "experiments/configs/formal/e3_budget_sensitivity_authorization.json",
        "ids": [f"E3-{case}-B{int(beta * 100):03d}" for case in CASES for beta in (0.8, 0.9, 1.0, 1.1, 1.2)],
    },
    "E4": {
        "root": "experiments/results/e4_gamma_sensitivity_v1",
        "runner": "experiments/run_e4_gamma_local.py",
        "manifest": "experiments/configs/formal/e4_gamma_sensitivity_authorization.json",
        "ids": [f"E4-{case}-G{gamma}" for case in CASES for gamma in range(5)],
    },
    "E6": {
        "root": "experiments/results/e6_budget_risk_interaction_v1",
        "runner": "experiments/run_e6_budget_risk_local.py",
        "manifest": "experiments/configs/formal/e6_budget_risk_interaction_authorization.json",
        "ids": [
            f"E6-{case}-B{int(beta * 100):03d}-G{gamma}"
            for case in CASES
            for beta in (0.8, 1.0, 1.2)
            for gamma in (0, 2, 4)
        ],
    },
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_hash(value: object) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def git_file(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def git_file_hash(commit: str, path: str) -> str:
    return sha256_bytes(git_file(commit, path))


def git_model_identity(commit: str, model_files: list[str]) -> str:
    hashes = {
        path: sha256_bytes(git_file(commit, path).replace(b"\r\n", b"\n"))
        for path in model_files
    }
    return canonical_hash(hashes)


def parse_condition(experiment: str, run_id: str) -> tuple[str, float, int]:
    parts = run_id.split("-")
    case = parts[1]
    if experiment == "E3":
        return case, int(parts[2][1:]) / 100.0, 2
    if experiment == "E4":
        return case, 1.0, int(parts[2][1:])
    return case, int(parts[2][1:]) / 100.0, int(parts[3][1:])


def expected_hashes() -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    with (ARTIFACTS / "e3_primary_result_hashes.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            output[row["run_id"]] = {
                "result.json": row["result_sha256"],
                "first_stage_solution.json": row["first_stage_solution_sha256"],
                "provenance.json": row["provenance_sha256"],
            }
    e6 = json.loads((ARTIFACTS / "e6_final_result_audit.json").read_text(encoding="utf-8"))
    output.update(e6["primary_artifact_hashes"])
    return output


def e4_archive_hashes(source_repo: Path) -> tuple[str, dict[str, str]]:
    archive = source_repo / "e4_gamma_sensitivity_v1.zip"
    hashes = {}
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.is_dir():
                hashes[info.filename.replace("\\", "/")] = sha256_bytes(bundle.read(info))
    return sha256(archive), hashes


def audit(source_repo: Path) -> tuple[list[dict], list[dict], dict]:
    contract = json.loads(
        (ROOT / "experiments/configs/formal/e6_budget_risk_interaction_authorization.json").read_text(
            encoding="utf-8"
        )
    )
    known = expected_hashes()
    e4_zip_hash, e4_hashes = e4_archive_hashes(source_repo)
    rows = []
    model_cache: dict[str, str] = {}
    for experiment, spec in EXPERIMENTS.items():
        result_root = source_repo / spec["root"]
        observed_ids = {path.name for path in result_root.iterdir() if path.is_dir()}
        expected_ids = set(spec["ids"])
        if observed_ids != expected_ids:
            raise RuntimeError(
                f"{experiment} run set mismatch: missing={sorted(expected_ids-observed_ids)}, "
                f"extra={sorted(observed_ids-expected_ids)}"
            )
        for run_id in spec["ids"]:
            directory = result_root / run_id
            paths = {name: directory / name for name in ("result.json", "first_stage_solution.json", "provenance.json")}
            if not all(path.is_file() for path in paths.values()):
                raise RuntimeError(f"incomplete source triple: {directory}")
            result = json.loads(paths["result.json"].read_text(encoding="utf-8"))
            provenance = json.loads(paths["provenance.json"].read_text(encoding="utf-8"))
            case, beta, gamma = parse_condition(experiment, run_id)
            expected = known.get(run_id, {})
            if experiment == "E4":
                expected = {
                    name: e4_hashes[f"{run_id}/{name}"]
                    for name in ("result.json", "first_stage_solution.json", "provenance.json")
                }
            commit = provenance["git_commit"]
            if commit not in model_cache:
                model_cache[commit] = git_model_identity(commit, contract["model_files"])
            parameter_identity = (
                result.get("run_id") == run_id
                and result.get("case") == case
                and float(result.get("beta")) == beta
                and result.get("Gamma") == gamma
                and result.get("lambda_R") == contract["lambda_R"]
            )
            instance_identity = (
                result.get("dataset_id") == contract["dataset_id"]
                and result.get("instance_hash") == contract["instance_hashes"][case]
                and result.get("x0_hash") == contract["x0_hashes"][case]
                and result.get("calibration_hash") == contract["calibration_hashes"][case]
                and result.get("mapping_hash") == contract["mapping_sha256"]
            )
            model_identity = (
                result.get("model_identity_sha256") == contract["model_identity_sha256"]
                == model_cache[commit]
            )
            runner_identity = (
                provenance.get("runner_sha256") == git_file_hash(commit, spec["runner"])
                and provenance.get("manifest_sha256") == git_file_hash(commit, spec["manifest"])
            )
            artifact_identity = (
                sha256(paths["result.json"]) == expected.get("result.json")
                and sha256(paths["first_stage_solution.json"])
                == expected.get("first_stage_solution.json")
                and sha256(paths["provenance.json"]) == expected.get("provenance.json")
                and provenance.get("result_sha256") == sha256(paths["result.json"])
                and provenance.get("first_stage_solution_sha256")
                == sha256(paths["first_stage_solution.json"])
            )
            certification_identity = (
                result.get("status") == "OPTIMAL"
                and result.get("certification_status") == "CERTIFIED_PRB_EXACT"
                and result.get("solver_profile") == contract["solver_profile"]
            )
            eligible = all(
                (
                    parameter_identity,
                    instance_identity,
                    model_identity,
                    runner_identity,
                    artifact_identity,
                    certification_identity,
                )
            )
            rows.append(
                {
                    "candidate_path": directory.as_posix(),
                    "experiment": experiment,
                    "run_id": run_id,
                    "candidate_hash": sha256(paths["result.json"]),
                    "expected_hash": expected.get("result.json", ""),
                    "parameter_identity": "PASS" if parameter_identity else "FAIL",
                    "instance_identity": "PASS" if instance_identity else "FAIL",
                    "model_identity": "PASS" if model_identity else "FAIL",
                    "runner_identity": "PASS" if runner_identity else "FAIL",
                    "certification_identity": "PASS" if certification_identity else "FAIL",
                    "artifact_identity": "PASS" if artifact_identity else "FAIL",
                    "historical_commit": commit,
                    "reuse_eligible": str(eligible).lower(),
                }
            )
    e4_manifest = [
        {
            "classification": "DERIVED_FROM_FROZEN_ARCHIVE_FOR_REUSE_AUDIT",
            "archive_path": (source_repo / "e4_gamma_sensitivity_v1.zip").as_posix(),
            "archive_sha256": e4_zip_hash,
            "relative_path": relative,
            "sha256": value,
            "extracted_file_match": str(
                sha256(source_repo / EXPERIMENTS["E4"]["root"] / relative) == value
            ).lower(),
        }
        for relative, value in sorted(e4_hashes.items())
    ]
    summary = {
        "schema": "e6_5x5_historical_source_audit_v1",
        "source_repo": source_repo.as_posix(),
        "optimization_calls": 0,
        "E3_source_path": (source_repo / EXPERIMENTS["E3"]["root"]).as_posix(),
        "E4_source_path": (source_repo / EXPERIMENTS["E4"]["root"]).as_posix(),
        "E6_source_path": (source_repo / EXPERIMENTS["E6"]["root"]).as_posix(),
        "E3_frozen_archive_sha256": sha256(source_repo / "experiments/results/e3_budget_sensitivity_v1.zip"),
        "E4_frozen_archive_sha256": e4_zip_hash,
        "E6_review_package_sha256": sha256(source_repo / "e6_full_review_package.zip"),
        "candidate_count": len(rows),
        "eligible_count": sum(row["reuse_eligible"] == "true" for row in rows),
        "historical_commits": sorted({row["historical_commit"] for row in rows}),
        "model_identity_by_commit": model_cache,
        "status": "PASS" if all(row["reuse_eligible"] == "true" for row in rows) else "FAIL",
    }
    return rows, e4_manifest, summary


def write_outputs(rows: list[dict], e4_manifest: list[dict], summary: dict) -> None:
    with (ARTIFACTS / "e6_budget_risk_5x5_historical_source_audit.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with (ARTIFACTS / "e4_per_file_hashes_for_e6_reuse_audit.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(e4_manifest[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(e4_manifest)
    (ARTIFACTS / "e6_budget_risk_5x5_historical_source_audit.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit historical E3/E4/E6 sources without optimization")
    parser.add_argument("--source-repo", type=Path, required=True)
    args = parser.parse_args()
    rows, e4_manifest, summary = audit(args.source_repo.resolve())
    write_outputs(rows, e4_manifest, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
