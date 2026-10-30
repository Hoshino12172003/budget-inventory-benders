from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments import run_e6_budget_risk_local as e6_v1


EXPERIMENT_ID = "E6_BUDGET_RISK_5X5_V1"
MANIFEST = ROOT / "artifacts/e6_budget_risk_5x5_authorization.json"
RESULT_ROOT = ROOT / "experiments/results/e6_budget_risk_5x5_v1"
IDENTITY_TABLE = ROOT / "table_empirical_8case_identity.csv"
E3_ROOT = ROOT / "experiments/results/e3_budget_sensitivity_v1"
E4_ROOT = ROOT / "experiments/results/e4_gamma_sensitivity_v1"
E6_ROOT = ROOT / "experiments/results/e6_budget_risk_interaction_v1"
CASES = e6_v1.CASES
BETA_BY_TOKEN = {
    "B080": Decimal("0.80"),
    "B090": Decimal("0.90"),
    "B100": Decimal("1.00"),
    "B110": Decimal("1.10"),
    "B120": Decimal("1.20"),
}
GAMMA_BY_TOKEN = {f"G{value}": value for value in range(5)}
LAMBDA_R = e6_v1.LAMBDA_R


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
        return f"E6-5X5-{self.case}-{self.beta_token}-{self.gamma_token}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enumerate_conditions() -> list[Condition]:
    return [
        Condition(case, beta_token, gamma_token)
        for case in CASES
        for beta_token in BETA_BY_TOKEN
        for gamma_token in GAMMA_BY_TOKEN
    ]


def selected_source(condition: Condition) -> tuple[str, str, Path] | None:
    if condition.beta_token in {"B080", "B100", "B120"} and condition.gamma_token in {
        "G0", "G2", "G4"
    }:
        run_id = f"E6-{condition.case}-{condition.beta_token}-{condition.gamma_token}"
        return "E6", run_id, E6_ROOT / run_id
    if condition.gamma_token == "G2":
        run_id = f"E3-{condition.case}-{condition.beta_token}"
        return "E3", run_id, E3_ROOT / run_id
    if condition.beta_token == "B100":
        run_id = f"E4-{condition.case}-{condition.gamma_token}"
        return "E4", run_id, E4_ROOT / run_id
    return None


def planned_reuse_conditions() -> list[Condition]:
    return [condition for condition in enumerate_conditions() if selected_source(condition)]


def planned_new_solve_conditions() -> list[Condition]:
    return [condition for condition in enumerate_conditions() if selected_source(condition) is None]


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_identities() -> dict[str, dict[str, str]]:
    with IDENTITY_TABLE.open(encoding="utf-8", newline="") as stream:
        return {row["case"]: row for row in csv.DictReader(stream)}


