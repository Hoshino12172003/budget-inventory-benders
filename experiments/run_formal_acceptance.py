from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from robust_inventory_reconfiguration.exact_benchmark import _extract_solution
from robust_inventory_reconfiguration.formal_acceptance import (
    AUTHORIZED_RUN_IDS,
    acceptance_output_path,
    validate_acceptance_manifest,
    validate_formal_result_shape,
)
from robust_inventory_reconfiguration.formal_protocol import (
    RESULT_FIELDS,
    RunIdentity,
    canonical_hash,
    committed_file_sha256,
    file_sha256,
    load_formal_config,
    validate_resume_identity,
)
from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.instance import InventoryInstance, load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.reconfiguration_model import (
    ReconfigurationSolution,
    build_exact_reconfiguration_model,
    reconfiguration_index,
)
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "configs" / "formal_acceptance_batch_1.yaml"
OBJECTIVE_TOLERANCE = 1e-4


class AcceptanceStop(RuntimeError):
    pass


def load_x0(case_id: str, instance: InventoryInstance) -> list[list[float]]:
    depot_index = {value: index for index, value in enumerate(instance.depot_ids)}
    product_index = {value: index for index, value in enumerate(instance.product_ids)}
    x0 = [[0.0] * instance.num_products for _ in range(instance.num_depots)]
    seen: set[tuple[str, str]] = set()
    path = ROOT / "artifacts" / f"nominal_baseline_{case_id}.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["depot_id"], row["product_id"])
            if key in seen or key[0] not in depot_index or key[1] not in product_index:
                raise AcceptanceStop("x0 identity mapping is invalid")
            seen.add(key)
            x0[depot_index[key[0]]][product_index[key[1]]] = float(row["x0"])
    if len(seen) != instance.num_depots * instance.num_products:
        raise AcceptanceStop("x0 identity mapping is incomplete")
    return x0


def solve_direct(
    instance: InventoryInstance,
    x0: list[list[float]],
    run: dict[str, Any],
) -> tuple[ReconfigurationSolution, dict[str, Any]]:
    from gurobipy import GRB

    model, variables = build_exact_reconfiguration_model(
        instance, x0, run["B"], run["Gamma"], run["lambda_R"]
    )
    if run["fix_x_to_x0"]:
        for i in range(instance.num_depots):
            for j in range(instance.num_products):
                model.addConstr(variables["x"][i, j] == x0[i][j], name=f"acceptance_x0[{i},{j}]")
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise AcceptanceStop(f"{run['acceptance_run_id']} Direct status {model.Status}")
    solution = _extract_solution(instance, x0, run["lambda_R"], True, model, variables)
    return solution, {
        "runtime": float(model.Runtime),
        "optimality_gap": float(model.MIPGap),
        "certification_status": "CERTIFIED_EXACT",
    }


def solve_prb(
    instance: InventoryInstance,
    x0: list[list[float]],
    run: dict[str, Any],
) -> tuple[ReconfigurationSolution, dict[str, Any]]:
    result = solve_prb_benders(
        instance, x0, run["B"], run["Gamma"], run["lambda_R"]
    )
    if result.status != "OPTIMAL" or not result.exact_certification_pass:
        raise AcceptanceStop("A2 PRB solution is not exactly certified")
    if not result.global_risk_budget_coupling_pass:
        raise AcceptanceStop("A2 global risk-budget coupling failed")
    return result.solution, {
        "runtime": result.total_runtime,
        "master_runtime": result.master_runtime,
        "subproblem_runtime": result.separation_runtime,
        "certification_runtime": result.certification_runtime,
        "iterations": result.master_solve_count,
        "cuts": result.unique_product_cuts,
        "optimality_gap": result.final_relative_gap,
        "certification_status": "CERTIFIED_PRB_EXACT",
    }


