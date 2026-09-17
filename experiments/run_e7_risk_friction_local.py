from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import experiments.run_e6_budget_risk_local as foundation
from robust_inventory_reconfiguration.e4_reporting import evaluate_e4_service
from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    matrix_from_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


MANIFEST = ROOT / "experiments/configs/e7_risk_friction_interaction_v1.json"
AUTHORIZATION_RECORD = ROOT / "experiments/configs/formal/e7_risk_friction_interaction_authorization.json"
STATIC_AUDIT = ROOT / "artifacts/e7_static_audit.json"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
RESULT_ROOT = ROOT / "experiments/results/e7_risk_friction_interaction_v1"
E4_ROOT = ROOT / "experiments/results/e4_gamma_sensitivity_v1"
E5_ROOT = ROOT / "experiments/results/e5_reconfiguration_friction_v1"
E4_MANIFEST = ROOT / "experiments/configs/formal/e4_gamma_sensitivity_authorization.json"
E5_MANIFEST = ROOT / "experiments/configs/formal/e5_reconfiguration_friction_authorization.json"
CASES = foundation.CASES
GAMMA_BY_TOKEN = {"G0": 0, "G2": 2, "G4": 4}
LAMBDA_BY_TOKEN = {"L0025": 0.0025, "L0500": 0.05, "L2000": 0.20}
BETA = 1.0
MODEL_FILES = foundation.MODEL_FILES
PRB_FILE = foundation.PRB_FILE


sha256 = foundation.sha256
canonical_hash = foundation.canonical_hash
git_file_sha256 = foundation.git_file_sha256
source_model_identity = foundation.source_model_identity


@dataclass(frozen=True)
class Condition:
    case: str
    gamma_token: str
    lambda_token: str

    @property
    def gamma(self) -> int:
        return GAMMA_BY_TOKEN[self.gamma_token]

    @property
    def lambda_r(self) -> float:
        return LAMBDA_BY_TOKEN[self.lambda_token]

    @property
    def run_id(self) -> str:
        return f"E7-{self.case}-{self.gamma_token}-{self.lambda_token}"


def parse_gamma_token(value: str) -> str:
    token = value.upper()
    if token not in GAMMA_BY_TOKEN:
        raise ValueError(f"Gamma token must be one of {list(GAMMA_BY_TOKEN)}")
    return token


def parse_lambda_token(value: str) -> str:
    token = value.upper()
    if token not in LAMBDA_BY_TOKEN:
        raise ValueError(f"lambda token must be one of {list(LAMBDA_BY_TOKEN)}")
    return token


def enumerate_conditions() -> list[Condition]:
    return [
        Condition(case, gamma_token, lambda_token)
        for case in CASES
        for gamma_token in GAMMA_BY_TOKEN
        for lambda_token in LAMBDA_BY_TOKEN
    ]


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_identities() -> dict[str, dict[str, str]]:
    with IDENTITY_TABLE.open(encoding="utf-8", newline="") as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


def reporting_evaluator_identity() -> str:
    paths = (
        ROOT / "src/robust_inventory_reconfiguration/robust_service.py",
        ROOT / "src/robust_inventory_reconfiguration/e4_reporting.py",
        ROOT / "src/robust_inventory_reconfiguration/scenarios.py",
    )
    return canonical_hash({str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in paths})


def certification_identity(manifest: dict) -> str:
    return canonical_hash({
        "solver_profile": manifest["solver_profile"],
        "tolerance_contract": manifest["tolerance_contract"],
        "prb_identity_sha256": manifest["prb_identity_sha256"],
        "contract": "status OPTIMAL and CERTIFIED_PRB_EXACT with final exact product-wise robust-recourse certification",
    })


