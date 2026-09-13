from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robust_inventory_reconfiguration.e4_reporting import evaluate_e4_service
from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.reconfiguration_model import reconfiguration_index
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


MANIFEST = ROOT / "experiments/configs/formal/e6_budget_risk_interaction_authorization.json"
STATIC_AUDIT = ROOT / "artifacts/e6_static_audit.json"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
RESULT_ROOT = ROOT / "experiments/results/e6_budget_risk_interaction_v1"
E3_ROOT = ROOT / "experiments/results/e3_budget_sensitivity_v1"
E4_ROOT = ROOT / "experiments/results/e4_gamma_sensitivity_v1"
E3_RUNNER = "experiments/run_e3_budget_local.py"
E4_RUNNER = "experiments/run_e4_gamma_local.py"
E3_MANIFEST = "experiments/configs/formal/e3_budget_sensitivity_authorization.json"
E4_MANIFEST = "experiments/configs/formal/e4_gamma_sensitivity_authorization.json"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
BETA_BY_TOKEN = {"B080": Decimal("0.80"), "B100": Decimal("1.00"), "B120": Decimal("1.20")}
GAMMA_BY_TOKEN = {"G0": 0, "G2": 2, "G4": 4}
LAMBDA_R = 0.05
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
PRB_FILE = ROOT / "src/robust_inventory_reconfiguration/product_risk_budget_benders.py"


@dataclass(frozen=True)
class Condition:
    case: str
    beta_token: str
    gamma_token: str

    @property
    def beta(self) -> Decimal:
        return BETA_BY_TOKEN[self.beta_token]

    @property
    def gamma(self) -> int:
        return GAMMA_BY_TOKEN[self.gamma_token]

    @property
    def run_id(self) -> str:
        return f"E6-{self.case}-{self.beta_token}-{self.gamma_token}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=None)
def git_file_sha256(revision: str, path: str) -> str:
    content = subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)
    return hashlib.sha256(content).hexdigest()


@lru_cache(maxsize=None)
def source_model_identity(revision: str | None = None) -> str:
    hashes = {}
    for name in MODEL_FILES:
        content = (
            (ROOT / name).read_bytes()
            if revision is None
            else subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=ROOT)
        )
        hashes[name] = hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()
    return canonical_hash(hashes)


def parse_beta_token(value: str) -> str:
    if value not in BETA_BY_TOKEN:
        raise ValueError(f"beta token must be one of {list(BETA_BY_TOKEN)}")
    return value


def parse_gamma_token(value: str) -> str:
    if value not in GAMMA_BY_TOKEN:
        raise ValueError(f"Gamma token must be one of {list(GAMMA_BY_TOKEN)}")
    return value


def make_run_id(case: str, beta_token: str, gamma_token: str) -> str:
    return Condition(case, parse_beta_token(beta_token), parse_gamma_token(gamma_token)).run_id


def enumerate_conditions() -> list[Condition]:
    return [
        Condition(case, beta_token, gamma_token)
        for case in CASES
        for beta_token in BETA_BY_TOKEN
        for gamma_token in GAMMA_BY_TOKEN
    ]


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_identities() -> dict[str, dict[str, str]]:
    with IDENTITY_TABLE.open(encoding="utf-8", newline="") as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


