from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import zipfile

from gurobipy import GRB

from robust_inventory_reconfiguration.nominal_baseline import (
    NominalBaseline, baseline_feasibility, build_nominal_model, solve_nominal_baseline,
)
from robust_inventory_reconfiguration.renault_empirical import (
    CASES, DATASET_ID, MAPPING_SHA256, build_case, canonical_bytes,
    sha256_bytes, sha256_file, verify_mapping,
)


ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = ROOT / "artifacts" / "e1_empirical_region_mapping_v1.json"
OBJECTIVE_FACE_TOLERANCE = 1e-7
STRUCTURAL_RANGE_TOLERANCE = 1e-3
POSITIVE_TOLERANCE = 1e-8
PROTECTED_PATHS = (
    "data/formal_instances",
    "artifacts/nominal_baseline_210202.csv",
    "artifacts/nominal_baseline_210628.csv",
    "artifacts/nominal_baseline_summary.json",
    "artifacts/nominal_baseline_provenance.json",
    "experiments/results/formal_acceptance_batch_1",
    "experiments/results/e1_algorithm_benchmark/attempt_001",
    "experiments/results/e1_algorithm_benchmark/attempt_002",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def tree_hash(path: Path) -> str:
    if path.is_file():
        return sha256_file(path)
    entries = [
        {"path": child.relative_to(path).as_posix(), "sha256": sha256_file(child)}
        for child in sorted(path.rglob("*")) if child.is_file()
    ]
    return sha256_bytes(canonical_bytes(entries))


def protected_hashes() -> dict[str, str]:
    return {relative: tree_hash(ROOT / relative) for relative in PROTECTED_PATHS}


def structural_audit(instance, baseline: NominalBaseline) -> tuple[dict[str, Any], int]:
    model, y, x, first_stage, recourse = build_nominal_model(instance)
    model.update()
    optimum = baseline.objective
    minimum_flip_gap: float | None = None
    y_rows = []
    solve_count = 0
    for i, depot_id in enumerate(instance.depot_ids):
        trial = model.copy()
        trial.Params.OutputFlag = 0
        trial.addConstr(trial.getVarByName(f"y[{i}]") == 1 - baseline.y[i])
        trial.optimize()
        solve_count += 1
        gap = float(trial.ObjVal - optimum) if trial.Status == GRB.OPTIMAL else None
        if gap is not None:
            minimum_flip_gap = gap if minimum_flip_gap is None else min(minimum_flip_gap, gap)
        y_rows.append({"depot_id": depot_id, "baseline": baseline.y[i], "forced_flip_objective_gap": gap})

    face, _, face_x, face_first_stage, face_recourse = build_nominal_model(instance)
    face.addConstr(face_first_stage + face_recourse <= optimum + OBJECTIVE_FACE_TOLERANCE)
    x_rows = []
    maximum_width = 0.0
    material_count = 0
    for i, depot_id in enumerate(instance.depot_ids):
        for j, product_id in enumerate(instance.product_ids):
            face.setObjective(face_x[i, j], GRB.MINIMIZE)
            face.optimize()
            solve_count += 1
            minimum = float(face_x[i, j].X)
            face.setObjective(face_x[i, j], GRB.MAXIMIZE)
            face.optimize()
            solve_count += 1
            maximum = float(face_x[i, j].X)
            width = maximum - minimum
            maximum_width = max(maximum_width, width)
            material_count += width > STRUCTURAL_RANGE_TOLERANCE
            x_rows.append({
                "depot_id": depot_id, "product_id": product_id,
                "minimum": minimum, "maximum": maximum, "range_width": width,
            })
    stable = (
        minimum_flip_gap is not None
        and minimum_flip_gap > OBJECTIVE_FACE_TOLERANCE
        and material_count == 0
    )
    return {
        "status": "PASS" if stable else f"BLOCK_CASE_X0_DEGENERACY_{instance.provenance['case']}",
        "objective_face_tolerance": OBJECTIVE_FACE_TOLERANCE,
        "structural_range_tolerance": STRUCTURAL_RANGE_TOLERANCE,
        "minimum_y_flip_objective_gap": minimum_flip_gap,
        "maximum_material_x_range": maximum_width,
        "material_x_range_count": material_count,
        "y_stable": minimum_flip_gap is not None and minimum_flip_gap > OBJECTIVE_FACE_TOLERANCE,
        "x_stable": material_count == 0,
        "y_audit": y_rows, "x_audit": x_rows,
    }, solve_count


def build_pass(
    archive_path: Path,
    mapping: dict[str, Any],
    builder_commit: str,
    destination: Path,
    run_structural_audits: bool,
) -> tuple[dict[str, Any], int]:
    archive_sha = sha256_file(archive_path)
    results: dict[str, Any] = {}
    solve_count = 0
    with zipfile.ZipFile(archive_path) as archive:
        for case in CASES:
            raw_instance, characteristics = build_case(
                archive, archive_sha, mapping, case, builder_commit
            )
            baseline = solve_nominal_baseline(raw_instance)
            solve_count += 1
            stability, audit_solves = (
                structural_audit(raw_instance, baseline)
                if run_structural_audits else ({"status": "REGENERATED_NOT_REAUDITED"}, 0)
            )
            solve_count += audit_solves
            final_instance = replace(raw_instance, initial_inventory=baseline.x)
            instance_path = destination / "data" / "formal_instances_v2" / f"{case}.json"
            write_json(instance_path, final_instance.to_dict())
            instance_hash = sha256_file(instance_path)
            x0_payload = {
                "schema": "renault_empirical_nominal_incumbent_v1",
                "dataset_id": DATASET_ID, "case": case,
                "definition": "Candidate A: unconstrained-budget Gamma=0 nominal optimum",
                "solver_profile": "gurobi-nominal-exact-1e-9-v1",
                "instance_sha256": instance_hash,
                "depot_ids": final_instance.depot_ids, "product_ids": final_instance.product_ids,
                "y0": baseline.y, "x0": baseline.x,
            }
            x0_path = destination / "artifacts" / DATASET_ID.lower() / "x0" / f"{case}.json"
            write_json(x0_path, x0_payload)
            x0_hash = sha256_file(x0_path)
            calibration = {
                "schema": "renault_empirical_bref_v1", "dataset_id": DATASET_ID,
                "case": case, "contract": "first-stage expenditure of the nominal incumbent",
                "gamma": 0, "budget": None, "lambda_R": None,
                "nominal_objective": baseline.objective,
                "first_stage_spending": baseline.first_stage_spending,
                "nominal_recourse": baseline.recourse_cost,
                "B_ref": baseline.first_stage_spending,
                "instance_sha256": instance_hash, "x0_sha256": x0_hash,
                "builder_commit": builder_commit,
            }
            calibration_path = destination / "artifacts" / DATASET_ID.lower() / "calibration" / f"{case}.json"
            write_json(calibration_path, calibration)
            calibration_hash = sha256_file(calibration_path)
            if run_structural_audits:
                write_json(
                    destination / "artifacts" / DATASET_ID.lower() / "stability" / f"{case}.json",
                    stability,
                )
            feasibility = baseline_feasibility(final_instance, baseline)
            per_product = {
                product: sum(baseline.x[i][j] for i in range(final_instance.num_depots))
                for j, product in enumerate(final_instance.product_ids)
            }
            results[case] = {
                "characteristics": characteristics,
                "instance_sha256": instance_hash, "x0_sha256": x0_hash,
                "calibration_sha256": calibration_hash,
                "baseline": asdict(baseline), "per_product": per_product,
                "positive_pairs": sum(value > POSITIVE_TOLERANCE for row in baseline.x for value in row),
                "active_depots": sum(baseline.y), "total_inventory": sum(map(sum, baseline.x)),
                "feasibility": feasibility, "stability": stability,
            }
    return results, solve_count


def copy_generated(source: Path) -> None:
    for relative in ("data/formal_instances_v2", f"artifacts/{DATASET_ID.lower()}"):
        target = ROOT / relative
        if target.exists():
            raise FileExistsError(f"refusing to overwrite paper-final dataset path: {target}")
        shutil.copytree(source / relative, target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the paper-final eight-case Renault dataset.")
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    verify_mapping(mapping)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("dataset construction requires a clean committed worktree")
    builder_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    before = protected_hashes()
    with tempfile.TemporaryDirectory(prefix="renault_empirical_8case_v1_") as temporary:
        temporary_path = Path(temporary)
        first, first_solves = build_pass(args.archive, mapping, builder_commit, temporary_path / "first", True)
        second, second_solves = build_pass(args.archive, mapping, builder_commit, temporary_path / "second", False)
        hashes_identical = all(
            first[case][key] == second[case][key]
            for case in CASES for key in ("instance_sha256", "x0_sha256", "calibration_sha256")
        )
        if not hashes_identical:
            raise RuntimeError("BLOCK_EMPIRICAL_REGENERATION")
        copy_generated(temporary_path / "first")
    after = protected_hashes()
    if before != after:
        raise RuntimeError("historical artifact protection failed")

    blocked = [case for case in CASES if first[case]["stability"]["status"] != "PASS"]
    status = "RENAULT_EMPIRICAL_8CASE_V1_READY" if not blocked else "RENAULT_EMPIRICAL_8CASE_V1_PARTIAL"
    characteristics_rows, x0_rows, bref_rows, identity_rows = [], [], [], []
    for case in CASES:
        result = first[case]
        characteristics_rows.append(result["characteristics"])
        baseline = result["baseline"]
        x0_rows.append({
            "case": case, "x0_total": result["total_inventory"],
            "positive_pairs": result["positive_pairs"], "active_depots": result["active_depots"],
            "per_product_summary": json.dumps(result["per_product"], sort_keys=True, separators=(",", ":")),
            "stability_status": result["stability"]["status"],
        })
        bref_rows.append({
            "case": case, "nominal_objective": baseline["objective"],
            "first_stage_spending": baseline["first_stage_spending"],
            "nominal_recourse": baseline["recourse_cost"], "B_ref": baseline["first_stage_spending"],
        })
        identity_rows.append({
            "case": case, "raw_identity": f"external://renault-raw/instances/{case}/",
            "mapping_hash": MAPPING_SHA256, "instance_hash": result["instance_sha256"],
            "x0_hash": result["x0_sha256"], "calibration_hash": result["calibration_sha256"],
            "builder_commit": builder_commit,
        })
    write_csv(ROOT / "table_empirical_8case_characteristics.csv", characteristics_rows)
    write_csv(ROOT / "table_empirical_8case_x0.csv", x0_rows)
    write_csv(ROOT / "table_empirical_8case_bref.csv", bref_rows)
    write_csv(ROOT / "table_empirical_8case_identity.csv", identity_rows)
    mapping_artifact = {
        **mapping, "paper_final_dataset_id": DATASET_ID,
        "paper_final_status": "FROZEN_DECISION_C",
        "legacy_compatibility_result_retained_as_history": True,
    }
    write_json(ROOT / "artifacts" / DATASET_ID.lower() / "region_mapping.json", mapping_artifact)
    total_solves = first_solves + second_solves
    summary = {
        "dataset_id": DATASET_ID, "status": status, "cases": first,
        "mapping_sha256": MAPPING_SHA256, "blocked_cases": blocked,
        "deterministic_regeneration": "PASS",
        "data_preparation_optimization_solve_count": total_solves,
        "gamma2_e1_direct_solves": 0, "gamma2_e1_prb_solves": 0,
        "synthetic_execution": 0, "e2_e7_authorization": False,
        "old_formal_artifacts_overwritten": False,
        "historical_protection_hashes": before,
    }
    write_json(ROOT / "artifacts" / DATASET_ID.lower() / "dataset_summary.json", summary)
    print(json.dumps({
        "status": status, "data_preparation_solves": total_solves,
        "blocked_cases": blocked, "deterministic_regeneration": "PASS",
    }, indent=2))


if __name__ == "__main__":
    main()
