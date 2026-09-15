from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from decimal import Decimal
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import experiments.run_e3_budget_local as runner
from robust_inventory_reconfiguration.first_stage_solution import load_first_stage_solution_artifact
from robust_inventory_reconfiguration.instance import load_instance


ROOT = Path(__file__).resolve().parents[1]
AUDIT_OUTPUT = ROOT / "artifacts/e3_final_result_audit.json"
HASH_OUTPUT = ROOT / "artifacts/e3_primary_result_hashes.csv"
ARCHIVE = ROOT / "experiments/results/e3_budget_sensitivity_v1.zip"
TOLERANCE = 1e-6


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    manifest = runner.load_manifest()
    runner.validate_manifest(manifest)
    expected = set(manifest["authorized_run_ids"])
    directories = sorted(path for path in runner.RESULT_ROOT.iterdir() if path.is_dir())
    rows = []
    checks_by_run = {}
    seen = set()
    with zipfile.ZipFile(ARCHIVE) as archive:
        archive_entries = set(archive.namelist())
        for directory in directories:
            paths = {name: directory / name for name in ("result.json", "first_stage_solution.json", "provenance.json")}
            if not all(path.is_file() for path in paths.values()):
                raise RuntimeError(f"BLOCK_E3_RESULT_CORRECTNESS: incomplete files in {directory.name}")
            result = json.loads(paths["result.json"].read_text(encoding="utf-8"))
            provenance = json.loads(paths["provenance.json"].read_text(encoding="utf-8"))
            run_id = result["run_id"]
            if run_id in seen:
                raise RuntimeError(f"BLOCK_E3_RESULT_CORRECTNESS: duplicate {run_id}")
            seen.add(run_id)
            case = result["case"]
            beta = Decimal(f"{result['beta']:.2f}")
            expected_budget, expected_decimal = runner.calculate_budget(beta, manifest["B_ref_by_case"][case])
            instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
            load_first_stage_solution_artifact(paths["first_stage_solution.json"], instance)
            hashes = {name: runner.sha256(path) for name, path in paths.items()}
            zip_matches = {}
            for name, digest in hashes.items():
                archive_name = f"e3_budget_sensitivity_v1/{run_id}/{name}"
                zip_matches[name] = archive_name in archive_entries and sha256_bytes(archive.read(archive_name)) == digest
            objective_reconstructed = (
                result["fixed_cost"] + result["inventory_cost"]
                + result["reconfiguration_cost"] + result["robust_recourse_cost"]
            )
            checks = {
                "directory_identity": directory.name == run_id,
                "status": result["status"] == "OPTIMAL" and result["certification_status"] == "CERTIFIED_PRB_EXACT",
                "Gamma": result["Gamma"] == manifest["Gamma"] == 2,
                "lambda_R": result["lambda_R"] == manifest["lambda_R"] == 0.05,
                "B_ref": result["B_ref"] == manifest["B_ref_by_case"][case],
                "beta": runner.make_run_id(case, beta) == run_id,
                "B": result["B"] == expected_budget and result["B_decimal"] == expected_decimal,
                "budget": result["budget_feasibility_pass"] is True and result["budget_used"] - result["B"] <= TOLERANCE,
                "objective_accounting": abs(result["objective"] - objective_reconstructed) <= TOLERANCE,
                "dataset": result["dataset_id"] == manifest["dataset_id"],
                "instance": result["instance_hash"] == manifest["instance_hashes"][case],
                "x0": result["x0_hash"] == manifest["x0_hashes"][case],
                "calibration": result["calibration_hash"] == manifest["calibration_hashes"][case],
                "mapping": result["mapping_hash"] == manifest["mapping_sha256"],
                "model": result["model_identity_sha256"] == manifest["model_identity_sha256"],
                "solver_profile": result["solver_profile"] == manifest["solver_profile"],
                "reuse": result["reused_from_E1_or_E2"] is (beta == Decimal("1.00")),
                "provenance_identity": provenance["run_id"] == run_id,
                "provenance_result_hash": provenance["result_sha256"] == hashes["result.json"],
                "provenance_solution_hash": provenance["first_stage_solution_sha256"] == hashes["first_stage_solution.json"],
                "provenance_runner": provenance["runner_sha256"] == manifest["runner_sha256"],
                "provenance_manifest": provenance["manifest_sha256"] == runner.sha256(runner.MANIFEST),
                "zip_archive_match": all(zip_matches.values()),
            }
            checks_by_run[run_id] = checks
            if not all(checks.values()):
                failed = [key for key, passed in checks.items() if not passed]
                raise RuntimeError(f"BLOCK_E3_RESULT_CORRECTNESS: {run_id}: {failed}")
            rows.append({
                "run_id": run_id,
                "case": case,
                "beta": float(beta),
                "result_sha256": hashes["result.json"],
                "first_stage_solution_sha256": hashes["first_stage_solution.json"],
                "provenance_sha256": hashes["provenance.json"],
                "zip_archive_match": True,
            })
    if seen != expected:
        raise RuntimeError(f"BLOCK_E3_RESULT_CORRECTNESS: missing={sorted(expected - seen)}, extra={sorted(seen - expected)}")
    rows.sort(key=lambda row: (manifest["cases"].index(row["case"]), row["beta"]))
    with HASH_OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "status": "E3_FINAL_RESULT_AUDIT_PASS",
        "expected_run_count": 40,
        "observed_run_count": len(rows),
        "B100_reuse_count": sum(row["beta"] == 1.0 for row in rows),
        "all_feasible": True,
        "all_certified": True,
        "all_primary_files_match_frozen_zip": True,
        "frozen_zip_sha256": runner.sha256(ARCHIVE),
        "run_checks": checks_by_run,
        "new_optimization_solves": 0,
    }
    AUDIT_OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("E3_FINAL_RESULT_AUDIT_PASS: 40/40")


if __name__ == "__main__":
    main()