def validate_manifest(manifest: dict) -> None:
    expected_ids = [condition.run_id for condition in enumerate_conditions()]
    checks = {
        "dataset": manifest["dataset_id"] == "RENAULT_EMPIRICAL_8CASE_V1",
        "cases": manifest["cases"] == list(CASES),
        "beta_grid": manifest["beta_tokens"] == list(BETA_BY_TOKEN)
        and manifest["beta_grid"] == [str(value) for value in BETA_BY_TOKEN.values()],
        "Gamma_grid": manifest["Gamma_tokens"] == list(GAMMA_BY_TOKEN)
        and manifest["Gamma_grid"] == list(GAMMA_BY_TOKEN.values()),
        "lambda_R": manifest["lambda_R"] == LAMBDA_R,
        "run_ids": manifest["planned_run_ids"] == expected_ids,
        "result_root": manifest["result_root"] == "experiments/results/e6_budget_risk_interaction_v1",
        "solver_profile": manifest["solver_profile"] == FORMAL_SOLVER_PROFILE_ID,
        "materiality": manifest["materiality_tolerance"] == 1e-6,
        "identity_table": sha256(IDENTITY_TABLE) == manifest["identity_table_sha256"],
        "model_files": manifest["model_files"] == list(MODEL_FILES),
        "model": source_model_identity() == manifest["model_identity_sha256"],
        "model_reference": source_model_identity(manifest["model_reference_commit"])
        == manifest["model_identity_sha256"],
        "prb": sha256(PRB_FILE) == manifest["prb_identity_sha256"],
        "coverage": all(
            set(manifest[key]) == set(CASES)
            for key in ("B_ref_by_case", "instance_hashes", "x0_hashes", "calibration_hashes")
        ),
        "runner": sha256(Path(__file__)) == manifest["runner_sha256"],
        "reporter": sha256(ROOT / manifest["reporting_script"]) == manifest["reporting_script_sha256"],
        "plotter": sha256(ROOT / manifest["plotting_script"]) == manifest["plotting_script_sha256"],
        "schema": sha256(ROOT / manifest["result_schema"]) == manifest["result_schema_sha256"],
        "protocol_document": sha256(ROOT / manifest["protocol_document"])
        == manifest["protocol_document_sha256"],
        "static_audit_script": sha256(ROOT / manifest["static_audit_script"])
        == manifest["static_audit_script_sha256"],
        "reuse_plan": sha256(ROOT / manifest["reuse_plan"]) == manifest["reuse_plan_sha256"],
        "preauthorization_static_audit": git_file_sha256(
            manifest["authorization_basis_commit"], manifest["preauthorization_static_audit"]
        )
        == manifest["preauthorization_static_audit_sha256"],
        "authorization": manifest["authorization_transition"] in ([False], [False, True])
        and manifest["authorization_transition"][-1] is manifest["formal_run_authorized"],
        "authorization_scope": manifest["formal_run_authorized"] is True
        and manifest["authorization_scope"] == [manifest["experiment_id"]]
        and manifest["authorization_exclusions"]
        == ["E7", "SCALING", "STANDARD_BENDERS", "FUTURE_EXPERIMENTS"],
        "authorization_status": manifest["protocol_status"] == "E6_FORMAL_RUN_AUTHORIZED",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E6_MANIFEST_IDENTITY: {','.join(failed)}")


def validate_case_identity(case: str, manifest: dict, identity: dict[str, str]) -> None:
    paths = {
        "instance_hash": ROOT / f"data/formal_instances_v2/{case}.json",
        "x0_hash": ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json",
        "calibration_hash": ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json",
    }
    checks = {
        "instance": sha256(paths["instance_hash"]) == identity["instance_hash"] == manifest["instance_hashes"][case],
        "x0": sha256(paths["x0_hash"]) == identity["x0_hash"] == manifest["x0_hashes"][case],
        "calibration": sha256(paths["calibration_hash"]) == identity["calibration_hash"] == manifest["calibration_hashes"][case],
        "mapping": identity["mapping_hash"] == manifest["mapping_sha256"],
        "B_ref": json.loads(paths["calibration_hash"].read_text(encoding="utf-8"))["B_ref"]
        == manifest["B_ref_by_case"][case],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E6_CASE_IDENTITY: {case}: {','.join(failed)}")


def expected_budget(condition: Condition, manifest: dict) -> float:
    return float(condition.beta * Decimal(str(manifest["B_ref_by_case"][condition.case])))


def source_descriptor(path: Path) -> dict:
    result_path = path / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    source_experiment = "E3" if result["run_id"].startswith("E3-") else "E4"
    return {
        "experiment": source_experiment,
        "run_id": result["run_id"],
        "directory": path,
        "result": result,
    }


def discover_source_candidates() -> dict[tuple[str, str, str], list[dict]]:
    candidates: dict[tuple[str, str, str], list[dict]] = {}
    beta_tokens = {float(beta): token for token, beta in BETA_BY_TOKEN.items()}
    gamma_tokens = {gamma: token for token, gamma in GAMMA_BY_TOKEN.items()}
    for root in (E3_ROOT, E4_ROOT):
        for result_path in sorted(root.glob("*/result.json")):
            source = source_descriptor(result_path.parent)
            result = source["result"]
            beta_token = beta_tokens.get(float(result.get("beta", math.nan)))
            gamma_token = gamma_tokens.get(result.get("Gamma"))
            if (
                result.get("case") in CASES
                and beta_token is not None
                and gamma_token is not None
                and result.get("lambda_R") == LAMBDA_R
            ):
                key = (result["case"], beta_token, gamma_token)
                candidates.setdefault(key, []).append(source)
    return candidates


def expected_reuse_cells_from_source_design() -> set[tuple[str, str]]:
    e3 = json.loads((ROOT / E3_MANIFEST).read_text(encoding="utf-8"))
    e4 = json.loads((ROOT / E4_MANIFEST).read_text(encoding="utf-8"))
    beta_tokens = {Decimal(value): token for token, value in BETA_BY_TOKEN.items()}
    gamma_tokens = {gamma: token for token, gamma in GAMMA_BY_TOKEN.items()}
    cells = set()
    if e3["lambda_R"] == LAMBDA_R and e3["Gamma"] in gamma_tokens:
        cells.update(
            (beta_tokens[Decimal(str(beta))], gamma_tokens[e3["Gamma"]])
            for beta in e3["beta_grid"]
            if Decimal(str(beta)) in beta_tokens
        )
    if e4["lambda_R"] == LAMBDA_R and Decimal(str(e4["beta"])) in beta_tokens:
        cells.update(
            (beta_tokens[Decimal(str(e4["beta"]))], gamma_tokens[gamma])
            for gamma in e4["Gamma_grid"]
            if gamma in gamma_tokens
        )
    return cells


def validate_source_provenance(source: dict) -> dict[str, bool]:
    directory = source["directory"]
    provenance_path = directory / "provenance.json"
    solution_path = directory / "first_stage_solution.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    runner_path = E3_RUNNER if source["experiment"] == "E3" else E4_RUNNER
    manifest_path = E3_MANIFEST if source["experiment"] == "E3" else E4_MANIFEST
    checks = {
        "files": provenance_path.is_file() and solution_path.is_file(),
        "result_hash": provenance["result_sha256"] == sha256(directory / "result.json"),
        "solution_hash": provenance["first_stage_solution_sha256"] == sha256(solution_path),
        "historical_runner_hash": provenance["runner_sha256"]
        == git_file_sha256(provenance["git_commit"], runner_path),
        "historical_manifest_hash": provenance["manifest_sha256"]
        == git_file_sha256(provenance["git_commit"], manifest_path),
    }
    return checks


def validate_reuse_candidate(
    condition: Condition, source: dict, manifest: dict, identity: dict[str, str]
) -> dict[str, bool]:
    result = source["result"]
    provenance = json.loads((source["directory"] / "provenance.json").read_text(encoding="utf-8"))
    solution = json.loads((source["directory"] / "first_stage_solution.json").read_text(encoding="utf-8"))
    tolerance = manifest["objective_certification_tolerance"]
    checks = {
        **{f"provenance_{key}": value for key, value in validate_source_provenance(source).items()},
        "case": result["case"] == solution["case_id"] == condition.case,
        "dataset": result["dataset_id"] == manifest["dataset_id"],
        "condition": result["beta"] == float(condition.beta)
        and result["Gamma"] == condition.gamma
        and result["lambda_R"] == LAMBDA_R,
        "budget": abs(result["B"] - expected_budget(condition, manifest)) <= manifest["budget_feasibility_tolerance"],
        "B_ref": result["B_ref"] == manifest["B_ref_by_case"][condition.case],
        "instance": result["instance_hash"] == identity["instance_hash"] == manifest["instance_hashes"][condition.case],
        "x0": result["x0_hash"] == identity["x0_hash"] == manifest["x0_hashes"][condition.case],
        "calibration": result["calibration_hash"] == identity["calibration_hash"] == manifest["calibration_hashes"][condition.case],
        "mapping": result["mapping_hash"] == identity["mapping_hash"] == manifest["mapping_sha256"],
        "solver_profile": result["solver_profile"] == manifest["solver_profile"],
        "model": result["model_identity_sha256"] == manifest["model_identity_sha256"]
        == source_model_identity(provenance["git_commit"]),
        "status": result["status"] == "OPTIMAL",
        "certification": result["certification_status"] == "CERTIFIED_PRB_EXACT"
        and result.get("exact_certification_pass", True) is True,
        "objective_accounting": abs(
            result["objective"] - result["budget_used"] - result["robust_recourse_cost"]
        ) <= tolerance,
        "solution_dimensions": solution["dimensions"]["x_entries"]
        == len(solution["depot_ids"]) * len(solution["product_ids"]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(
            f"BLOCK_E6_REUSE_IDENTITY_MISMATCH: {condition.run_id}: "
            f"{source['run_id']}: {','.join(failed)}"
        )
    return checks


def validate_overlap(condition: Condition, sources: list[dict], manifest: dict) -> dict[str, bool]:
    by_experiment = {source["experiment"]: source for source in sources}
    if set(by_experiment) != {"E3", "E4"}:
        raise RuntimeError(f"BLOCK_E6_OVERLAP_SOURCE_SET: {condition.run_id}")
    e3 = by_experiment["E3"]
    e4 = by_experiment["E4"]
    fields = (
        "B", "B_ref", "objective", "fixed_cost", "inventory_cost", "reconfiguration_cost",
        "robust_recourse_cost", "budget_used", "RI", "RS", "active_depots",
    )
    checks = {
        "condition": condition.beta_token == "B100" and condition.gamma_token == "G2",
        "E4_points_to_E3": e4["result"].get("reuse_source_run") == e3["run_id"],
        "first_stage_identity": sha256(e3["directory"] / "first_stage_solution.json")
        == sha256(e4["directory"] / "first_stage_solution.json"),
        "economic_identity": all(
            abs(float(e3["result"][field]) - float(e4["result"][field]))
            <= manifest["reporting_tolerance"]
            for field in fields
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E6_OVERLAP_IDENTITY: {condition.run_id}: {','.join(failed)}")
    return checks


def build_reuse_plan(manifest: dict | None = None) -> list[dict]:
    manifest = load_manifest() if manifest is None else manifest
    identities = load_identities()
    source_index = discover_source_candidates()
    expected_reuse_cells = expected_reuse_cells_from_source_design()
    plan = []
    for condition in enumerate_conditions():
        validate_case_identity(condition.case, manifest, identities[condition.case])
        sources = source_index.get((condition.case, condition.beta_token, condition.gamma_token), [])
        validated = []
        for source in sources:
            checks = validate_reuse_candidate(condition, source, manifest, identities[condition.case])
            validated.append({**source, "checks": checks})
        overlap_checks = validate_overlap(condition, validated, manifest) if len(validated) == 2 else None
        if len(validated) > 2:
            raise RuntimeError(f"BLOCK_E6_AMBIGUOUS_REUSE: {condition.run_id}")
        cell = (condition.beta_token, condition.gamma_token)
        if cell in expected_reuse_cells and not validated:
            raise RuntimeError(f"BLOCK_E6_MISSING_REUSE_SOURCE: {condition.run_id}")
        if cell not in expected_reuse_cells and validated:
            raise RuntimeError(f"BLOCK_E6_UNPLANNED_REUSE_SOURCE: {condition.run_id}")
        selected = next((source for source in validated if source["experiment"] == "E3"), None)
        if selected is None and validated:
            selected = validated[0]
        plan.append(
            {
                "run_id": condition.run_id,
                "case": condition.case,
                "beta_token": condition.beta_token,
                "beta": float(condition.beta),
                "Gamma_token": condition.gamma_token,
                "Gamma": condition.gamma,
                "classification": "REUSE" if selected else "NEW_SOLVE",
                "selected_source_experiment": selected["experiment"] if selected else None,
                "selected_source_run": selected["run_id"] if selected else None,
                "source_candidates": [source["run_id"] for source in validated],
                "overlap_identity_checks": overlap_checks,
            }
        )
    return plan


def static_feasibility(case: str, manifest: dict) -> dict:
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    x0_artifact = json.loads(
        (ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8")
    )
    x0 = x0_artifact["x0"]
    removal_cost = LAMBDA_R * sum(
        instance.inventory_cost[i][j] * x0[i][j]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    tight_budget = float(BETA_BY_TOKEN["B080"] * Decimal(str(manifest["B_ref_by_case"][case])))
    finite_nonnegative = all(
        math.isfinite(value) and value >= 0.0 for row in x0 for value in row
    )
    return {
        "case": case,
        "corner": f"E6-{case}-B080-G4",
        "construction": "all depots inactive; x=0; a_plus=0; a_minus=x0; shortage recourse",
        "removal_reconfiguration_cost": removal_cost,
        "B080": tight_budget,
        "budget_slack": tight_budget - removal_cost,
        "x0_finite_nonnegative": finite_nonnegative,
        "capacity_and_UB_feasible_at_x_zero": True,
        "reconfiguration_balance_feasible": finite_nonnegative,
        "recourse_feasible_by_shortage_and_service_violation": True,
        "feasible": finite_nonnegative
        and removal_cost <= tight_budget + manifest["budget_feasibility_tolerance"],
        "optimization_executed": False,
    }


def check_output_target(run_id: str, output_root: Path = RESULT_ROOT) -> None:
    if (output_root / run_id).exists():
        raise FileExistsError(f"refusing to overwrite {run_id}")


def validate_static_audit(manifest: dict) -> None:
    if not STATIC_AUDIT.is_file():
        raise RuntimeError("E6 static audit artifact is missing")
    audit = json.loads(STATIC_AUDIT.read_text(encoding="utf-8"))
    if audit["status"] != "E6_PROTOCOL_STATIC_AUDIT_PASS":
        raise RuntimeError("E6 static audit did not pass")
    if audit["manifest_sha256"] != sha256(MANIFEST):
        raise RuntimeError("E6 config hash differs from the passed static audit")


def dry_run() -> dict:
    manifest = load_manifest()
    validate_manifest(manifest)
    plan = build_reuse_plan(manifest)
    preflight = [static_feasibility(case, manifest) for case in CASES]
    return {
        "status": "E6_DRY_RUN_PASS",
        "total_conditions": len(plan),
        "reusable_conditions": sum(row["classification"] == "REUSE" for row in plan),
        "new_solve_conditions": sum(row["classification"] == "NEW_SOLVE" for row in plan),
        "overlap_conditions": [row["run_id"] for row in plan if len(row["source_candidates"]) > 1],
        "B080_G4_static_feasibility": {row["case"]: row["feasible"] for row in preflight},
        "formal_run_authorized": manifest["formal_run_authorized"],
        "optimization_solver_invocations": 0,
        "conditions": plan,
    }


def cost_components(instance, solution) -> tuple[float, float, float]:
    fixed = sum(instance.fixed_depot_cost[i] * solution.y[i] for i in range(instance.num_depots))
    inventory = sum(
        instance.inventory_cost[i][j] * solution.x[i][j]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    reconfiguration = LAMBDA_R * sum(
        instance.inventory_cost[i][j] * (solution.a_plus[i][j] + solution.a_minus[i][j])
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    return fixed, inventory, reconfiguration


def solve_new_result(condition: Condition, manifest: dict, identity: dict[str, str]):
    instance = load_instance(ROOT / f"data/formal_instances_v2/{condition.case}.json")
    x0_artifact = json.loads(
        (ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case}.json").read_text(encoding="utf-8")
    )
    x0, y0 = x0_artifact["x0"], x0_artifact["y0"]
    budget = expected_budget(condition, manifest)
    solved = solve_prb_benders(instance, x0, budget, condition.gamma, LAMBDA_R)
    if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
        raise RuntimeError("E6 PRB solve is not exactly certified")
    service, reporting_diagnostic = evaluate_e4_service(instance, solved.solution.x, condition.gamma)
    fixed, inventory, reconfiguration = cost_components(instance, solved.solution)
    budget_used = fixed + inventory + reconfiguration
    budget_slack = budget - budget_used
    if -budget_slack > manifest["budget_feasibility_tolerance"]:
        raise RuntimeError("E6 financial budget violation")
    canonical_ri, represented_ri = reconfiguration_index(
        solved.solution.x, x0, solved.solution.a_plus, solved.solution.a_minus
    )
    if abs(canonical_ri - represented_ri) > manifest["reporting_tolerance"]:
        raise RuntimeError("E6 reconfiguration identity mismatch")
    active_ids = [instance.depot_ids[i] for i, value in enumerate(solved.solution.y) if value]
    opened = [instance.depot_ids[i] for i in range(instance.num_depots) if solved.solution.y[i] and not y0[i]]
    closed = [instance.depot_ids[i] for i in range(instance.num_depots) if y0[i] and not solved.solution.y[i]]
    total_adjustment = sum(
        abs(solved.solution.x[i][j] - x0[i][j])
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    result = {
        "run_id": condition.run_id,
        "experiment_id": manifest["experiment_id"],
        "case": condition.case,
        "beta_token": condition.beta_token,
        "beta": float(condition.beta),
        "Gamma_token": condition.gamma_token,
        "Gamma": condition.gamma,
        "lambda_R": LAMBDA_R,
        "B": budget,
        "B_ref": manifest["B_ref_by_case"][condition.case],
        "dataset_id": manifest["dataset_id"],
        "instance_hash": identity["instance_hash"],
        "x0_hash": identity["x0_hash"],
        "calibration_hash": identity["calibration_hash"],
        "mapping_hash": manifest["mapping_sha256"],
        "model_identity_sha256": manifest["model_identity_sha256"],
        "prb_identity_sha256": manifest["prb_identity_sha256"],
        "solver_profile": manifest["solver_profile"],
        "reused": False,
        "reuse_source_run": None,
        "objective": budget_used + service.robust_recourse_cost,
        "fixed_cost": fixed,
        "inventory_cost": inventory,
        "reconfiguration_cost": reconfiguration,
        "robust_recourse_cost": service.robust_recourse_cost,
        "budget_used": budget_used,
        "budget_utilization": budget_used / budget,
        "budget_slack": budget_slack,
        "budget_binding": abs(budget_slack) <= manifest["budget_binding_tolerance"],
        "inventory_spending_share": inventory / budget,
        "reconfiguration_spending_share": reconfiguration / budget,
        "canonical_total_adjustment": total_adjustment,
        "RI": canonical_ri,
        "RS": reconfiguration / budget,
        "changed_pair_count": sum(
            abs(solved.solution.x[i][j] - x0[i][j]) > manifest["materiality_tolerance"]
            for i in range(instance.num_depots)
            for j in range(instance.num_products)
        ),
        "material_reconfiguration": canonical_ri > manifest["materiality_tolerance"],
        "active_depots": len(active_ids),
        "active_depot_ids": active_ids,
        "opened_depots": opened,
        "closed_depots": closed,
        "shortage_cost": service.worst_recourse_scenario.shortage_cost,
        "transportation_cost": service.worst_recourse_scenario.transportation_cost,
        "service_penalty": service.worst_recourse_scenario.service_penalty_cost,
        "total_shortage": service.worst_recourse_scenario.total_shortage,
        "minimum_fill_rate": service.worst_service_scenario.minimum_fill_rate,
        "average_fill_rate": service.worst_service_scenario.average_fill_rate,
        "runtime_seconds": solved.total_runtime,
        "iterations": len(solved.iterations),
        "master_solves": solved.master_solve_count,
        "subproblem_evaluations": solved.product_subproblem_evaluations,
        "cuts": solved.unique_product_cuts,
        "lower_bound": solved.final_lower_bound,
        "upper_bound": solved.final_upper_bound,
        "relative_gap": solved.final_relative_gap,
        "status": "OPTIMAL",
        "certification_status": "CERTIFIED_PRB_EXACT",
        "exact_certification_pass": True,
        "global_coupling_pass": solved.global_risk_budget_coupling_pass,
        "reporting_tiebreak_diagnostic": reporting_diagnostic,
    }
    artifact = build_first_stage_solution_artifact(
        instance,
        x0,
        solved.solution,
        case_id=condition.case,
        mode="E6_PRB",
        identity={
            "config_hash": sha256(MANIFEST),
            "data_hash": identity["instance_hash"],
            "x0_hash": identity["x0_hash"],
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        },
        solver_profile=manifest["solver_profile"],
    )
    return result, artifact


def source_for_condition(condition: Condition, manifest: dict) -> dict | None:
    row = next(row for row in build_reuse_plan(manifest) if row["run_id"] == condition.run_id)
    if row["classification"] != "REUSE":
        return None
    index = discover_source_candidates()
    sources = index[(condition.case, condition.beta_token, condition.gamma_token)]
    return next(source for source in sources if source["run_id"] == row["selected_source_run"])


def build_reused_result(condition: Condition, manifest: dict, identity: dict[str, str]):
    source = source_for_condition(condition, manifest)
    if source is None:
        raise RuntimeError(f"no reusable source for {condition.run_id}")
    result = source["result"]
    solution_path = source["directory"] / "first_stage_solution.json"
    solution = json.loads(solution_path.read_text(encoding="utf-8"))
    x0_artifact = json.loads(
        (ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case}.json").read_text(encoding="utf-8")
    )
    x0 = x0_artifact["x0"]
    if (
        x0_artifact["depot_ids"] != solution["depot_ids"]
        or x0_artifact["product_ids"] != solution["product_ids"]
    ):
        raise RuntimeError(f"BLOCK_E6_REUSE_SOLUTION_IDENTITY: {condition.run_id}")
    x_lookup = {(item["depot_id"], item["product_id"]): item["value"] for item in solution["x"]}
    canonical_adjustment = sum(
        abs(x_lookup[(depot, product)] - x0[i][j])
        for i, depot in enumerate(solution["depot_ids"])
        for j, product in enumerate(solution["product_ids"])
    )
    x0_total = sum(map(sum, x0))
    shortage_cost = result["worst_recourse_shortage_cost"]
    service_penalty = result["worst_recourse_service_penalty_cost"]
    transportation_cost = result.get(
        "transport_cost", result["robust_recourse_cost"] - shortage_cost - service_penalty
    )
    budget = expected_budget(condition, manifest)
    budget_slack = budget - result["budget_used"]
    active_ids = [item["depot_id"] for item in solution["y"] if item["value"]]
    canonical = {
        "run_id": condition.run_id,
        "experiment_id": manifest["experiment_id"],
        "case": condition.case,
        "beta_token": condition.beta_token,
        "beta": float(condition.beta),
        "Gamma_token": condition.gamma_token,
        "Gamma": condition.gamma,
        "lambda_R": LAMBDA_R,
        "B": budget,
        "B_ref": manifest["B_ref_by_case"][condition.case],
        "dataset_id": manifest["dataset_id"],
        "instance_hash": identity["instance_hash"],
        "x0_hash": identity["x0_hash"],
        "calibration_hash": identity["calibration_hash"],
        "mapping_hash": manifest["mapping_sha256"],
        "model_identity_sha256": manifest["model_identity_sha256"],
        "prb_identity_sha256": manifest["prb_identity_sha256"],
        "solver_profile": manifest["solver_profile"],
        "reused": True,
        "reuse_source_run": source["run_id"],
        "objective": result["objective"],
        "fixed_cost": result["fixed_cost"],
        "inventory_cost": result["inventory_cost"],
        "reconfiguration_cost": result["reconfiguration_cost"],
        "robust_recourse_cost": result["robust_recourse_cost"],
        "budget_used": result["budget_used"],
        "budget_utilization": result["budget_used"] / budget,
        "budget_slack": budget_slack,
        "budget_binding": abs(budget_slack) <= manifest["budget_binding_tolerance"],
        "inventory_spending_share": result["inventory_cost"] / budget,
        "reconfiguration_spending_share": result["reconfiguration_cost"] / budget,
        "canonical_total_adjustment": canonical_adjustment,
        "RI": canonical_adjustment / x0_total,
        "RS": result["reconfiguration_cost"] / budget,
        "changed_pair_count": sum(
            abs(x_lookup[(depot, product)] - x0[i][j]) > manifest["materiality_tolerance"]
            for i, depot in enumerate(solution["depot_ids"])
            for j, product in enumerate(solution["product_ids"])
        ),
        "material_reconfiguration": canonical_adjustment / x0_total > manifest["materiality_tolerance"],
        "active_depots": len(active_ids),
        "active_depot_ids": active_ids,
        "opened_depots": result["opened_depots"],
        "closed_depots": result["closed_depots"],
        "shortage_cost": shortage_cost,
        "transportation_cost": transportation_cost,
        "service_penalty": service_penalty,
        "total_shortage": result["worst_recourse_total_shortage"],
        "minimum_fill_rate": result["minimum_fill_rate"],
        "average_fill_rate": result["average_fill_rate"],
        "runtime_seconds": result["runtime_seconds"],
        "iterations": result["iterations"],
        "master_solves": result["master_solves"],
        "subproblem_evaluations": result["product_subproblem_evaluations"],
        "cuts": result["cuts_added"],
        "lower_bound": result.get("lower_bound"),
        "upper_bound": result.get("upper_bound"),
        "relative_gap": result.get("relative_gap"),
        "status": "OPTIMAL",
        "certification_status": result["certification_status"],
        "exact_certification_pass": result.get("exact_certification_pass", True),
        "global_coupling_pass": result.get("global_coupling_pass"),
        "reporting_tiebreak_diagnostic": result.get("reporting_tiebreak_diagnostic"),
    }
    return canonical, solution_path


def write_run(result: dict, first_stage, output_root: Path, manifest: dict) -> None:
    target = output_root / result["run_id"]
    temporary = output_root / f".{result['run_id']}.{uuid4().hex}.tmp"
    temporary.mkdir(parents=True)
    try:
        result_path = temporary / "result.json"
        solution_path = temporary / "first_stage_solution.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if isinstance(first_stage, Path):
            shutil.copy2(first_stage, solution_path)
        else:
            write_first_stage_solution_artifact(solution_path, first_stage)
        provenance = {
            "run_id": result["run_id"],
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "runner_sha256": sha256(Path(__file__)),
            "manifest_sha256": sha256(MANIFEST),
            "result_sha256": sha256(result_path),
            "first_stage_solution_sha256": sha256(solution_path),
            "reused": result["reused"],
            "reuse_source_run": result["reuse_source_run"],
        }
        (temporary / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if target.exists():
            raise FileExistsError(f"refusing to overwrite {result['run_id']}")
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def validate_execution_gate(condition: Condition, output_root: Path) -> tuple[dict, dict[str, str]]:
    manifest = load_manifest()
    validate_manifest(manifest)
    validate_static_audit(manifest)
    if manifest["formal_run_authorized"] is not True:
        raise PermissionError("E6_FORMAL_RUN_NOT_AUTHORIZED")
    if condition.run_id not in manifest["planned_run_ids"]:
        raise PermissionError("E6 run ID is outside the frozen grid")
    if output_root.resolve() != RESULT_ROOT.resolve():
        raise RuntimeError("E6 result namespace is frozen")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E6 requires a clean committed worktree")
    check_output_target(condition.run_id, output_root)
    identity = load_identities()[condition.case]
    validate_case_identity(condition.case, manifest, identity)
    return manifest, identity


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or audit the frozen E6 interaction protocol")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--beta-token", choices=tuple(BETA_BY_TOKEN))
    parser.add_argument("--gamma-token", choices=tuple(GAMMA_BY_TOKEN))
    args = parser.parse_args()
    if args.dry_run:
        if any((args.case, args.beta_token, args.gamma_token)):
            parser.error("--dry-run enumerates the complete frozen grid and takes no condition")
        print(json.dumps(dry_run(), indent=2, default=str))
        return
    if not all((args.case, args.beta_token, args.gamma_token)):
        parser.error("formal execution requires --case, --beta-token, and --gamma-token")
    condition = Condition(args.case, args.beta_token, args.gamma_token)
    manifest, identity = validate_execution_gate(condition, RESULT_ROOT)
    source = source_for_condition(condition, manifest)
    if source is None:
        result, first_stage = solve_new_result(condition, manifest, identity)
    else:
        result, first_stage = build_reused_result(condition, manifest, identity)
    write_run(result, first_stage, RESULT_ROOT, manifest)


if __name__ == "__main__":
    main()
