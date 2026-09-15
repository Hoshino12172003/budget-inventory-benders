from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.reconfiguration_model import reconfiguration_index
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service_detailed
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/configs/formal/e3_budget_sensitivity_authorization.json"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
RESULT_ROOT = ROOT / "experiments/results/e3_budget_sensitivity_v1"
E1_ROOT = ROOT / "experiments/results/e1_empirical_8case_v1"
E2_ROOT = ROOT / "experiments/results/e2_existing_nominal_robust_v1"
E2_MANIFEST = ROOT / "experiments/configs/formal/e2_existing_nominal_robust_authorization.json"
BETA_GRID = tuple(Decimal(value) for value in ("0.80", "0.90", "1.00", "1.10", "1.20"))
MODEL_FILES = (
    "src/robust_inventory_reconfiguration/instance.py",
    "src/robust_inventory_reconfiguration/reconfiguration_model.py",
    "src/robust_inventory_reconfiguration/recourse.py",
    "src/robust_inventory_reconfiguration/scenarios.py",
    "src/robust_inventory_reconfiguration/product_risk_subproblem.py",
    "src/robust_inventory_reconfiguration/risk_budget_composition.py",
    "src/robust_inventory_reconfiguration/product_risk_budget_benders.py",
    "src/robust_inventory_reconfiguration/robust_service.py",
    "src/robust_inventory_reconfiguration/solver_profile.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_beta(value: str | Decimal | float) -> Decimal:
    beta = Decimal(str(value)).quantize(Decimal("0.00"))
    if beta not in BETA_GRID or Decimal(str(value)) != beta:
        raise ValueError(f"beta must be one of {[str(item) for item in BETA_GRID]}")
    return beta


def beta_code(beta: Decimal) -> str:
    return f"B{int(beta * 100):03d}"


def make_run_id(case: str, beta: Decimal) -> str:
    return f"E3-{case}-{beta_code(beta)}"


def calculate_budget(beta: Decimal, b_ref: float) -> tuple[float, str]:
    exact = beta * Decimal(str(b_ref))
    return float(exact), format(exact, "f")


def budget_audit(budget_used: float, budget: float, tolerance: float) -> dict:
    residual = budget_used - budget
    return {
        "budget_slack": budget - budget_used,
        "budget_absolute_residual": max(0.0, residual),
        "budget_feasibility_pass": residual <= tolerance,
    }


def load_identities() -> dict[str, dict[str, str]]:
    with IDENTITY_TABLE.open(encoding="utf-8", newline="") as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


def source_model_identity(revision: str | None = None) -> str:
    hashes = {}
    for name in MODEL_FILES:
        if revision is None:
            content = (ROOT / name).read_bytes()
        else:
            content = subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=ROOT)
        hashes[name] = hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()
    return canonical_hash(hashes)


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def expected_run_ids(cases: list[str]) -> list[str]:
    return [make_run_id(case, beta) for case in cases for beta in BETA_GRID]


def validate_manifest(manifest: dict) -> None:
    cases = manifest["cases"]
    if manifest["dataset_id"] != "RENAULT_EMPIRICAL_8CASE_V1":
        raise RuntimeError("E3 dataset identity mismatch")
    if [Decimal(value) for value in manifest["beta_grid"]] != list(BETA_GRID):
        raise RuntimeError("E3 beta grid mismatch")
    if manifest["authorized_run_ids"] != expected_run_ids(cases):
        raise RuntimeError("E3 run ID mismatch")
    if manifest["Gamma"] != 2:
        raise RuntimeError("E3 Gamma mismatch")
    if manifest["lambda_R"] != 0.05:
        raise RuntimeError("E3 lambda_R mismatch")
    if manifest["solver_profile"] != FORMAL_SOLVER_PROFILE_ID:
        raise RuntimeError("E3 solver profile mismatch")
    if manifest["result_root"] != "experiments/results/e3_budget_sensitivity_v1":
        raise RuntimeError("E3 result root mismatch")
    if manifest["model_files"] != list(MODEL_FILES):
        raise RuntimeError("E3 model file identity mismatch")
    if sha256(IDENTITY_TABLE) != manifest["identity_table_sha256"]:
        raise RuntimeError("E3 identity table hash mismatch")
    if manifest["e4_e7_authorization"] is not False:
        raise RuntimeError("E4-E7 authorization changed")
    if set(manifest["B_ref_by_case"]) != set(cases):
        raise RuntimeError("E3 B_ref coverage mismatch")
    if set(manifest["instance_hashes"]) != set(cases) or set(manifest["x0_hashes"]) != set(cases):
        raise RuntimeError("E3 identity coverage mismatch")


