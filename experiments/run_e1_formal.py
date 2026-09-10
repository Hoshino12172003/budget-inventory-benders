from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from robust_inventory_reconfiguration.e1_formal import (
    E1_NEW_RUN_IDS,
    E1_RESULT_FIELDS,
    e1_output_path,
    synthetic_reproducibility_audit,
    validate_e1_authorization,
)
from robust_inventory_reconfiguration.exact_benchmark import solve_exact_benchmark
from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.formal_protocol import (
    RESULT_FIELDS,
    canonical_hash,
    committed_file_sha256,
    file_sha256,
    load_formal_config,
)
from robust_inventory_reconfiguration.instance import InventoryInstance, load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.reconfiguration_model import (
    ReconfigurationSolution,
    reconfiguration_index,
)
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "configs" / "e1_formal_authorization_attempt_002.yaml"
ACCEPTANCE = ROOT / "experiments" / "results" / "formal_acceptance_batch_1" / "attempt_001"
FREEZE = ROOT / "experiments" / "configs" / "formal" / "formal_parameter_freeze.json"
E1_CONFIG = ROOT / "experiments" / "configs" / "formal" / "e1_algorithm_benchmark.yaml"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_x0(case_id: str, instance: InventoryInstance) -> list[list[float]]:
    depot_index = {value: index for index, value in enumerate(instance.depot_ids)}
    product_index = {value: index for index, value in enumerate(instance.product_ids)}
    matrix = [[0.0] * instance.num_products for _ in range(instance.num_depots)]
    seen = set()
    with (ROOT / "artifacts" / f"nominal_baseline_{case_id}.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        for row in csv.DictReader(stream):
            key = (row["depot_id"], row["product_id"])
            if key in seen or key[0] not in depot_index or key[1] not in product_index:
                raise ValueError("x0 identity mapping is invalid")
            seen.add(key)
            matrix[depot_index[key[0]]][product_index[key[1]]] = float(row["x0"])
    if len(seen) != instance.num_depots * instance.num_products:
        raise ValueError("x0 identity mapping is incomplete")
    return matrix


def verify_hash_manifest(directory: Path) -> None:
    hashes = json.loads((directory / "hashes.json").read_text(encoding="utf-8"))
    for relative, expected in hashes.items():
        if file_sha256(directory / relative) != expected:
            raise RuntimeError(f"immutable artifact hash mismatch: {relative}")


def git_blob_hash(commit: str, path: str) -> str:
    content = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)
    return hashlib.sha256(content).hexdigest()


