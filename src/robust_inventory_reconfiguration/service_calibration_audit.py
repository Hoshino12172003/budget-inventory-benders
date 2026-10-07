from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .instance import load_instance
from .service_calibration import (
    BASELINE_PHI_MULTIPLIER,
    BASELINE_SL,
    BETA,
    FORMAL_CASES,
    GAMMA,
    LAMBDA_R,
    calibrated_instance,
    file_sha256,
    phi_vector,
)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_model_identity(root: Path, model_files: list[str]) -> str:
    hashes = {
        name: hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in model_files
    }
    return _canonical_hash(hashes)


def load_identity_table(root: Path, relative_path: str) -> dict[str, dict[str, str]]:
    with (root / relative_path).open(encoding="utf-8", newline="") as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


def baseline_reuse_audit(root: Path, config: dict) -> list[dict[str, object]]:
    identities = load_identity_table(root, config["identity_table"])
    source_manifest_path = root / config["baseline_source"]["manifest"]
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    model_files = config["code_identity"]["model_files"]
    current_model_identity = source_model_identity(root, model_files)
    rows = []
    for case in FORMAL_CASES:
        instance_path = root / f"data/formal_instances_v2/{case}.json"
        x0_path = root / f"artifacts/renault_empirical_8case_v1/x0/{case}.json"
        calibration_path = root / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json"
        run_id = config["baseline_source"]["run_pattern"].replace("<case>", case)
        source_dir = root / config["baseline_source"]["result_root"] / run_id
        result_path = source_dir / "result.json"
        solution_path = source_dir / "first_stage_solution.json"
        provenance_path = source_dir / "provenance.json"
        source = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
        provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.is_file() else {}
        source_files_present = result_path.is_file() and solution_path.is_file() and provenance_path.is_file()
        identity = identities[case]
        instance = load_instance(instance_path)
        expected_phi = phi_vector(instance, BASELINE_PHI_MULTIPLIER)
        calibrated = calibrated_instance(
            instance,
            service_level=BASELINE_SL,
            phi_multiplier=BASELINE_PHI_MULTIPLIER,
        )
        checks = {
            "source_files": source_files_present,
            "instance_identity": file_sha256(instance_path) == identity["instance_hash"] == source_manifest["instance_hashes"][case],
            "data_identity": instance.provenance.get("dataset_id") == config["dataset_id"] == source_manifest["dataset_id"],
            "x0_identity": file_sha256(x0_path) == identity["x0_hash"] == source_manifest["x0_hashes"][case],
            "calibration_identity": file_sha256(calibration_path) == identity["calibration_hash"] == source_manifest["calibration_hashes"][case],
            "model_implementation": current_model_identity == config["code_identity"]["current_model_identity_sha256"] == source_manifest["model_identity_sha256"],
            "uncertainty_set": source_manifest["uncertainty_item_definition"] == "one adverse region-product demand component",
            "Gamma": source.get("Gamma") == GAMMA,
            "beta": source.get("beta") == BETA,
            "lambda_R": source.get("lambda_R") == LAMBDA_R,
            "SL": instance.service_level == [BASELINE_SL] * instance.num_products,
            "phi_definition": instance.service_penalty == expected_phi and calibrated.service_penalty == instance.service_penalty,
            "solver_tolerances": source_manifest["budget_feasibility_tolerance"] == config["solver_tolerances"]["budget_feasibility"] and source_manifest["objective_certification_tolerance"] == config["solver_tolerances"]["objective_certification"],
            "algorithm_configuration": source_manifest["solver_profile"] == config["solver_profile"] and source.get("solver_profile") == config["solver_profile"],
            "evaluation_definition": source_manifest["objective_definition"] == "first-stage economic expenditure plus exact robust recourse at the selected Gamma" and "average_fill_rate" in source and "minimum_fill_rate" in source,
            "result_provenance": source_files_present and provenance.get("result_sha256") == file_sha256(result_path) and provenance.get("first_stage_solution_sha256") == file_sha256(solution_path),
            "exact_certification": source.get("status") == "OPTIMAL" and source.get("certification_status") == "CERTIFIED_PRB_EXACT" and source.get("exact_certification_pass") is True,
        }
        failed = [name for name, passed in checks.items() if not passed]
        rows.append({
            "case_id": case,
            "source_run_id": run_id,
            "reuse_authorized": not failed,
            "classification": "IDENTITY_SAFE_BASELINE_REUSE" if not failed else "BASELINE_REUSE_NOT_AUTHORIZED",
            "failed_checks": ";".join(failed),
            "current_model_identity_sha256": current_model_identity,
            "baseline_source_model_identity_sha256": source_manifest["model_identity_sha256"],
            **{f"check_{name}": passed for name, passed in checks.items()},
        })
    return rows


def write_baseline_audit_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