def validate_case_identity(case: str, manifest: dict, identity: dict[str, str]) -> None:
    instance_path = ROOT / f"data/formal_instances_v2/{case}.json"
    x0_path = ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json"
    calibration_path = ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json"
    checks = {
        "instance_hash": sha256(instance_path) == identity["instance_hash"] == manifest["instance_hashes"][case],
        "x0_hash": sha256(x0_path) == identity["x0_hash"] == manifest["x0_hashes"][case],
        "calibration_hash": sha256(calibration_path) == identity["calibration_hash"] == manifest["calibration_hashes"][case],
        "mapping_hash": identity["mapping_hash"] == manifest["mapping_sha256"],
    }
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    checks["B_ref"] = calibration["B_ref"] == manifest["B_ref_by_case"][case]
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"BLOCK_E3_IDENTITY_MISMATCH: {','.join(failed)}")


def validate_b100_reuse(case: str, manifest: dict, identity: dict[str, str]) -> dict:
    e1 = json.loads((E1_ROOT / f"E1-{case}-PRB/result.json").read_text(encoding="utf-8"))
    e2 = json.loads((E2_ROOT / f"E2-{case}-ROBUST/result.json").read_text(encoding="utf-8"))
    e2_manifest = json.loads(E2_MANIFEST.read_text(encoding="utf-8"))
    checks = {
        "dataset": e1["dataset_id"] == e2_manifest["dataset_id"] == manifest["dataset_id"],
        "case": e1["case"] == e2["case"] == case,
        "run_ids": e1["run_id"] == f"E1-{case}-PRB" and e2["run_id"] == f"E2-{case}-ROBUST" and e2["policy"] == "ROBUST",
        "instance": e1["instance_hash"] == e2["instance_hash"] == identity["instance_hash"],
        "x0": e1["x0_hash"] == e2["x0_hash"] == identity["x0_hash"],
        "calibration": e1["calibration_hash"] == identity["calibration_hash"],
        "B_ref": e1["B"] == manifest["B_ref_by_case"][case],
        "E2_budget_accounting": abs(e2["budget_used"] - manifest["B_ref_by_case"][case]) <= manifest["budget_feasibility_tolerance"],
        "beta": e1["beta"] == 1.0,
        "Gamma": e1["Gamma"] == e2["Gamma_plan"] == e2["Gamma_eval"] == manifest["Gamma"],
        "lambda_R": e1["lambda_R"] == e2_manifest["lambda_R"] == manifest["lambda_R"],
        "solver_profile": e1["solver_profile"] == e2["solver_profile"] == manifest["solver_profile"],
        "method": e1["method"] == "prb_benders",
        "certification": e1["status"] == "OPTIMAL" and e1["exact_certification_status"] == "CERTIFIED_PRB_EXACT",
        "objective": abs(e1["objective"] - e2["objective_eval"]) <= 1e-4,
        "mapping": e1["mapping_hash"] == e2["mapping_hash"] == manifest["mapping_sha256"],
        "model": source_model_identity(e1["git_commit"]) == manifest["model_identity_sha256"],
        "current_model": source_model_identity() == manifest["model_identity_sha256"],
        "first_stage_artifact": (E1_ROOT / f"E1-{case}-PRB/first_stage_solution.json").is_file(),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"BLOCK_E3_B100_REUSE_IDENTITY_MISMATCH: {','.join(failed)}")
    return {"e1": e1, "e2": e2, "checks": checks}


def validate_gate(case: str, beta: Decimal, output_root: Path = RESULT_ROOT) -> tuple[dict, dict[str, str]]:
    manifest = load_manifest()
    validate_manifest(manifest)
    run_id = make_run_id(case, beta)
    if manifest.get("formal_run_authorized") is not True or run_id not in manifest["authorized_run_ids"]:
        raise PermissionError("E3_FORMAL_RUN_NOT_AUTHORIZED")
    if sha256(Path(__file__)) != manifest["runner_sha256"]:
        raise RuntimeError("E3 runner hash mismatch")
    if source_model_identity() != manifest["model_identity_sha256"]:
        raise RuntimeError("E3 model identity mismatch")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E3 requires a clean committed worktree")
    if (output_root / run_id).exists():
        raise FileExistsError(f"refusing to overwrite {run_id}")
    identities = load_identities()
    if case not in identities:
        raise ValueError(f"unknown E3 case: {case}")
    validate_case_identity(case, manifest, identities[case])
    return manifest, identities[case]