def reuse_identity_audit(e1_config: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    verify_hash_manifest(ACCEPTANCE)
    results = {
        run_id: json.loads((ACCEPTANCE / "runs" / run_id / "result.json").read_text(encoding="utf-8"))
        for run_id in ("A1", "A2")
    }
    provenance = {
        run_id: json.loads((ACCEPTANCE / "runs" / run_id / "provenance.json").read_text(encoding="utf-8"))
        for run_id in ("A1", "A2")
    }
    acceptance_commit = results["A1"]["git_commit"]
    model_paths = (
        "src/robust_inventory_reconfiguration/reconfiguration_model.py",
        "src/robust_inventory_reconfiguration/product_risk_budget_benders.py",
        "src/robust_inventory_reconfiguration/product_risk_subproblem.py",
        "src/robust_inventory_reconfiguration/solver_profile.py",
    )
    checks = {
        "case_id": all(row["case_id"] == "210202" for row in results.values()),
        "beta_and_B": all(row["B"] == 84614.30513135393 for row in results.values()),
        "Gamma": all(row["Gamma"] == 2 for row in results.values()),
        "lambda_R": all(row["lambda_R"] == 0.05 for row in results.values()),
        "source_data": len({row["source_data_hash"] for row in results.values()}) == 1,
        "processed_data": all(
            row["data_hash"] == freeze["evidence"]["formal_instance_sha256"]["210202"]
            for row in results.values()
        ),
        "x0": all(
            row["x0_hash"] == freeze["evidence"]["nominal_baseline_x0_sha256"]["210202"]
            for row in results.values()
        ),
        "calibration_artifact": all(
            row["calibration_artifact_hash"]
            == freeze["evidence"]["lambda_calibration_summary"]["sha256"]
            for row in provenance.values()
        ),
        "formal_config": all(row["config_hash"] == canonical_hash(e1_config) for row in results.values()),
        "mathematical_model": all(
            git_blob_hash(acceptance_commit, path) == git_blob_hash("HEAD", path)
            for path in model_paths
        ),
        "uncertainty_set": git_blob_hash(
            acceptance_commit, "src/robust_inventory_reconfiguration/scenarios.py"
        ) == git_blob_hash("HEAD", "src/robust_inventory_reconfiguration/scenarios.py"),
        "solver_profile": all(
            row["solver_profile"] == FORMAL_SOLVER_PROFILE_ID for row in provenance.values()
        ),
        "certification_contract": results["A1"]["certification_status"] == "CERTIFIED_EXACT"
        and results["A2"]["certification_status"] == "CERTIFIED_PRB_EXACT",
        "result_schema": all(set(row) == set(RESULT_FIELDS) for row in results.values()),
        "objective_consistency": abs(results["A1"]["objective"] - results["A2"]["objective"])
        <= 1e-4,
    }
    return {
        "status": "E1_REUSE_ACCEPTED" if all(checks.values()) else "BLOCK_E1_REUSE_IDENTITY",
        "checks": checks,
        "results": results,
        "provenance": provenance,
    }


def component_values(instance: InventoryInstance, solution: ReconfigurationSolution) -> tuple[float, float]:
    fixed = sum(instance.fixed_depot_cost[i] * solution.y[i] for i in range(instance.num_depots))
    inventory = sum(
        instance.inventory_cost[i][j] * solution.x[i][j]
        for i in range(instance.num_depots)
        for j in range(instance.num_products)
    )
    return fixed, inventory


def empty_row(**values: Any) -> dict[str, Any]:
    row = {field: None for field in E1_RESULT_FIELDS}
    row.update(values)
    return row


def reused_rows(audit: dict[str, Any]) -> list[dict[str, Any]]:
    direct = audit["results"]["A1"]
    prb = audit["results"]["A2"]
    base = {
        "instance_id": "210202", "instance_type": "Renault", "scale": "Renault",
        "I": 15, "R": 12, "J": 8, "uncertain_item_count": 96, "beta": 1.0,
        "B": direct["B"], "Gamma": 2, "lambda_R": 0.05,
        "solver_profile": FORMAL_SOLVER_PROFILE_ID, "seed": direct["random_seed"],
        "instance_hash": direct["data_hash"], "config_hash": direct["config_hash"],
        "first_stage_solution_hash": None, "result_origin": "formal_acceptance_batch_1",
    }
    rows = []
    for run_id, source in (("E1-210202-DIRECT", direct), ("E1-210202-PRB", prb)):
        row = empty_row(
            **base, run_id=run_id, method=source["method"], objective=source["objective"],
            first_stage_cost=source["first_stage_cost"], depot_fixed_cost=source["depot_fixed_cost"],
            inventory_cost=source["inventory_cost"], reconfiguration_cost=source["reconfiguration_cost"],
            recourse_cost=source["recourse_cost"], runtime_seconds=source["runtime_seconds"],
            peak_memory_gb=source["peak_memory_gb"], final_gap=source["optimality_gap"],
            termination_status=source["termination_status"],
            certification_status=source["certification_status"], git_commit=source["git_commit"],
            benders_iterations=source["iterations"], master_solves=source["iterations"],
            unique_product_cuts=source["cuts"], master_runtime_seconds=source["master_runtime_seconds"],
            subproblem_runtime_seconds=source["subproblem_runtime_seconds"],
            global_coupling_runtime_seconds=None,
            final_relative_gap=source["optimality_gap"],
        )
        rows.append(row)
    with (ROOT / "artifacts" / "reconfiguration_correctness_runs.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        exact = next(
            row for row in csv.DictReader(stream)
            if row["case"] == "210202" and row["gamma"] == "2"
            and row["beta"] == "1.0" and row["lambda_r"] == "0.05"
        )
    rows[0].update(
        variable_count=int(exact["variable_count"]),
        constraint_count=int(exact["constraint_count"]),
        integer_variable_count=15,
        continuous_variable_count=int(exact["variable_count"]) - 15,
        uncertainty_representation_size=8 * (1 + 12 + len(list(combinations(range(12), 2)))),
        nonzero_count=int(exact["nonzero_count"]),
    )
    return rows


def new_result_row(
    run: dict[str, Any], instance: InventoryInstance, x0: list[list[float]], solution: ReconfigurationSolution,
    diagnostics: dict[str, Any], identity: dict[str, str], solution_hash: str,
) -> dict[str, Any]:
    fixed, inventory = component_values(instance, solution)
    return empty_row(
        run_id=run["run_id"], instance_id=run["instance_id"], instance_type="Renault",
        scale="Renault", I=instance.num_depots, R=instance.num_regions, J=instance.num_products,
        uncertain_item_count=instance.num_regions * instance.num_products, method=run["method"],
        beta=run["beta"], B=run["B"], Gamma=run["Gamma"], lambda_R=run["lambda_R"],
        objective=solution.objective, first_stage_cost=solution.first_stage_expenditure,
        depot_fixed_cost=fixed, inventory_cost=inventory,
        reconfiguration_cost=solution.reconfiguration_cost, recourse_cost=solution.robust_recourse_cost,
        runtime_seconds=diagnostics["runtime_seconds"], peak_memory_gb=None,
        final_gap=diagnostics["final_gap"], termination_status="OPTIMAL",
        certification_status=diagnostics["certification_status"],
        solver_profile=FORMAL_SOLVER_PROFILE_ID, seed=None, instance_hash=identity["data_hash"],
        config_hash=identity["config_hash"], first_stage_solution_hash=solution_hash,
        git_commit=identity["git_commit"], result_origin="e1_formal_execution",
        benders_iterations=diagnostics.get("iterations"), master_solves=diagnostics.get("master_solves"),
        unique_product_cuts=diagnostics.get("cuts"), active_cuts=None,
        product_subproblem_solves=diagnostics.get("subproblem_solves"),
        master_runtime_seconds=diagnostics.get("master_runtime"),
        subproblem_runtime_seconds=diagnostics.get("subproblem_runtime"),
        global_coupling_runtime_seconds=None, lower_bound=diagnostics.get("lower_bound"),
        upper_bound=diagnostics.get("upper_bound"), final_relative_gap=diagnostics.get("relative_gap"),
        global_coupling_residual=diagnostics.get("coupling_residual"),
        variable_count=diagnostics.get("variable_count"), constraint_count=diagnostics.get("constraint_count"),
        integer_variable_count=diagnostics.get("integer_variable_count"),
        continuous_variable_count=diagnostics.get("continuous_variable_count"),
        uncertainty_representation_size=diagnostics.get("uncertainty_representation_size"),
        node_count=diagnostics.get("node_count"), nonzero_count=diagnostics.get("nonzero_count"),
    )


def planned_synthetic_rows(manifest: dict[str, Any], ladder: dict[str, Any]) -> list[dict[str, Any]]:
    scale_by_id = {scale["id"]: scale for scale in ladder["scales"]}
    rows = []
    for run in manifest["runs"][2:]:
        scale = scale_by_id[run["scale"]]
        rows.append(empty_row(
            run_id=run["run_id"], instance_id=run["instance_id"], instance_type="synthetic",
            scale=run["scale"], I=scale["I"], R=scale["R"], J=scale["J"],
            uncertain_item_count=scale["uncertainty_terms"], method=run["method"], beta=1.0,
            B=None, Gamma=2, lambda_R=0.05, termination_status="NOT_RUN",
            certification_status="BLOCK_E1_SYNTHETIC_REPRODUCIBILITY",
            solver_profile=FORMAL_SOLVER_PROFILE_ID, seed=ladder["seed"],
            result_origin="not_executed_reproducibility_block",
            uncertainty_representation_size=scale["local_patterns_per_product"] * scale["J"],
        ))
    return rows


def main() -> None:
    manifest = load_formal_config(MANIFEST)
    validate_e1_authorization(manifest)
    output = e1_output_path(ROOT, manifest)
    if output.exists():
        raise FileExistsError("configured E1 attempt already exists and cannot be overwritten")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise RuntimeError("E1 execution requires a clean committed worktree")
    for path in sorted((ROOT / "experiments" / "configs" / "formal").glob("e[2-7]*.yaml")):
        if load_formal_config(path)["formal_run_authorized"] is not False:
            raise RuntimeError("E2-E7 authorization changed")

    output.mkdir(parents=True)
    shutil.copyfile(MANIFEST, output / "authorization_manifest.yaml")
    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    e1_config = load_formal_config(E1_CONFIG)
    freeze = load_formal_config(FREEZE)
    reuse = reuse_identity_audit(e1_config, freeze)
    write_json(output / "audits" / "reuse_identity_audit.json", {k: v for k, v in reuse.items() if k not in {"results", "provenance"}})
    if reuse["status"] != "E1_REUSE_ACCEPTED":
        raise RuntimeError("BLOCK_E1_REUSE_IDENTITY")

    rows = reused_rows(reuse)
    completed_new = []
    failures = []
    try:
        instance_path = ROOT / "data" / "formal_instances" / "210628.json"
        x0_path = ROOT / "artifacts" / "nominal_baseline_210628.csv"
        instance = load_instance(instance_path)
        x0 = load_x0("210628", instance)
        identity = {
            "config_hash": canonical_hash(e1_config), "data_hash": file_sha256(instance_path),
            "x0_hash": file_sha256(x0_path), "git_commit": git_commit,
        }
        direct_run, prb_run = manifest["runs"][:2]
        direct = solve_exact_benchmark(instance, x0, direct_run["B"], 2, 0.05)
        if direct.status != "OPTIMAL" or direct.solution is None:
            raise RuntimeError(f"210628 Direct did not certify: {direct.status}")
        direct_artifact_path = output / "runs" / direct_run["run_id"] / "first_stage_solution.json"
        write_first_stage_solution_artifact(
            direct_artifact_path,
            build_first_stage_solution_artifact(
                instance, x0, direct.solution, case_id="210628", mode="direct_exact",
                identity=identity, solver_profile=FORMAL_SOLVER_PROFILE_ID,
            ),
        )
        direct_diagnostics = {
            "runtime_seconds": direct.runtime, "final_gap": direct.mip_gap,
            "certification_status": "CERTIFIED_EXACT", "lower_bound": direct.best_bound,
            "upper_bound": direct.solution.objective, "relative_gap": direct.mip_gap,
            "variable_count": direct.variable_count, "constraint_count": direct.constraint_count,
            "integer_variable_count": instance.num_depots,
            "continuous_variable_count": direct.variable_count - instance.num_depots,
            "uncertainty_representation_size": instance.num_products * sum(
                len(list(combinations(range(instance.num_regions), g))) for g in range(3)
            ),
            "node_count": direct.node_count, "nonzero_count": direct.nonzero_count,
        }
        direct_row = new_result_row(
            direct_run, instance, x0, direct.solution, direct_diagnostics, identity,
            file_sha256(direct_artifact_path),
        )
        write_json(output / "runs" / direct_run["run_id"] / "result.json", direct_row)
        rows.append(direct_row)
        completed_new.append(direct_run["run_id"])

        prb = solve_prb_benders(instance, x0, prb_run["B"], 2, 0.05)
        if prb.status != "OPTIMAL" or not prb.exact_certification_pass:
            raise RuntimeError("210628 PRB did not certify")
        prb_artifact_path = output / "runs" / prb_run["run_id"] / "first_stage_solution.json"
        write_first_stage_solution_artifact(
            prb_artifact_path,
            build_first_stage_solution_artifact(
                instance, x0, prb.solution, case_id="210628", mode="prb_benders",
                identity=identity, solver_profile=FORMAL_SOLVER_PROFILE_ID,
            ),
        )
        prb_diagnostics = {
            "runtime_seconds": prb.total_runtime, "final_gap": prb.final_relative_gap,
            "certification_status": "CERTIFIED_PRB_EXACT", "iterations": len(prb.iterations),
            "master_solves": prb.master_solve_count, "cuts": prb.unique_product_cuts,
            "subproblem_solves": prb.product_subproblem_evaluations,
            "master_runtime": prb.master_runtime, "subproblem_runtime": prb.separation_runtime,
            "lower_bound": prb.final_lower_bound, "upper_bound": prb.final_upper_bound,
            "relative_gap": prb.final_relative_gap,
            "coupling_residual": prb.global_risk_budget_coupling_error,
        }
        prb_row = new_result_row(
            prb_run, instance, x0, prb.solution, prb_diagnostics, identity,
            file_sha256(prb_artifact_path),
        )
        write_json(output / "runs" / prb_run["run_id"] / "result.json", prb_row)
        rows.append(prb_row)
        completed_new.append(prb_run["run_id"])
        difference = abs(direct_row["objective"] - prb_row["objective"])
        if difference > manifest["objective_absolute_tolerance"]:
            raise RuntimeError("E1_BLOCKED_CORRECTNESS")

        ladder = load_formal_config(ROOT / "experiments" / "configs" / "synthetic_scaling_ladder.json")
        synthetic_audit = synthetic_reproducibility_audit(ladder)
        write_json(output / "audits" / "synthetic_reproducibility_gate.json", synthetic_audit)
        rows.extend(planned_synthetic_rows(manifest, ladder))

        consistency = [
            {
                "Instance": "210202", "Direct Obj": rows[0]["objective"], "PRB Obj": rows[1]["objective"],
                "Abs Diff": abs(rows[0]["objective"] - rows[1]["objective"]), "Tolerance": 1e-4,
                "Direct Status": rows[0]["certification_status"], "PRB Status": rows[1]["certification_status"], "PASS": "PASS",
            },
            {
                "Instance": "210628", "Direct Obj": direct_row["objective"], "PRB Obj": prb_row["objective"],
                "Abs Diff": difference, "Tolerance": 1e-4,
                "Direct Status": direct_row["certification_status"], "PRB Status": prb_row["certification_status"], "PASS": "PASS",
            },
        ]
        for scale in ("Small", "Medium", "Renault-like", "Large"):
            consistency.append({
                "Instance": scale, "Direct Obj": None, "PRB Obj": None, "Abs Diff": None,
                "Tolerance": 1e-4, "Direct Status": "NOT_RUN", "PRB Status": "NOT_RUN",
                "PASS": "NOT_COMPARABLE",
            })
        with (output / "table_e1_objective_consistency.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=consistency[0].keys())
            writer.writeheader(); writer.writerows(consistency)
        with (output / "table_e1_algorithm_benchmark.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=E1_RESULT_FIELDS)
            writer.writeheader(); writer.writerows(rows)
        runtime_ratios = {
            "210202": rows[0]["runtime_seconds"] / rows[1]["runtime_seconds"],
            "210628": direct_row["runtime_seconds"] / prb_row["runtime_seconds"],
        }
        summary = {
            "status": synthetic_audit["status"], "reuse_status": reuse["status"],
            "planned_observations": 12, "completed_observations": 4,
            "reused_observations": 2, "new_optimization_solves": len(completed_new),
            "completed_new_run_ids": completed_new,
            "not_executed_authorized_run_ids": list(E1_NEW_RUN_IDS[2:]),
            "unauthorized_runs_executed": 0, "runtime_ratios": runtime_ratios,
            "objective_consistency": {"210202": consistency[0], "210628": consistency[1]},
            "e2_e7_authorization": False, "failures": failures, "retries": 0,
        }
        write_json(output / "e1_summary.json", summary)
        write_json(output / "provenance.json", {
            "attempt_id": manifest["attempt_id"],
            "authorization_manifest_hash": committed_file_sha256(MANIFEST, ROOT),
            "formal_config_hash": canonical_hash(e1_config),
            "formal_parameter_freeze_hash": committed_file_sha256(FREEZE, ROOT),
            "execution_git_commit": git_commit, "solver_profile": FORMAL_SOLVER_PROFILE_ID,
            "solver_version": ".".join(map(str, __import__("gurobipy").gurobi.version())),
            "python_version": platform.python_version(), "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(), "platform": platform.platform(),
        })
    except Exception as exc:
        failures.append(str(exc))
        write_json(output / "failure.json", {
            "status": str(exc), "completed_new_run_ids": completed_new,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        })
        raise
    finally:
        hashes = {}
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "hashes.json":
                hashes[path.relative_to(output).as_posix()] = file_sha256(path)
        write_json(output / "hashes.json", hashes)


if __name__ == "__main__":
    main()