def validate_manifest(manifest: dict) -> None:
    old_manifest = ROOT / "experiments/configs/formal/e6_budget_risk_interaction_authorization.json"
    contract_paths = {
        "E3_manifest_sha256": ROOT / "experiments/configs/formal/e3_budget_sensitivity_authorization.json",
        "E4_manifest_sha256": ROOT / "experiments/configs/formal/e4_gamma_sensitivity_authorization.json",
        "E6_manifest_sha256": old_manifest,
        "E3_final_audit_sha256": ROOT / "artifacts/e3_final_result_audit.json",
        "E4_final_audit_sha256": ROOT / "artifacts/e4_final_result_audit.json",
        "E6_final_audit_sha256": ROOT / "artifacts/e6_final_result_audit.json",
        "historical_source_audit_sha256": ROOT
        / "artifacts/e6_budget_risk_5x5_historical_source_audit.json",
        "historical_source_table_sha256": ROOT
        / "artifacts/e6_budget_risk_5x5_historical_source_audit.csv",
        "E4_derived_per_file_hashes_sha256": ROOT
        / "artifacts/e4_per_file_hashes_for_e6_reuse_audit.csv",
    }
    expected_ids = [condition.run_id for condition in enumerate_conditions()]
    checks = {
        "schema": manifest.get("schema") == "e6_budget_risk_5x5_authorization_v1",
        "experiment": manifest.get("experiment_id") == EXPERIMENT_ID,
        "dataset": manifest.get("dataset_id") == "RENAULT_EMPIRICAL_8CASE_V1",
        "cases": manifest.get("cases") == list(CASES),
        "beta_grid": manifest.get("beta_grid") == [str(value) for value in BETA_BY_TOKEN.values()],
        "Gamma_grid": manifest.get("Gamma_grid") == list(GAMMA_BY_TOKEN.values()),
        "lambda_R": manifest.get("lambda_R") == LAMBDA_R,
        "planned_run_ids": manifest.get("planned_run_ids") == expected_ids,
        "result_root": manifest.get("result_root") == "experiments/results/e6_budget_risk_5x5_v1",
        "old_e6_manifest": manifest.get("source_contracts", {}).get("E6_manifest_sha256")
        == sha256(old_manifest),
        "runner": manifest.get("runner_sha256") == sha256(Path(__file__)),
        "schema_file": manifest.get("result_schema_sha256")
        == sha256(ROOT / "experiments/schemas/e6_budget_risk_5x5_result.schema.json"),
        "aggregation": manifest.get("aggregation_script_sha256")
        == sha256(ROOT / "scripts/summarize_e6_budget_risk_5x5_results.py"),
        "reuse_map": manifest.get("reuse_map_sha256")
        == sha256(ROOT / "artifacts/e6_budget_risk_5x5_reuse_map.csv"),
        "source_contracts": all(
            manifest.get("source_contracts", {}).get(name) == sha256(path)
            for name, path in contract_paths.items()
        ),
        "identity_table": manifest.get("identity_table_sha256") == sha256(IDENTITY_TABLE),
        "authorization_transition": manifest.get("authorization_transition") in ([False], [False, True]),
        "authorization_state": manifest.get("authorization_transition", [None])[-1]
        is manifest.get("formal_run_authorized"),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E6_5X5_MANIFEST_IDENTITY: {','.join(failed)}")


def validate_case_identity(case: str, manifest: dict, identity: dict[str, str]) -> None:
    files = {
        "instance": ROOT / f"data/formal_instances_v2/{case}.json",
        "x0": ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json",
        "calibration": ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json",
    }
    checks = {
        name: sha256(path) == identity[f"{name}_hash"] == manifest[f"{name}_hashes"][case]
        for name, path in files.items()
    }
    checks["mapping"] = identity["mapping_hash"] == manifest["mapping_sha256"]
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E6_5X5_CASE_IDENTITY: {case}: {','.join(failed)}")


def expected_budget(condition: Condition, manifest: dict) -> float:
    return float(condition.beta * Decimal(str(manifest["B_ref_by_case"][condition.case])))


def validate_source(condition: Condition, manifest: dict) -> dict:
    descriptor = selected_source(condition)
    if descriptor is None:
        raise ValueError(f"{condition.run_id} is not a reuse cell")
    experiment, source_run, directory = descriptor
    required = [directory / name for name in ("result.json", "first_stage_solution.json", "provenance.json")]
    if not all(path.is_file() for path in required):
        raise FileNotFoundError(f"BLOCK_E6_5X5_REUSE_SOURCE_UNAVAILABLE: {source_run}")
    result = json.loads(required[0].read_text(encoding="utf-8"))
    solution = json.loads(required[1].read_text(encoding="utf-8"))
    provenance = json.loads(required[2].read_text(encoding="utf-8"))
    with (ROOT / "artifacts/e6_budget_risk_5x5_reuse_map.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        reuse_row = next(
            row for row in csv.DictReader(stream) if row["target_run_id"] == condition.run_id
        )
    identity = load_identities()[condition.case]
    validate_case_identity(condition.case, manifest, identity)
    checks = {
        "run_id": result.get("run_id") == source_run,
        "case": result.get("case") == condition.case == solution.get("case_id"),
        "beta": float(result.get("beta")) == float(condition.beta),
        "Gamma": result.get("Gamma") == condition.gamma,
        "lambda_R": result.get("lambda_R") == LAMBDA_R,
        "dataset": result.get("dataset_id") == manifest["dataset_id"],
        "instance": result.get("instance_hash") == manifest["instance_hashes"][condition.case],
        "x0": result.get("x0_hash") == manifest["x0_hashes"][condition.case],
        "calibration": result.get("calibration_hash") == manifest["calibration_hashes"][condition.case],
        "mapping": result.get("mapping_hash") == manifest["mapping_sha256"],
        "model": result.get("model_identity_sha256") == manifest["model_identity_sha256"],
        "solver": result.get("solver_profile") == manifest["solver_profile"],
        "status": result.get("status") == "OPTIMAL",
        "certification": result.get("certification_status") == "CERTIFIED_PRB_EXACT"
        and result.get("exact_certification_pass", True) is True,
        "result_hash": provenance.get("result_sha256") == sha256(required[0]),
        "solution_hash": provenance.get("first_stage_solution_sha256") == sha256(required[1]),
        "frozen_source_hash": reuse_row["reuse_pass"] == "true"
        and reuse_row["source_hash"] == sha256(required[0]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E6_5X5_REUSE_IDENTITY: {source_run}: {','.join(failed)}")
    return {
        "experiment": experiment,
        "run_id": source_run,
        "directory": directory,
        "result": result,
        "solution": solution,
        "provenance": provenance,
        "checks": checks,
    }


def validate_checkpoint(condition: Condition, directory: Path, manifest: dict) -> None:
    result_path = directory / "result.json"
    solution_path = directory / "first_stage_solution.json"
    provenance_path = directory / "provenance.json"
    if not all(path.is_file() for path in (result_path, solution_path, provenance_path)):
        raise RuntimeError(f"BLOCK_E6_5X5_PARTIAL_CHECKPOINT: {condition.run_id}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    checks = {
        "run_id": result.get("run_id") == condition.run_id == provenance.get("run_id"),
        "manifest": provenance.get("manifest_sha256") == sha256(MANIFEST),
        "runner": provenance.get("runner_sha256") == sha256(Path(__file__)),
        "result": provenance.get("result_sha256") == sha256(result_path),
        "solution": provenance.get("first_stage_solution_sha256") == sha256(solution_path),
        "status": result.get("status") == "OPTIMAL",
        "certification": result.get("certification_status") == "CERTIFIED_PRB_EXACT",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E6_5X5_CHECKPOINT_IDENTITY: {condition.run_id}: {','.join(failed)}")


def validate_execution_gate(manifest: dict) -> None:
    validate_manifest(manifest)
    if manifest["formal_run_authorized"] is not True:
        raise PermissionError("E6_5X5_FORMAL_RUN_NOT_AUTHORIZED")
    if manifest.get("authorization_scope") != [EXPERIMENT_ID]:
        raise PermissionError("E6_5X5_AUTHORIZATION_SCOPE_MISMATCH")
    if manifest.get("source_inventory_ready") is not True:
        raise RuntimeError("BLOCK_E6_5X5_REUSE_SOURCE_INVENTORY")
    runtime_checks = {
        "model": e6_v1.source_model_identity() == manifest["model_identity_sha256"],
        "prb": sha256(e6_v1.PRB_FILE) == manifest["prb_identity_sha256"],
    }
    failed = [name for name, passed in runtime_checks.items() if not passed]
    if failed:
        raise RuntimeError(f"BLOCK_E6_5X5_RUNTIME_IDENTITY: {','.join(failed)}")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E6_5X5 requires a clean committed worktree")
    for condition in planned_reuse_conditions():
        validate_source(condition, manifest)


def canonical_reused_result(condition: Condition, manifest: dict, source: dict) -> tuple[dict, Path]:
    if source["experiment"] == "E6":
        result = dict(source["result"])
    else:
        original = source["result"]
        solution = source["solution"]
        x0_artifact = json.loads(
            (ROOT / f"artifacts/renault_empirical_8case_v1/x0/{condition.case}.json").read_text(
                encoding="utf-8"
            )
        )
        if (
            x0_artifact["depot_ids"] != solution["depot_ids"]
            or x0_artifact["product_ids"] != solution["product_ids"]
        ):
            raise RuntimeError(f"BLOCK_E6_5X5_REUSE_SOLUTION_IDENTITY: {condition.run_id}")
        x0 = x0_artifact["x0"]
        x_lookup = {
            (item["depot_id"], item["product_id"]): item["value"] for item in solution["x"]
        }
        canonical_adjustment = sum(
            abs(x_lookup[(depot, product)] - x0[i][j])
            for i, depot in enumerate(solution["depot_ids"])
            for j, product in enumerate(solution["product_ids"])
        )
        x0_total = sum(map(sum, x0))
        budget = expected_budget(condition, manifest)
        shortage_cost = original["worst_recourse_shortage_cost"]
        service_penalty = original["worst_recourse_service_penalty_cost"]
        transportation = original.get(
            "transport_cost", original["robust_recourse_cost"] - shortage_cost - service_penalty
        )
        active_ids = [item["depot_id"] for item in solution["y"] if item["value"]]
        result = {
            "case": condition.case,
            "beta": float(condition.beta),
            "Gamma": condition.gamma,
            "lambda_R": LAMBDA_R,
            "B": budget,
            "B_ref": manifest["B_ref_by_case"][condition.case],
            "dataset_id": manifest["dataset_id"],
            "instance_hash": manifest["instance_hashes"][condition.case],
            "x0_hash": manifest["x0_hashes"][condition.case],
            "calibration_hash": manifest["calibration_hashes"][condition.case],
            "mapping_hash": manifest["mapping_sha256"],
            "model_identity_sha256": manifest["model_identity_sha256"],
            "prb_identity_sha256": manifest["prb_identity_sha256"],
            "solver_profile": manifest["solver_profile"],
            "objective": original["objective"],
            "fixed_cost": original["fixed_cost"],
            "inventory_cost": original["inventory_cost"],
            "reconfiguration_cost": original["reconfiguration_cost"],
            "robust_recourse_cost": original["robust_recourse_cost"],
            "budget_used": original["budget_used"],
            "budget_utilization": original["budget_used"] / budget,
            "budget_slack": budget - original["budget_used"],
            "budget_binding": abs(budget - original["budget_used"])
            <= manifest["budget_binding_tolerance"],
            "inventory_spending_share": original["inventory_cost"] / budget,
            "reconfiguration_spending_share": original["reconfiguration_cost"] / budget,
            "canonical_total_adjustment": canonical_adjustment,
            "RI": canonical_adjustment / x0_total,
            "RS": original["reconfiguration_cost"] / budget,
            "changed_pair_count": sum(
                abs(x_lookup[(depot, product)] - x0[i][j]) > manifest["materiality_tolerance"]
                for i, depot in enumerate(solution["depot_ids"])
                for j, product in enumerate(solution["product_ids"])
            ),
            "material_reconfiguration": canonical_adjustment / x0_total
            > manifest["materiality_tolerance"],
            "active_depots": len(active_ids),
            "active_depot_ids": active_ids,
            "opened_depots": original["opened_depots"],
            "closed_depots": original["closed_depots"],
            "shortage_cost": shortage_cost,
            "transportation_cost": transportation,
            "service_penalty": service_penalty,
            "total_shortage": original["worst_recourse_total_shortage"],
            "minimum_fill_rate": original["minimum_fill_rate"],
            "average_fill_rate": original["average_fill_rate"],
            "runtime_seconds": original["runtime_seconds"],
            "iterations": original["iterations"],
            "master_solves": original["master_solves"],
            "subproblem_evaluations": original["product_subproblem_evaluations"],
            "cuts": original["cuts_added"],
            "lower_bound": original.get("lower_bound"),
            "upper_bound": original.get("upper_bound"),
            "relative_gap": original.get("relative_gap"),
            "status": "OPTIMAL",
            "certification_status": original["certification_status"],
            "exact_certification_pass": original.get("exact_certification_pass", True),
            "global_coupling_pass": original.get("global_coupling_pass"),
            "reporting_tiebreak_diagnostic": original.get("reporting_tiebreak_diagnostic"),
        }
    result.update(
        {
            "run_id": condition.run_id,
            "experiment_id": EXPERIMENT_ID,
            "beta_token": condition.beta_token,
            "Gamma_token": condition.gamma_token,
            "reused": True,
            "reuse_source_experiment": source["experiment"],
            "reuse_source_run": source["run_id"],
            "reuse_source_result_sha256": sha256(source["directory"] / "result.json"),
        }
    )
    return result, source["directory"] / "first_stage_solution.json"


def solve_new_result(condition: Condition, manifest: dict, identity: dict[str, str]):
    # This is the unchanged E6 mathematical path with only the expanded parameter tokens.
    result, artifact = e6_v1.solve_new_result(condition, manifest, identity)
    result.update(
        {
            "run_id": condition.run_id,
            "experiment_id": EXPERIMENT_ID,
            "beta_token": condition.beta_token,
            "Gamma_token": condition.gamma_token,
            "reused": False,
            "reuse_source_experiment": None,
            "reuse_source_run": None,
            "reuse_source_result_sha256": None,
        }
    )
    artifact["config_hash"] = sha256(MANIFEST)
    payload = {key: value for key, value in artifact.items() if key != "solution_payload_sha256"}
    artifact["solution_payload_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    return result, artifact


def write_run(result: dict, first_stage, manifest: dict) -> None:
    target = RESULT_ROOT / result["run_id"]
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {result['run_id']}")
    temporary = RESULT_ROOT / f".{result['run_id']}.{uuid4().hex}.tmp"
    temporary.mkdir(parents=True)
    try:
        result_path = temporary / "result.json"
        solution_path = temporary / "first_stage_solution.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if isinstance(first_stage, Path):
            shutil.copy2(first_stage, solution_path)
        else:
            e6_v1.write_first_stage_solution_artifact(solution_path, first_stage)
        provenance = {
            "run_id": result["run_id"],
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "runner_sha256": sha256(Path(__file__)),
            "manifest_sha256": sha256(MANIFEST),
            "result_sha256": sha256(result_path),
            "first_stage_solution_sha256": sha256(solution_path),
            "reused": result["reused"],
            "reuse_source_run": result["reuse_source_run"],
            "reuse_source_result_sha256": result["reuse_source_result_sha256"],
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


def run_condition(condition: Condition, manifest: dict) -> str:
    target = RESULT_ROOT / condition.run_id
    if target.exists():
        validate_checkpoint(condition, target, manifest)
        return "CHECKPOINT_VALID_SKIP"
    identity = load_identities()[condition.case]
    validate_case_identity(condition.case, manifest, identity)
    source_descriptor = selected_source(condition)
    if source_descriptor:
        result, first_stage = canonical_reused_result(
            condition, manifest, validate_source(condition, manifest)
        )
        status = "REUSE_MATERIALIZED"
    else:
        result, first_stage = solve_new_result(condition, manifest, identity)
        status = "NEW_SOLVE_COMPLETED"
    write_run(result, first_stage, manifest)
    return status


def audit_only() -> dict:
    manifest = load_manifest()
    validate_manifest(manifest)
    verified_reuse = sum(
        validate_source(condition, manifest)["checks"]["certification"]
        for condition in planned_reuse_conditions()
    )
    return {
        "status": "E6_5X5_PREPARATION_ONLY",
        "parameter_combinations": len(BETA_BY_TOKEN) * len(GAMMA_BY_TOKEN),
        "case_level_cells": len(enumerate_conditions()),
        "planned_reuse_cells": len(planned_reuse_conditions()),
        "verified_reuse_cells": verified_reuse,
        "planned_new_solve_cells": len(planned_new_solve_conditions()),
        "formal_run_authorized": manifest["formal_run_authorized"],
        "optimization_solver_invocations": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="E6 5x5 budget-risk extension")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--beta-token", choices=tuple(BETA_BY_TOKEN))
    parser.add_argument("--gamma-token", choices=tuple(GAMMA_BY_TOKEN))
    args = parser.parse_args()
    if args.audit_only:
        print(json.dumps(audit_only(), indent=2))
        return
    manifest = load_manifest()
    validate_execution_gate(manifest)
    if args.run_all:
        if any((args.case, args.beta_token, args.gamma_token)):
            parser.error("--run-all takes no cell arguments")
        for condition in enumerate_conditions():
            print(condition.run_id, run_condition(condition, manifest), flush=True)
        return
    if not all((args.case, args.beta_token, args.gamma_token)):
        parser.error("provide --run-all or all of --case, --beta-token, --gamma-token")
    condition = Condition(args.case, args.beta_token, args.gamma_token)
    print(condition.run_id, run_condition(condition, manifest))


if __name__ == "__main__":
    main()