def cost_components(instance, solution, lambda_r: float) -> tuple[float, float, float]:
    fixed = sum(instance.fixed_depot_cost[i] * solution.y[i] for i in range(instance.num_depots))
    inventory = sum(instance.inventory_cost[i][j] * solution.x[i][j] for i in range(instance.num_depots) for j in range(instance.num_products))
    reconfiguration = lambda_r * sum(instance.inventory_cost[i][j] * (solution.a_plus[i][j] + solution.a_minus[i][j]) for i in range(instance.num_depots) for j in range(instance.num_products))
    return fixed, inventory, reconfiguration


def reused_result(case: str, budget: float, budget_decimal: str, manifest: dict, identity: dict[str, str]) -> tuple[dict, Path]:
    sources = validate_b100_reuse(case, manifest, identity)
    e1, e2 = sources["e1"], sources["e2"]
    audit = budget_audit(e2["budget_used"], budget, manifest["budget_feasibility_tolerance"])
    result = {
        "run_id": make_run_id(case, Decimal("1.00")), "case": case, "beta": 1.0,
        "B": budget, "B_decimal": budget_decimal, "B_ref": manifest["B_ref_by_case"][case],
        "Gamma": 2, "lambda_R": 0.05, "dataset_id": manifest["dataset_id"],
        "instance_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"],
        "calibration_hash": identity["calibration_hash"], "mapping_hash": manifest["mapping_sha256"],
        "model_identity_sha256": manifest["model_identity_sha256"], "solver_profile": manifest["solver_profile"],
        "reused_from_E1_or_E2": True, "objective": e2["objective_eval"],
        "fixed_cost": e2["fixed_cost"], "inventory_cost": e2["inventory_cost"],
        "reconfiguration_cost": e2["reconfiguration_cost"], "robust_recourse_cost": e2["robust_recourse_cost"],
        "budget_used": e2["budget_used"], "budget_utilization": e2["budget_utilization"], **audit,
        "total_a_plus": e2["total_a_plus"], "total_a_minus": e2["total_a_minus"],
        "total_adjustment": e2["total_adjustment"], "changed_pair_count": e2["changed_pair_count"],
        "RI": e2["RI"], "RS": e2["RS"], "active_depots": e2["active_depots"],
        "opened_depots": e2["opened_depots"], "closed_depots": e2["closed_depots"],
        "worst_recourse_shortage_cost": e2["worst_recourse_shortage_cost"],
        "worst_recourse_service_penalty_cost": e2["worst_recourse_service_penalty_cost"],
        "worst_recourse_total_shortage": e2["worst_recourse_total_shortage"],
        "minimum_fill_rate": e2["minimum_fill_rate"], "average_fill_rate": e2["average_fill_rate"],
        "worst_region": e2["worst_region"], "runtime_seconds": e1["runtime_seconds"],
        "iterations": e1["iterations"], "master_solves": e1["master_solve_count"],
        "product_subproblem_evaluations": e1["product_subproblem_evaluations"],
        "cuts_added": e1["unique_product_cuts"], "certification_status": e1["exact_certification_status"],
        "status": "OPTIMAL",
    }
    return result, E1_ROOT / f"E1-{case}-PRB/first_stage_solution.json"