def component_values(
    instance: InventoryInstance, solution: ReconfigurationSolution
) -> tuple[float, float]:
    fixed = sum(
        instance.fixed_depot_cost[i] * solution.y[i]
        for i in range(instance.num_depots)
    )
    inventory = sum(
        instance.inventory_cost[i][j] * solution.x[i][j]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    return fixed, inventory


def result_row(
    run: dict[str, Any],
    instance: InventoryInstance,
    x0: list[list[float]],
    solution: ReconfigurationSolution,
    diagnostics: dict[str, Any],
    identity: RunIdentity,
    solver_version: str,
    service: Any | None,
) -> dict[str, Any]:
    fixed, inventory = component_values(instance, solution)
    ri, represented_ri = reconfiguration_index(
        solution.x, x0, solution.a_plus, solution.a_minus
    )
    if abs(ri - represented_ri) > 1e-6:
        raise AcceptanceStop(f"{run['acceptance_run_id']} RI identity failed")
    row = {
        "experiment_id": run["experiment_id"],
        "case_id": run["case_id"],
        "method": run["method"],
        "B": run["B"],
        "Gamma": run["Gamma"],
        "lambda_R": run["lambda_R"],
        "objective": solution.objective,
        "first_stage_cost": solution.first_stage_expenditure,
        "inventory_cost": inventory,
        "depot_fixed_cost": fixed,
        "reconfiguration_cost": solution.reconfiguration_cost,
        "recourse_cost": solution.robust_recourse_cost,
        "RI": ri,
        "RS": solution.reconfiguration_cost / run["B"],
        "total_inventory": sum(map(sum, solution.x)),
        "active_depots": sum(solution.y),
        "fr_min_robust": service.minimum_fill_rate if service else None,
        "average_fill_rate_in_worst_service_scenario": service.average_fill_rate if service else None,
        "worst_region": service.worst_region_id if service else None,
        "worst_scenario": json.dumps(service.worst_scenario) if service else None,
        "total_shortage_in_worst_service_scenario": service.total_shortage if service else None,
        "service_penalty_cost": None,
        "runtime_seconds": diagnostics["runtime"],
        "master_runtime_seconds": diagnostics.get("master_runtime"),
        "subproblem_runtime_seconds": diagnostics.get("subproblem_runtime"),
        "certification_runtime_seconds": diagnostics.get("certification_runtime"),
        "iterations": diagnostics.get("iterations"),
        "cuts": diagnostics.get("cuts"),
        "peak_memory_gb": None,
        "optimality_gap": diagnostics["optimality_gap"],
        "termination_status": "OPTIMAL",
        "certification_status": diagnostics["certification_status"],
        "config_hash": identity.config_hash,
        "source_data_hash": identity.source_data_hash,
        "data_hash": identity.data_hash,
        "parameter_hash": identity.parameter_hash,
        "x0_hash": identity.x0_hash,
        "git_commit": identity.git_commit,
        "solver_version": solver_version,
        "python_version": platform.python_version(),
        "random_seed": 20260907,
    }
    validate_formal_result_shape(row, RESULT_FIELDS)
    if abs(row["objective"] - row["first_stage_cost"] - row["recourse_cost"]) > OBJECTIVE_TOLERANCE:
        raise AcceptanceStop(f"{run['acceptance_run_id']} objective accounting failed")
    if service and abs(service.robust_recourse_cost - row["recourse_cost"]) > OBJECTIVE_TOLERANCE:
        raise AcceptanceStop(f"{run['acceptance_run_id']} service recourse mismatch")
    return row


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    manifest = load_formal_config(MANIFEST)
    validate_acceptance_manifest(manifest)
    output = acceptance_output_path(ROOT, manifest)
    if output.exists():
        raise FileExistsError("acceptance attempt already exists; results cannot be overwritten")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise RuntimeError("acceptance execution requires a clean committed worktree")
    for config_path in sorted((ROOT / "experiments" / "configs" / "formal").glob("e*.yaml")):
        if load_formal_config(config_path)["formal_run_authorized"] is not False:
            raise AcceptanceStop("full E1-E7 authorization changed")

    output.mkdir(parents=True)
    shutil.copyfile(MANIFEST, output / "authorization_manifest.yaml")
    manifest_hash = committed_file_sha256(MANIFEST, ROOT)
    git_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    instance_path = ROOT / "data" / "formal_instances" / "210202.json"
    x0_path = ROOT / "artifacts" / "nominal_baseline_210202.csv"
    freeze_path = ROOT / "experiments" / "configs" / "formal" / "formal_parameter_freeze.json"
    source_hash = json.loads(
        (ROOT / "artifacts" / "renault_x0_compatibility_summary.json").read_text(
            encoding="utf-8"
        )
    )["source"]["official_archive_sha256"]
    instance = load_instance(instance_path)
    x0 = load_x0("210202", instance)
    solver_version = ".".join(map(str, __import__("gurobipy").gurobi.version()))
    formal_configs = {
        experiment: load_formal_config(
            ROOT / "experiments" / "configs" / "formal" / filename
        )
        for experiment, filename in {
            "E1": "e1_algorithm_benchmark.yaml",
            "E2": "e2_reconfiguration_value.yaml",
        }.items()
    }
    rows: list[dict[str, Any]] = []
    solutions: dict[str, ReconfigurationSolution] = {}
    run_provenance: dict[str, Any] = {}

    try:
        for run in manifest["runs"]:
            run_id = run["acceptance_run_id"]
            if run_id not in AUTHORIZED_RUN_IDS:
                raise AcceptanceStop(f"unauthorized run id {run_id}")
            if run["solver_profile_id"] != FORMAL_SOLVER_PROFILE_ID:
                raise AcceptanceStop(f"{run_id} solver profile mismatch")
            config = formal_configs[run["experiment_id"]]
            identity = RunIdentity(
                config_hash=canonical_hash(config),
                source_data_hash=source_hash,
                data_hash=file_sha256(instance_path),
                parameter_hash=committed_file_sha256(freeze_path, ROOT),
                x0_hash=file_sha256(x0_path),
                git_commit=git_revision,
            )
            if run_id == "A2":
                solution, diagnostics = solve_prb(instance, x0, run)
            else:
                solution, diagnostics = solve_direct(instance, x0, run)
            service = (
                evaluate_robust_service(instance, solution.x, run["Gamma"])
                if run_id in {"A3", "A4", "A5"}
                else None
            )
            row = result_row(
                run, instance, x0, solution, diagnostics, identity, solver_version, service
            )
            timestamp = datetime.now(timezone.utc).isoformat()
            provenance = {
                "acceptance_run_id": run_id,
                "experiment_id": run["experiment_id"],
                "case_id": run["case_id"],
                "method": run["method"],
                "source_data_hash": identity.source_data_hash,
                "processed_data_hash": identity.data_hash,
                "x0_hash": identity.x0_hash,
                "calibration_artifact_hash": "7e727f89379da5fdffc63a7ac9fce711cac9814a948b8f5e1921c91d16920e94",
                "formal_config_hash": identity.config_hash,
                "authorization_manifest_hash": manifest_hash,
                "parameter_freeze_hash": identity.parameter_hash,
                "git_commit": git_revision,
                "solver_profile": FORMAL_SOLVER_PROFILE_ID,
                "solver_version": solver_version,
                "python_version": platform.python_version(),
                "timestamp_utc": timestamp,
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "B": run["B"],
                "Gamma": run["Gamma"],
                "lambda_R": run["lambda_R"],
            }
            write_json(output / "runs" / run_id / "result.json", row)
            write_json(output / "runs" / run_id / "provenance.json", provenance)
            write_first_stage_solution_artifact(
                output / "runs" / run_id / "first_stage_solution.json",
                build_first_stage_solution_artifact(
                    instance,
                    x0,
                    solution,
                    case_id=run["case_id"],
                    mode=run["method"],
                    identity=identity.__dict__,
                    solver_profile=FORMAL_SOLVER_PROFILE_ID,
                ),
            )
            (output / "logs").mkdir(exist_ok=True)
            (output / "logs" / f"{run_id}.log").write_text(
                f"{timestamp} {run_id} OPTIMAL CERTIFIED\n", encoding="utf-8"
            )
            rows.append({"acceptance_run_id": run_id, **row})
            solutions[run_id] = solution
            run_provenance[run_id] = provenance

            if run_id == "A2":
                direct = rows[0]
                difference = abs(direct["objective"] - row["objective"])
                first_stage_difference = abs(
                    direct["first_stage_cost"] - row["first_stage_cost"]
                )
                recourse_difference = abs(direct["recourse_cost"] - row["recourse_cost"])
                if max(difference, first_stage_difference, recourse_difference) > OBJECTIVE_TOLERANCE:
                    raise AcceptanceStop("BLOCK_FORMULATION_OR_CERTIFICATION_MISMATCH")
            if run_id == "A3":
                max_x_difference = max(
                    abs(solution.x[i][j] - x0[i][j])
                    for i in range(instance.num_depots)
                    for j in range(instance.num_products)
                )
                if max_x_difference > manifest["semantic_tolerance"] or row["RI"] > manifest["semantic_tolerance"]:
                    raise AcceptanceStop("existing-system x=x0 semantic check failed")
            if run_id == "A4" and run["Gamma"] != 0:
                raise AcceptanceStop("nominal reconfiguration Gamma propagation failed")
            if run_id == "A5" and run["Gamma"] != 2:
                raise AcceptanceStop("robust reconfiguration Gamma propagation failed")

        direct, prb = rows[0], rows[1]
        direct_prb = {
            "status": "PASS",
            "objective_absolute_difference": abs(direct["objective"] - prb["objective"]),
            "first_stage_absolute_difference": abs(
                direct["first_stage_cost"] - prb["first_stage_cost"]
            ),
            "recourse_absolute_difference": abs(
                direct["recourse_cost"] - prb["recourse_cost"]
            ),
            "maximum_x_absolute_difference": max(
                abs(solutions["A1"].x[i][j] - solutions["A2"].x[i][j])
                for i in range(instance.num_depots)
                for j in range(instance.num_products)
            ),
            "tolerance": OBJECTIVE_TOLERANCE,
        }
        existing_max_x = max(
            abs(solutions["A3"].x[i][j] - x0[i][j])
            for i in range(instance.num_depots)
            for j in range(instance.num_products)
        )
        semantics = {
            "status": "PASS",
            "A3_existing": {"x_equals_x0": existing_max_x <= 1e-6, "maximum_x_difference": existing_max_x, "RI": rows[2]["RI"]},
            "A4_nominal": {"reconfiguration_allowed": True, "Gamma": rows[3]["Gamma"], "uncertainty_budget_active": False},
            "A5_robust": {"reconfiguration_allowed": True, "Gamma": rows[4]["Gamma"], "robust_recourse_active": True, "certified": True},
        }
        checkpoint = RunIdentity(
            config_hash=rows[1]["config_hash"],
            source_data_hash=rows[1]["source_data_hash"],
            data_hash=rows[1]["data_hash"],
            parameter_hash=rows[1]["parameter_hash"],
            x0_hash=rows[1]["x0_hash"],
            git_commit=rows[1]["git_commit"],
        )
        checkpoint_path = output / "diagnostics" / "A2_checkpoint_identity.json"
        write_json(checkpoint_path, checkpoint.__dict__)
        reloaded_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        validate_resume_identity(reloaded_checkpoint, checkpoint)
        checkpoint_audit = {
            "status": "PASS",
            "checkpoint_identity_valid": True,
            "restart_identity_valid": True,
            "config_hash_valid": reloaded_checkpoint["config_hash"] == rows[1]["config_hash"],
            "case_hash_valid": reloaded_checkpoint["data_hash"] == rows[1]["data_hash"],
        }
        write_json(output / "diagnostics" / "direct_prb_comparison.json", direct_prb)
        write_json(output / "diagnostics" / "e2_semantics.json", semantics)
        write_json(output / "diagnostics" / "checkpoint_resume_audit.json", checkpoint_audit)
        with (output / "consolidated_acceptance.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("acceptance_run_id", *RESULT_FIELDS))
            writer.writeheader()
            writer.writerows(rows)
        write_json(
            output / "provenance.json",
            {
                "batch_id": manifest["batch_id"],
                "authorization_manifest_hash": manifest_hash,
                "execution_git_commit": git_revision,
                "runs": run_provenance,
            },
        )
        write_json(
            output / "acceptance_summary.json",
            {
                "status": "FORMAL_ACCEPTANCE_PASS",
                "run_count": len(rows),
                "authorized_run_ids": list(AUTHORIZED_RUN_IDS),
                "direct_prb_consistency": direct_prb,
                "e2_semantics": semantics,
                "checkpoint_resume": checkpoint_audit,
                "schema_audit": "PASS",
                "full_e1_e7_authorization": False,
                "failures": [],
                "retries": 0,
            },
        )
    except Exception as exc:
        write_json(
            output / "failure.json",
            {
                "status": "ACCEPTANCE_BLOCKED",
                "reason": str(exc),
                "completed_run_count": len(rows),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise
    finally:
        hashes = {}
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "hashes.json":
                hashes[path.relative_to(output).as_posix()] = file_sha256(path)
        write_json(output / "hashes.json", hashes)


if __name__ == "__main__":
    main()