def validate_manifest(manifest: dict) -> None:
    checks = {
        "status": manifest["protocol_status"] == "E7_FORMAL_RUN_AUTHORIZED",
        "authorized": manifest["formal_run_authorized"] is True
        and manifest["authorization_transition"] == [False, True],
        "dataset": manifest["dataset_id"] == "RENAULT_EMPIRICAL_8CASE_V1",
        "cases": manifest["cases"] == list(CASES),
        "beta": manifest["beta"] == BETA,
        "Gamma_grid": manifest["Gamma_levels"] == [
            {"token": token, "value": value} for token, value in GAMMA_BY_TOKEN.items()
        ],
        "lambda_grid": manifest["lambda_levels"] == [
            {"token": token, "value": value} for token, value in LAMBDA_BY_TOKEN.items()
        ],
        "run_ids": manifest["planned_run_ids"] == [condition.run_id for condition in enumerate_conditions()],
        "result_root": manifest["result_root"] == "experiments/results/e7_risk_friction_interaction_v1",
        "authorization_record": manifest["authorization_record"]
        == "experiments/configs/formal/e7_risk_friction_interaction_authorization.json",
        "identity_table": sha256(IDENTITY_TABLE) == manifest["identity_table_sha256"],
        "solver": manifest["solver_profile"] == FORMAL_SOLVER_PROFILE_ID,
        "model": source_model_identity() == manifest["model_identity_sha256"],
        "prb": sha256(PRB_FILE) == manifest["prb_identity_sha256"],
        "reporting_evaluator": reporting_evaluator_identity() == manifest["reporting_evaluator_sha256"],
        "protocol": sha256(ROOT / manifest["protocol_document"]) == manifest["protocol_document_sha256"],
        "schema": sha256(ROOT / manifest["result_schema"]) == manifest["result_schema_sha256"],
        "runner": sha256(Path(__file__)) == manifest["runner_sha256"],
        "audit": sha256(ROOT / manifest["static_audit_script"]) == manifest["static_audit_script_sha256"],
        "reporter": sha256(ROOT / manifest["reporting_script"]) == manifest["reporting_script_sha256"],
        "plotter": sha256(ROOT / manifest["plotting_script"]) == manifest["plotting_script_sha256"],
        "coverage": all(
            set(manifest[key]) == set(CASES)
            for key in ("B_ref_by_case", "instance_hashes", "x0_hashes", "calibration_hashes")
        ),
        "tolerances": manifest["tolerance_contract"] == {
            "budget_feasibility": 1e-6,
            "objective_certification": 1e-4,
            "reporting": 1e-6,
            "materiality": 1e-6,
        },
        "timing_fields": manifest["timing_fields"] == [
            "t_instance_load_seconds", "t_reuse_validation_seconds", "t_core_prb_seconds",
            "t_exact_certification_seconds", "t_post_evaluation_seconds",
            "t_reporting_seconds", "t_artifact_write_seconds", "t_total_runner_wallclock_seconds",
        ],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E7_MANIFEST_IDENTITY: {','.join(failed)}")


def validate_authorization_record(manifest: dict) -> dict:
    if not AUTHORIZATION_RECORD.is_file():
        raise RuntimeError("BLOCK_E7_AUTHORIZATION_RECORD_MISSING")
    record = json.loads(AUTHORIZATION_RECORD.read_text(encoding="utf-8"))
    checks = {
        "state": record["authorization_state"] == "AUTHORIZED" and record["formal_run_authorized"] is True,
        "scope": record["experiment_id"] == manifest["experiment_id"],
        "timestamp": isinstance(record["authorized_at"], str) and bool(record["authorized_at"]),
        "manifest": record["manifest_sha256"] == sha256(MANIFEST),
        "protocol": record["protocol_sha256"] == sha256(ROOT / manifest["protocol_document"]),
        "runner": record["runner_sha256"] == sha256(Path(__file__)),
        "dataset": record["dataset_id"] == manifest["dataset_id"],
        "cases": record["cases"] == manifest["cases"],
        "x0": record["x0_identity_sha256"] == canonical_hash(manifest["x0_hashes"]),
        "B_ref": record["B_ref_identity_sha256"] == canonical_hash(manifest["B_ref_by_case"]),
        "design": record["beta"] == BETA
        and record["Gamma_levels"] == manifest["Gamma_levels"]
        and record["lambda_levels"] == manifest["lambda_levels"],
        "reuse": record["reuse_plan_sha256"] == sha256(ROOT / manifest["reuse_plan"]),
        "static_audit": record["preauthorization_static_audit_sha256"] == sha256(STATIC_AUDIT),
        "namespace": record["result_namespace"] == manifest["result_root"],
        "solver": record["solver_profile"] == manifest["solver_profile"],
        "certification": record["certification_identity_sha256"] == certification_identity(manifest),
        "timing": record["timing_schema_sha256"] == sha256(ROOT / manifest["result_schema"]),
        "reporting": record["reporting_evaluator_sha256"] == reporting_evaluator_identity(),
        "launcher": record["launcher_sha256"] == sha256(ROOT / "scripts/run_e7_formal.ps1"),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E7_AUTHORIZATION_IDENTITY: {','.join(failed)}")
    return record


def validate_case_identity(case: str, manifest: dict, identity: dict[str, str]) -> None:
    paths = {
        "instance": ROOT / f"data/formal_instances_v2/{case}.json",
        "x0": ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json",
        "calibration": ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json",
    }
    checks = {
        "instance": sha256(paths["instance"]) == identity["instance_hash"] == manifest["instance_hashes"][case],
        "x0": sha256(paths["x0"]) == identity["x0_hash"] == manifest["x0_hashes"][case],
        "calibration": sha256(paths["calibration"]) == identity["calibration_hash"] == manifest["calibration_hashes"][case],
        "mapping": identity["mapping_hash"] == manifest["mapping_sha256"],
        "B_ref": json.loads(paths["calibration"].read_text(encoding="utf-8"))["B_ref"]
        == manifest["B_ref_by_case"][case],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E7_CASE_IDENTITY: {case}: {','.join(failed)}")


def _source_descriptor(path: Path, experiment: str) -> dict:
    return {
        "experiment": experiment,
        "run_id": path.name,
        "directory": path,
        "result": json.loads((path / "result.json").read_text(encoding="utf-8")),
    }


def discover_source_candidates() -> dict[tuple[str, str, str], list[dict]]:
    index: dict[tuple[str, str, str], list[dict]] = {}
    gamma_tokens = {value: token for token, value in GAMMA_BY_TOKEN.items()}
    lambda_tokens = {value: token for token, value in LAMBDA_BY_TOKEN.items()}
    for root, experiment in ((E4_ROOT, "E4"), (E5_ROOT, "E5")):
        for path in sorted(root.glob("*/result.json")):
            source = _source_descriptor(path.parent, experiment)
            result = source["result"]
            gamma_token = gamma_tokens.get(result.get("Gamma"))
            lambda_token = lambda_tokens.get(float(result.get("lambda_R", math.nan)))
            if result.get("case") in CASES and result.get("beta") == BETA and gamma_token and lambda_token:
                index.setdefault((result["case"], gamma_token, lambda_token), []).append(source)
    return index


def expected_reuse_cells_from_source_design() -> set[tuple[str, str]]:
    e4 = json.loads(E4_MANIFEST.read_text(encoding="utf-8"))
    e5 = json.loads(E5_MANIFEST.read_text(encoding="utf-8"))
    gamma_tokens = {value: token for token, value in GAMMA_BY_TOKEN.items()}
    lambda_tokens = {value: token for token, value in LAMBDA_BY_TOKEN.items()}
    cells = set()
    if e4["beta"] == BETA and e4["lambda_R"] in lambda_tokens:
        cells.update((gamma_tokens[gamma], lambda_tokens[e4["lambda_R"]]) for gamma in e4["Gamma_grid"] if gamma in gamma_tokens)
    if e5["beta"] == BETA and e5["Gamma"] in gamma_tokens:
        cells.update((gamma_tokens[e5["Gamma"]], lambda_tokens[item["value"]]) for item in e5["lambda_levels"] if item["value"] in lambda_tokens)
    return cells


def validate_source(condition: Condition, source: dict, manifest: dict, identity: dict[str, str]) -> None:
    directory = source["directory"]
    result = source["result"]
    provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    solution_path = directory / "first_stage_solution.json"
    runner_path = "experiments/run_e4_gamma_local.py" if source["experiment"] == "E4" else "experiments/run_e5_lambda_local.py"
    manifest_path = (
        "experiments/configs/formal/e4_gamma_sensitivity_authorization.json"
        if source["experiment"] == "E4"
        else "experiments/configs/formal/e5_reconfiguration_friction_authorization.json"
    )
    checks = {
        "hashes": provenance["result_sha256"] == sha256(directory / "result.json")
        and provenance["first_stage_solution_sha256"] == sha256(solution_path),
        "historical_runner": provenance["runner_sha256"] == git_file_sha256(provenance["git_commit"], runner_path),
        "historical_manifest": provenance["manifest_sha256"] == git_file_sha256(provenance["git_commit"], manifest_path),
        "condition": result["case"] == condition.case and result["beta"] == BETA
        and result["Gamma"] == condition.gamma and result["lambda_R"] == condition.lambda_r,
        "dataset": result["dataset_id"] == manifest["dataset_id"],
        "budget": result["B"] == result["B_ref"] == manifest["B_ref_by_case"][condition.case],
        "instance": result["instance_hash"] == identity["instance_hash"],
        "x0": result["x0_hash"] == identity["x0_hash"],
        "calibration": result["calibration_hash"] == identity["calibration_hash"],
        "mapping": result["mapping_hash"] == manifest["mapping_sha256"],
        "model": result["model_identity_sha256"] == manifest["model_identity_sha256"]
        == source_model_identity(provenance["git_commit"]),
        "prb": result["prb_identity_sha256"] == manifest["prb_identity_sha256"],
        "solver": result["solver_profile"] == manifest["solver_profile"],
        "certification": result["status"] == "OPTIMAL"
        and result["certification_status"] == "CERTIFIED_PRB_EXACT"
        and result.get("exact_certification_pass", True) is True,
        "accounting": abs(result["objective"] - result["budget_used"] - result["robust_recourse_cost"])
        <= manifest["tolerance_contract"]["objective_certification"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E7_REUSE_IDENTITY: {condition.run_id}:{source['run_id']}:{','.join(failed)}")


def validate_overlap(condition: Condition, sources: list[dict], manifest: dict) -> dict:
    by_experiment = {source["experiment"]: source for source in sources}
    fields = ("B", "B_ref", "objective", "fixed_cost", "inventory_cost", "reconfiguration_cost", "robust_recourse_cost", "budget_used", "RI", "RS", "active_depots")
    checks = {
        "source_set": set(by_experiment) == {"E4", "E5"},
        "condition": condition.gamma_token == "G2" and condition.lambda_token == "L0500",
        "solution_identity": sha256(by_experiment["E4"]["directory"] / "first_stage_solution.json")
        == sha256(by_experiment["E5"]["directory"] / "first_stage_solution.json"),
        "economic_identity": all(
            abs(float(by_experiment["E4"]["result"][field]) - float(by_experiment["E5"]["result"][field]))
            <= manifest["tolerance_contract"]["reporting"] for field in fields
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E7_OVERLAP_IDENTITY:{condition.run_id}:{','.join(failed)}")
    return checks


def build_reuse_plan(manifest: dict | None = None) -> list[dict]:
    manifest = load_manifest() if manifest is None else manifest
    identities = load_identities()
    sources = discover_source_candidates()
    expected = expected_reuse_cells_from_source_design()
    plan = []
    for condition in enumerate_conditions():
        validate_case_identity(condition.case, manifest, identities[condition.case])
        candidates = sources.get((condition.case, condition.gamma_token, condition.lambda_token), [])
        for source in candidates:
            validate_source(condition, source, manifest, identities[condition.case])
        overlap = validate_overlap(condition, candidates, manifest) if len(candidates) == 2 else None
        cell = (condition.gamma_token, condition.lambda_token)
        if cell in expected and not candidates:
            raise RuntimeError(f"BLOCK_E7_MISSING_REUSE:{condition.run_id}")
        if cell not in expected and candidates:
            raise RuntimeError(f"BLOCK_E7_UNPLANNED_REUSE:{condition.run_id}")
        if len(candidates) > 2:
            raise RuntimeError(f"BLOCK_E7_AMBIGUOUS_REUSE:{condition.run_id}")
        selected = next((source for source in candidates if source["experiment"] == "E4"), None)
        if selected is None and candidates:
            selected = candidates[0]
        plan.append({
            "run_id": condition.run_id, "case": condition.case,
            "Gamma_token": condition.gamma_token, "Gamma": condition.gamma,
            "lambda_token": condition.lambda_token, "lambda_R": condition.lambda_r,
            "classification": "REUSE" if selected else "NEW_SOLVE",
            "selected_source_experiment": selected["experiment"] if selected else None,
            "selected_source_run": selected["run_id"] if selected else None,
            "source_candidates": [source["run_id"] for source in candidates],
            "overlap_identity_checks": overlap,
        })
    return plan


def static_feasibility(condition: Condition, manifest: dict) -> dict:
    instance = load_instance(ROOT / f"data/formal_instances_v2/{condition.case}.json")
    x0 = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case}.json").read_text(encoding="utf-8"))["x0"]
    removal_cost = condition.lambda_r * sum(
        instance.inventory_cost[i][j] * x0[i][j]
        for i in range(instance.num_depots) for j in range(instance.num_products)
    )
    budget = manifest["B_ref_by_case"][condition.case]
    return {
        "run_id": condition.run_id,
        "case": condition.case,
        "Gamma": condition.gamma,
        "lambda_R": condition.lambda_r,
        "construction": "y=0,x=0,a_plus=0,a_minus=x0; shortage/service-violation recourse",
        "removal_reconfiguration_cost": removal_cost,
        "B": budget,
        "budget_slack": budget - removal_cost,
        "feasible": removal_cost <= budget + manifest["tolerance_contract"]["budget_feasibility"],
        "optimization_executed": False,
    }


def dry_run() -> dict:
    manifest = load_manifest()
    validate_manifest(manifest)
    validate_authorization_record(manifest)
    plan = build_reuse_plan(manifest)
    new_rows = [row for row in plan if row["classification"] == "NEW_SOLVE"]
    preflight = [
        static_feasibility(Condition(row["case"], row["Gamma_token"], row["lambda_token"]), manifest)
        for row in new_rows
    ]
    output_states = [classify_output_state(
        Condition(row["case"], row["Gamma_token"], row["lambda_token"]), manifest
    ) for row in plan]
    return {
        "status": "E7_AUTHORIZED_DRY_RUN_PASS" if all(row["feasible"] for row in preflight)
        and not any(state["state"] == "PARTIAL" for state in output_states)
        else "E7_FORMAL_RUN_AUTHORIZATION_BLOCKED",
        "total_conditions": len(plan),
        "reusable_conditions": len(plan) - len(new_rows),
        "new_solve_conditions": len(new_rows),
        "reuse_parameter_cells": sorted({f"{row['Gamma_token']}-{row['lambda_token']}" for row in plan if row["classification"] == "REUSE"}),
        "new_parameter_cells": sorted({f"{row['Gamma_token']}-{row['lambda_token']}" for row in new_rows}),
        "G4_L2000_feasible_cases": sum(row["feasible"] for row in preflight if row["Gamma"] == 4 and row["lambda_R"] == 0.2),
        "completed_conditions": sum(state["state"] == "COMPLETED" for state in output_states),
        "absent_conditions": sum(state["state"] == "ABSENT" for state in output_states),
        "partial_conditions": [state["run_id"] for state in output_states if state["state"] == "PARTIAL"],
        "formal_run_authorized": manifest["formal_run_authorized"],
        "optimization_solver_invocations": 0,
        "conditions": plan,
    }


def check_output_target(run_id: str, output_root: Path = RESULT_ROOT) -> None:
    if (output_root / run_id).exists():
        raise FileExistsError(f"refusing to overwrite {run_id}")


def timing_containment_passes(timing: dict[str, float], tolerance: float = 1e-6) -> bool:
    contained = sum(
        value for field, value in timing.items()
        if field != "t_total_runner_wallclock_seconds"
    )
    return timing["t_total_runner_wallclock_seconds"] + tolerance >= contained


def classify_output_state(
    condition: Condition, manifest: dict, output_root: Path = RESULT_ROOT
) -> dict:
    target = output_root / condition.run_id
    temporary = sorted(output_root.glob(f".{condition.run_id}.*.tmp")) if output_root.exists() else []
    if temporary:
        return {"run_id": condition.run_id, "state": "PARTIAL", "reason": "temporary artifact directory exists"}
    if not target.exists():
        return {"run_id": condition.run_id, "state": "ABSENT", "reason": None}
    required = [target / name for name in ("result.json", "first_stage_solution.json", "provenance.json")]
    if not all(path.is_file() for path in required):
        return {"run_id": condition.run_id, "state": "PARTIAL", "reason": "required completion artifacts missing"}
    try:
        result = json.loads(required[0].read_text(encoding="utf-8"))
        provenance = json.loads(required[2].read_text(encoding="utf-8"))
        timing = result["timing"]
        valid = {
            "completion_marker": provenance["completion_status"] == "COMPLETED",
            "run_id": result["run_id"] == provenance["run_id"] == condition.run_id,
            "condition": result["case"] == condition.case and result["Gamma"] == condition.gamma
            and result["lambda_R"] == condition.lambda_r and result["beta"] == BETA,
            "certification": result["status"] == "OPTIMAL"
            and result["certification_status"] == "CERTIFIED_PRB_EXACT"
            and result["exact_certification_pass"] is True,
            "hashes": provenance["result_sha256"] == sha256(required[0])
            and provenance["first_stage_solution_sha256"] == sha256(required[1]),
            "authorization": provenance["authorization_record_sha256"] == sha256(AUTHORIZATION_RECORD),
            "timing_fields": set(timing) == set(manifest["timing_fields"])
            and all(isinstance(value, (int, float)) and value >= 0 for value in timing.values()),
            "timing_containment": timing_containment_passes(timing, manifest["tolerance_contract"]["reporting"]),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return {"run_id": condition.run_id, "state": "PARTIAL", "reason": f"invalid completion artifact: {error}"}
    failed = [name for name, passed in valid.items() if not passed]
    if failed:
        return {"run_id": condition.run_id, "state": "PARTIAL", "reason": f"completion validation failed: {','.join(failed)}"}
    return {"run_id": condition.run_id, "state": "COMPLETED", "reason": None}


def validate_execution_gate(condition: Condition, output_root: Path = RESULT_ROOT) -> tuple[dict, dict[str, str]]:
    manifest = load_manifest()
    validate_manifest(manifest)
    validate_authorization_record(manifest)
    audit = json.loads(STATIC_AUDIT.read_text(encoding="utf-8"))
    if audit["status"] != "E7_PROTOCOL_STATIC_AUDIT_PASS":
        raise RuntimeError("E7 preauthorization static audit failed")
    if condition.run_id not in manifest["planned_run_ids"] or output_root.resolve() != RESULT_ROOT.resolve():
        raise PermissionError("E7 condition or result namespace is outside the frozen protocol")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E7 requires a clean committed worktree")
    check_output_target(condition.run_id, output_root)
    identity = load_identities()[condition.case]
    validate_case_identity(condition.case, manifest, identity)
    return manifest, identity


def _adjustment_metrics(x, x0, tolerance: float) -> tuple[float, int, float]:
    values = [abs(x[i][j] - x0[i][j]) for i in range(len(x)) for j in range(len(x[i]))]
    total = sum(values)
    return total, sum(value > tolerance for value in values), max(values) / total if total else 0.0


def _source_metrics(source: dict) -> dict:
    result = source["result"]
    if source["experiment"] == "E4":
        return {
            "transportation_cost": result["transport_cost"],
            "shortage_cost": result["worst_recourse_shortage_cost"],
            "service_penalty": result["worst_recourse_service_penalty_cost"],
            "total_shortage": result["worst_recourse_total_shortage"],
        }
    return {key: result[key] for key in ("transportation_cost", "shortage_cost", "service_penalty", "total_shortage")}


def build_reused_result(condition: Condition, manifest: dict, identity: dict, source: dict, instance, x0) -> tuple[dict, Path]:
    result = source["result"]
    solution_path = source["directory"] / "first_stage_solution.json"
    artifact = json.loads(solution_path.read_text(encoding="utf-8"))
    x = matrix_from_artifact(artifact, instance, "x")
    adjustment, changed, concentration = _adjustment_metrics(x, x0, manifest["tolerance_contract"]["materiality"])
    y_ids = [item["depot_id"] for item in artifact["y"] if item["value"]]
    positive_ids = [instance.depot_ids[i] for i, row in enumerate(x) if sum(row) > manifest["tolerance_contract"]["materiality"]]
    service = _source_metrics(source)
    canonical = {
        "run_id": condition.run_id, "experiment_id": manifest["experiment_id"], "case": condition.case,
        "beta": BETA, "Gamma_token": condition.gamma_token, "Gamma": condition.gamma,
        "lambda_token": condition.lambda_token, "lambda_R": condition.lambda_r,
        "B": manifest["B_ref_by_case"][condition.case], "B_ref": manifest["B_ref_by_case"][condition.case],
        "dataset_id": manifest["dataset_id"], "instance_hash": identity["instance_hash"],
        "x0_hash": identity["x0_hash"], "calibration_hash": identity["calibration_hash"],
        "mapping_hash": manifest["mapping_sha256"], "model_identity_sha256": manifest["model_identity_sha256"],
        "prb_identity_sha256": manifest["prb_identity_sha256"], "solver_profile": manifest["solver_profile"],
        "reused": True, "reuse_source_run": source["run_id"], "source_reported_runtime_seconds": result["runtime_seconds"],
        "objective": result["objective"], "fixed_cost": result["fixed_cost"], "inventory_cost": result["inventory_cost"],
        "reconfiguration_cost": result["reconfiguration_cost"], "robust_recourse_cost": result["robust_recourse_cost"],
        "budget_used": result["budget_used"], "budget_utilization": result["budget_utilization"],
        "budget_slack": result["budget_slack"], "canonical_total_adjustment": adjustment,
        "RI": adjustment / sum(map(sum, x0)), "RS": result["reconfiguration_cost"] / result["B"],
        "changed_pair_count": changed, "top_adjustment_share": concentration,
        "material_reconfiguration": adjustment / sum(map(sum, x0)) > manifest["tolerance_contract"]["materiality"],
        "active_depots": len(y_ids), "active_depot_ids": y_ids, "positive_inventory_depot_ids": positive_ids,
        "opened_depots": result["opened_depots"], "closed_depots": result["closed_depots"],
        **service, "average_fill_rate": result["average_fill_rate"], "minimum_fill_rate": result["minimum_fill_rate"],
        "iterations": result["iterations"], "cuts": result.get("cuts", result.get("cuts_added")),
        "master_solves": result["master_solves"],
        "subproblem_evaluations": result.get("subproblem_evaluations", result.get("product_subproblem_evaluations")),
        "lower_bound": result.get("lower_bound"), "upper_bound": result.get("upper_bound"),
        "relative_gap": result.get("relative_gap"), "status": "OPTIMAL",
        "certification_status": result["certification_status"], "exact_certification_pass": result.get("exact_certification_pass", True),
        "global_coupling_pass": result.get("global_coupling_pass"),
    }
    return canonical, solution_path


def build_new_result(condition: Condition, manifest: dict, identity: dict, instance, x0, x0_artifact, timing: dict) -> tuple[dict, dict]:
    print(f"[{condition.run_id}] stage=core_prb started", flush=True)
    solved = solve_prb_benders(instance, x0, manifest["B_ref_by_case"][condition.case], condition.gamma, condition.lambda_r)
    timing["t_core_prb_seconds"] = max(0.0, solved.total_runtime - solved.certification_runtime)
    timing["t_exact_certification_seconds"] = solved.certification_runtime
    print(f"[{condition.run_id}] stage=core_prb finished seconds={timing['t_core_prb_seconds']:.6f}", flush=True)
    print(f"[{condition.run_id}] stage=exact_certification finished seconds={timing['t_exact_certification_seconds']:.6f}", flush=True)
    if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
        raise RuntimeError("E7 PRB solve is not exactly certified")
    started = perf_counter()
    print(f"[{condition.run_id}] stage=post_evaluation started", flush=True)
    service, reporting_diagnostic = evaluate_e4_service(instance, solved.solution.x, condition.gamma)
    timing["t_post_evaluation_seconds"] = perf_counter() - started
    print(f"[{condition.run_id}] stage=post_evaluation finished seconds={timing['t_post_evaluation_seconds']:.6f}", flush=True)
    started = perf_counter()
    fixed = sum(instance.fixed_depot_cost[i] * solved.solution.y[i] for i in range(instance.num_depots))
    inventory = sum(instance.inventory_cost[i][j] * solved.solution.x[i][j] for i in range(instance.num_depots) for j in range(instance.num_products))
    reconfiguration = condition.lambda_r * sum(instance.inventory_cost[i][j] * (solved.solution.a_plus[i][j] + solved.solution.a_minus[i][j]) for i in range(instance.num_depots) for j in range(instance.num_products))
    budget = manifest["B_ref_by_case"][condition.case]
    budget_used = fixed + inventory + reconfiguration
    adjustment, changed, concentration = _adjustment_metrics(solved.solution.x, x0, manifest["tolerance_contract"]["materiality"])
    active_ids = [instance.depot_ids[i] for i, value in enumerate(solved.solution.y) if value]
    positive_ids = [instance.depot_ids[i] for i, row in enumerate(solved.solution.x) if sum(row) > manifest["tolerance_contract"]["materiality"]]
    y0 = x0_artifact["y0"]
    result = {
        "run_id": condition.run_id, "experiment_id": manifest["experiment_id"], "case": condition.case,
        "beta": BETA, "Gamma_token": condition.gamma_token, "Gamma": condition.gamma,
        "lambda_token": condition.lambda_token, "lambda_R": condition.lambda_r,
        "B": budget, "B_ref": budget, "dataset_id": manifest["dataset_id"],
        "instance_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"],
        "calibration_hash": identity["calibration_hash"], "mapping_hash": manifest["mapping_sha256"],
        "model_identity_sha256": manifest["model_identity_sha256"], "prb_identity_sha256": manifest["prb_identity_sha256"],
        "solver_profile": manifest["solver_profile"], "reused": False, "reuse_source_run": None,
        "source_reported_runtime_seconds": None, "objective": budget_used + service.robust_recourse_cost,
        "fixed_cost": fixed, "inventory_cost": inventory, "reconfiguration_cost": reconfiguration,
        "robust_recourse_cost": service.robust_recourse_cost, "budget_used": budget_used,
        "budget_utilization": budget_used / budget, "budget_slack": budget - budget_used,
        "canonical_total_adjustment": adjustment, "RI": adjustment / sum(map(sum, x0)),
        "RS": reconfiguration / budget, "changed_pair_count": changed, "top_adjustment_share": concentration,
        "material_reconfiguration": adjustment / sum(map(sum, x0)) > manifest["tolerance_contract"]["materiality"],
        "active_depots": len(active_ids), "active_depot_ids": active_ids, "positive_inventory_depot_ids": positive_ids,
        "opened_depots": [instance.depot_ids[i] for i in range(instance.num_depots) if solved.solution.y[i] and not y0[i]],
        "closed_depots": [instance.depot_ids[i] for i in range(instance.num_depots) if y0[i] and not solved.solution.y[i]],
        "transportation_cost": service.worst_recourse_scenario.transportation_cost,
        "shortage_cost": service.worst_recourse_scenario.shortage_cost,
        "service_penalty": service.worst_recourse_scenario.service_penalty_cost,
        "total_shortage": service.worst_recourse_scenario.total_shortage,
        "average_fill_rate": service.worst_service_scenario.average_fill_rate,
        "minimum_fill_rate": service.worst_service_scenario.minimum_fill_rate,
        "iterations": len(solved.iterations), "cuts": solved.unique_product_cuts,
        "master_solves": solved.master_solve_count, "subproblem_evaluations": solved.product_subproblem_evaluations,
        "lower_bound": solved.final_lower_bound, "upper_bound": solved.final_upper_bound,
        "relative_gap": solved.final_relative_gap, "status": "OPTIMAL",
        "certification_status": "CERTIFIED_PRB_EXACT", "exact_certification_pass": True,
        "global_coupling_pass": solved.global_risk_budget_coupling_pass,
        "reporting_tiebreak_diagnostic": reporting_diagnostic,
    }
    artifact = build_first_stage_solution_artifact(
        instance, x0, solved.solution, case_id=condition.case, mode="E7_PRB",
        identity={"config_hash": sha256(MANIFEST), "data_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"], "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()},
        solver_profile=manifest["solver_profile"],
    )
    timing["t_reporting_seconds"] = perf_counter() - started
    return result, artifact


def write_run(result: dict, first_stage, timing: dict, total_started: float, output_root: Path = RESULT_ROOT) -> None:
    target = output_root / result["run_id"]
    temporary = output_root / f".{result['run_id']}.{uuid4().hex}.tmp"
    temporary.mkdir(parents=True)
    try:
        write_started = perf_counter()
        solution_path = temporary / "first_stage_solution.json"
        if isinstance(first_stage, Path):
            shutil.copy2(first_stage, solution_path)
        else:
            write_first_stage_solution_artifact(solution_path, first_stage)
        timing["t_artifact_write_seconds"] = perf_counter() - write_started
        timing["t_total_runner_wallclock_seconds"] = perf_counter() - total_started
        if not timing_containment_passes(timing):
            raise RuntimeError("E7 timing containment contract failed")
        result["timing"] = timing
        result_path = temporary / "result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        provenance = {
            "run_id": result["run_id"], "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "runner_sha256": sha256(Path(__file__)), "manifest_sha256": sha256(MANIFEST),
            "authorization_record_sha256": sha256(AUTHORIZATION_RECORD),
            "result_sha256": sha256(result_path), "first_stage_solution_sha256": sha256(solution_path),
            "reused": result["reused"], "reuse_source_run": result["reuse_source_run"],
            "timing_semantics": "monotonic stage timers; final provenance serialization and atomic rename excluded",
            "completion_status": "COMPLETED",
        }
        (temporary / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if target.exists():
            raise FileExistsError(f"refusing to overwrite {result['run_id']}")
        os.replace(temporary, target)
        print(f"[{result['run_id']}] stage=artifact_write finished", flush=True)
        print(f"[{result['run_id']}] total_runner_wallclock={timing['t_total_runner_wallclock_seconds']:.6f}", flush=True)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def execute(condition: Condition) -> None:
    total_started = perf_counter()
    print(f"[{condition.run_id}] execution started", flush=True)
    manifest, identity = validate_execution_gate(condition)
    timing = {field: 0.0 for field in manifest["timing_fields"]}
    started = perf_counter()
    instance = load_instance(ROOT / f"data/formal_instances_v2/{condition.case}.json")
    x0_artifact = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case}.json").read_text(encoding="utf-8"))
    x0 = x0_artifact["x0"]
    timing["t_instance_load_seconds"] = perf_counter() - started
    started = perf_counter()
    row = next(item for item in build_reuse_plan(manifest) if item["run_id"] == condition.run_id)
    print(f"[{condition.run_id}] classification={row['classification']}", flush=True)
    source = None
    if row["classification"] == "REUSE":
        source = next(item for item in discover_source_candidates()[(condition.case, condition.gamma_token, condition.lambda_token)] if item["run_id"] == row["selected_source_run"])
    timing["t_reuse_validation_seconds"] = perf_counter() - started
    if source:
        print(f"[{condition.run_id}] timing_provenance=reused_historical; unavailable stages recorded as zero", flush=True)
        started = perf_counter()
        result, artifact = build_reused_result(condition, manifest, identity, source, instance, x0)
        timing["t_reporting_seconds"] = perf_counter() - started
    else:
        result, artifact = build_new_result(condition, manifest, identity, instance, x0, x0_artifact, timing)
    write_run(result, artifact, timing, total_started)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or audit the frozen E7 risk-friction interaction")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--gamma-token")
    parser.add_argument("--lambda-token")
    args = parser.parse_args()
    if args.dry_run:
        if any((args.case, args.gamma_token, args.lambda_token)):
            parser.error("--dry-run enumerates the full grid")
        print(json.dumps(dry_run(), indent=2))
        return
    if not all((args.case, args.gamma_token, args.lambda_token)):
        parser.error("formal execution requires case, Gamma token, and lambda token")
    condition = Condition(args.case, parse_gamma_token(args.gamma_token), parse_lambda_token(args.lambda_token))
    if args.status_only:
        manifest = load_manifest()
        validate_manifest(manifest)
        validate_authorization_record(manifest)
        status = classify_output_state(condition, manifest)
        print(json.dumps(status))
        if status["state"] == "PARTIAL":
            raise SystemExit(2)
        return
    execute(condition)


if __name__ == "__main__":
    main()