def solved_result(case: str, beta: Decimal, budget: float, budget_decimal: str, manifest: dict, identity: dict[str, str]):
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    x0_artifact = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8"))
    x0, y0 = x0_artifact["x0"], x0_artifact["y0"]
    solved = solve_prb_benders(instance, x0, budget, 2, 0.05)
    if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
        raise RuntimeError("E3 PRB solve is not exactly certified")
    service = evaluate_robust_service_detailed(instance, solved.solution.x, 2)
    fixed, inventory, reconfiguration = cost_components(instance, solved.solution, 0.05)
    budget_used = fixed + inventory + reconfiguration
    audit = budget_audit(budget_used, budget, manifest["budget_feasibility_tolerance"])
    if not audit["budget_feasibility_pass"]:
        raise RuntimeError("E3 financial budget violation")
    direct_ri, represented_ri = reconfiguration_index(solved.solution.x, x0, solved.solution.a_plus, solved.solution.a_minus)
    if abs(direct_ri - represented_ri) > 1e-6:
        raise RuntimeError("E3 reconfiguration index mismatch")
    opened = [instance.depot_ids[i] for i in range(instance.num_depots) if solved.solution.y[i] and not y0[i]]
    closed = [instance.depot_ids[i] for i in range(instance.num_depots) if y0[i] and not solved.solution.y[i]]
    result = {
        "run_id": make_run_id(case, beta), "case": case, "beta": float(beta),
        "B": budget, "B_decimal": budget_decimal, "B_ref": manifest["B_ref_by_case"][case],
        "Gamma": 2, "lambda_R": 0.05, "dataset_id": manifest["dataset_id"],
        "instance_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"],
        "calibration_hash": identity["calibration_hash"], "mapping_hash": manifest["mapping_sha256"],
        "model_identity_sha256": manifest["model_identity_sha256"], "solver_profile": manifest["solver_profile"],
        "reused_from_E1_or_E2": False, "objective": budget_used + service.robust_recourse_cost,
        "fixed_cost": fixed, "inventory_cost": inventory, "reconfiguration_cost": reconfiguration,
        "robust_recourse_cost": service.robust_recourse_cost, "budget_used": budget_used,
        "budget_utilization": budget_used / budget, **audit,
        "total_a_plus": sum(map(sum, solved.solution.a_plus)), "total_a_minus": sum(map(sum, solved.solution.a_minus)),
        "total_adjustment": sum(map(sum, solved.solution.a_plus)) + sum(map(sum, solved.solution.a_minus)),
        "changed_pair_count": sum(abs(solved.solution.x[i][j] - x0[i][j]) > 1e-6 for i in range(instance.num_depots) for j in range(instance.num_products)),
        "RI": direct_ri, "RS": reconfiguration / budget, "active_depots": sum(solved.solution.y),
        "opened_depots": opened, "closed_depots": closed,
        "worst_recourse_shortage_cost": service.worst_recourse_scenario.shortage_cost,
        "worst_recourse_service_penalty_cost": service.worst_recourse_scenario.service_penalty_cost,
        "worst_recourse_total_shortage": service.worst_recourse_scenario.total_shortage,
        "minimum_fill_rate": service.worst_service_scenario.minimum_fill_rate,
        "average_fill_rate": service.worst_service_scenario.average_fill_rate,
        "worst_region": service.worst_service_scenario.worst_region_id,
        "runtime_seconds": solved.total_runtime, "iterations": len(solved.iterations),
        "master_solves": solved.master_solve_count,
        "product_subproblem_evaluations": solved.product_subproblem_evaluations,
        "cuts_added": solved.unique_product_cuts,
        "certification_status": "CERTIFIED_PRB_EXACT", "status": "OPTIMAL",
    }
    artifact = build_first_stage_solution_artifact(
        instance, x0, solved.solution, case_id=case, mode="E3_PRB",
        identity={"config_hash": sha256(MANIFEST), "data_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"], "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()},
        solver_profile=manifest["solver_profile"],
    )
    return result, artifact


def write_run(result: dict, first_stage, output_root: Path, manifest: dict) -> None:
    target = output_root / result["run_id"]
    temporary = output_root / f".{result['run_id']}.{uuid4().hex}.tmp"
    temporary.mkdir(parents=True)
    try:
        (temporary / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if isinstance(first_stage, Path):
            shutil.copy2(first_stage, temporary / "first_stage_solution.json")
        else:
            write_first_stage_solution_artifact(temporary / "first_stage_solution.json", first_stage)
        provenance = {
            "run_id": result["run_id"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "runner_sha256": sha256(Path(__file__)), "manifest_sha256": sha256(MANIFEST),
            "result_sha256": sha256(temporary / "result.json"),
            "first_stage_solution_sha256": sha256(temporary / "first_stage_solution.json"),
            "reused_from_E1_or_E2": result["reused_from_E1_or_E2"],
            "reuse_source_runs": [f"E1-{result['case']}-PRB", f"E2-{result['case']}-ROBUST"] if result["reused_from_E1_or_E2"] else [],
        }
        (temporary / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if target.exists():
            raise FileExistsError(f"refusing to overwrite {result['run_id']}")
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--beta", required=True)
    parser.add_argument("--output-root", type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    beta = parse_beta(args.beta)
    manifest, identity = validate_gate(args.case, beta, args.output_root)
    budget, budget_decimal = calculate_budget(beta, manifest["B_ref_by_case"][args.case])
    if beta == Decimal("1.00"):
        result, first_stage = reused_result(args.case, budget, budget_decimal, manifest, identity)
    else:
        result, first_stage = solved_result(args.case, beta, budget, budget_decimal, manifest, identity)
    write_run(result, first_stage, args.output_root, manifest)


if __name__ == "__main__":
    main()
