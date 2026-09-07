from __future__ import annotations

import csv
import hashlib
import json
import platform
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from robust_inventory_reconfiguration.exact_benchmark import _extract_solution
from robust_inventory_reconfiguration.first_stage_solution import (
    build_first_stage_solution_artifact,
    load_first_stage_solution_artifact,
    matrix_from_artifact,
    write_first_stage_solution_artifact,
)
from robust_inventory_reconfiguration.formal_protocol import (
    canonical_hash,
    committed_file_sha256,
    file_sha256,
    load_formal_config,
)
from robust_inventory_reconfiguration.formal_recovery import (
    RECOVERY_RUN_IDS,
    recovery_output_path,
    validate_recovery_manifest,
)
from robust_inventory_reconfiguration.instance import InventoryInstance, load_instance
from robust_inventory_reconfiguration.reconfiguration_model import (
    build_exact_reconfiguration_model,
)
from robust_inventory_reconfiguration.robust_service import (
    ScenarioServiceResult,
    evaluate_robust_service_detailed,
)
from robust_inventory_reconfiguration.scenarios import scenario_count
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "configs" / "formal_acceptance_recovery_attempt_002.yaml"
ORIGINAL_ATTEMPT = ROOT / "experiments" / "results" / "formal_acceptance_batch_1" / "attempt_001"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_x0(case_id: str, instance: InventoryInstance) -> list[list[float]]:
    depot_index = {value: index for index, value in enumerate(instance.depot_ids)}
    product_index = {value: index for index, value in enumerate(instance.product_ids)}
    x0 = [[0.0] * instance.num_products for _ in range(instance.num_depots)]
    seen = set()
    with (ROOT / "artifacts" / f"nominal_baseline_{case_id}.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        for row in csv.DictReader(stream):
            key = (row["depot_id"], row["product_id"])
            if key in seen or key[0] not in depot_index or key[1] not in product_index:
                raise ValueError("x0 identity mapping is invalid")
            seen.add(key)
            x0[depot_index[key[0]]][product_index[key[1]]] = float(row["x0"])
    if len(seen) != instance.num_depots * instance.num_products:
        raise ValueError("x0 identity mapping is incomplete")
    return x0


def verify_original_attempt() -> str:
    recorded = json.loads((ORIGINAL_ATTEMPT / "hashes.json").read_text(encoding="utf-8"))
    for relative, expected in recorded.items():
        if file_sha256(ORIGINAL_ATTEMPT / relative) != expected:
            raise RuntimeError(f"attempt_001 changed: {relative}")
    digest = hashlib.sha256()
    for relative, expected in sorted(recorded.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(expected.encode("ascii"))
    return digest.hexdigest()


def solve_recovery(
    instance: InventoryInstance,
    x0: list[list[float]],
    run: dict[str, Any],
):
    from gurobipy import GRB

    model, variables = build_exact_reconfiguration_model(
        instance, x0, run["B"], run["Gamma"], run["lambda_R"]
    )
    if run["fix_x_to_x0"]:
        for i in range(instance.num_depots):
            for j in range(instance.num_products):
                model.addConstr(variables["x"][i, j] == x0[i][j])
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"{run['acceptance_run_id']} recovery status {model.Status}")
    return _extract_solution(instance, x0, run["lambda_R"], True, model, variables), {
        "runtime_seconds": float(model.Runtime),
        "optimality_gap": float(model.MIPGap),
    }


def scenario_row(result: ScenarioServiceResult) -> dict[str, Any]:
    return {
        "shock_set": json.dumps(result.shock_set),
        "recourse_cost": result.recourse_cost,
        "transportation_cost": result.transportation_cost,
        "shortage_cost": result.shortage_cost,
        "soft_service_penalty": result.service_penalty_cost,
        "total_shortage": result.total_shortage,
        "FR_min": result.minimum_fill_rate,
        "avg_fill": result.average_fill_rate,
        "worst_region": result.worst_region_id,
    }


def main() -> None:
    manifest = load_formal_config(MANIFEST)
    validate_recovery_manifest(manifest)
    output = recovery_output_path(ROOT, manifest)
    if output.exists():
        raise FileExistsError("recovery_attempt_002 already exists and cannot be overwritten")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise RuntimeError("recovery execution requires a clean committed worktree")
    for path in sorted((ROOT / "experiments" / "configs" / "formal").glob("e*.yaml")):
        if load_formal_config(path)["formal_run_authorized"] is not False:
            raise RuntimeError("a full formal experiment became authorized")

    original_tree_hash = verify_original_attempt()
    output.mkdir(parents=True)
    shutil.copyfile(MANIFEST, output / "authorization_manifest.yaml")
    git_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    instance_path = ROOT / "data" / "formal_instances" / "210202.json"
    x0_path = ROOT / "artifacts" / "nominal_baseline_210202.csv"
    instance = load_instance(instance_path)
    x0 = load_x0("210202", instance)
    e2_config = load_formal_config(
        ROOT / "experiments" / "configs" / "formal" / "e2_reconfiguration_value.yaml"
    )
    identity = {
        "config_hash": canonical_hash(e2_config),
        "data_hash": file_sha256(instance_path),
        "x0_hash": file_sha256(x0_path),
        "git_commit": git_commit,
    }
    manifest_hash = committed_file_sha256(MANIFEST, ROOT)
    solver_version = ".".join(map(str, __import__("gurobipy").gurobi.version()))
    recovery_rows = []
    completed = []

    try:
        for run in manifest["runs"]:
            run_id = run["acceptance_run_id"]
            if run_id not in RECOVERY_RUN_IDS:
                raise RuntimeError(f"unauthorized recovery run {run_id}")
            solution, diagnostics = solve_recovery(instance, x0, run)
            difference = abs(solution.objective - run["original_objective"])
            if difference > manifest["objective_absolute_tolerance"]:
                raise RuntimeError(f"RECOVERY_IDENTITY_MISMATCH: {run_id}")
            artifact = build_first_stage_solution_artifact(
                instance,
                x0,
                solution,
                case_id=run["case_id"],
                mode=run["mode"],
                identity=identity,
                solver_profile=FORMAL_SOLVER_PROFILE_ID,
            )
            artifact_path = output / "solutions" / f"{run_id.lower()}_first_stage_solution.json"
            write_first_stage_solution_artifact(artifact_path, artifact)
            load_first_stage_solution_artifact(artifact_path, instance)
            recovery_rows.append(
                {
                    "run_id": run_id,
                    "mode": run["mode"],
                    "objective": solution.objective,
                    "original_objective": run["original_objective"],
                    "objective_absolute_difference": difference,
                    "runtime_seconds": diagnostics["runtime_seconds"],
                    "optimality_gap": diagnostics["optimality_gap"],
                    "solution_payload_sha256": artifact["solution_payload_sha256"],
                    "solution_file_sha256": file_sha256(artifact_path),
                }
            )
            completed.append(run_id)

        evaluations = {}
        solution_artifacts = {}
        for run_id in RECOVERY_RUN_IDS:
            artifact = load_first_stage_solution_artifact(
                output / "solutions" / f"{run_id.lower()}_first_stage_solution.json",
                instance,
            )
            solution_artifacts[run_id] = artifact
            evaluations[run_id] = evaluate_robust_service_detailed(
                instance, matrix_from_artifact(artifact, instance), manifest["evaluation_Gamma"]
            )
            if evaluations[run_id].scenario_count != scenario_count(instance, 2):
                raise RuntimeError("unified evaluator scenario count mismatch")

        unified_rows = []
        for run_id in RECOVERY_RUN_IDS:
            artifact = solution_artifacts[run_id]
            evaluation = evaluations[run_id]
            service = evaluation.worst_service_scenario
            economic = evaluation.worst_recourse_scenario
            shortage = evaluation.worst_shortage_scenario
            unified_rows.append(
                {
                    "solution": run_id,
                    "optimization_mode": artifact["mode"],
                    "evaluation_Gamma": 2,
                    "scenario_count": evaluation.scenario_count,
                    "worst_recourse": evaluation.robust_recourse_cost,
                    "worst_recourse_transportation": economic.transportation_cost,
                    "worst_recourse_shortage_cost": economic.shortage_cost,
                    "worst_recourse_soft_service_penalty": economic.service_penalty_cost,
                    "worst_total_shortage": shortage.total_shortage,
                    "FR_min": service.minimum_fill_rate,
                    "avg_fill": service.average_fill_rate,
                    "worst_region": service.worst_region_id,
                    "worst_product": "NA",
                    "worst_recourse_shocks": json.dumps(economic.shock_set),
                    "worst_shortage_shocks": json.dumps(shortage.shock_set),
                    "worst_service_shocks": json.dumps(service.shock_set),
                    "total_inventory": artifact["total_inventory"],
                    "RI": artifact["RI"],
                    "reconfiguration_cost": artifact["reconfiguration_cost"],
                }
            )

        common_rows = []
        scenario_sources = {
            source: evaluations[source].worst_recourse_scenario.shock_set
            for source in RECOVERY_RUN_IDS
        }
        for source, shock_set in scenario_sources.items():
            for solution_id in RECOVERY_RUN_IDS:
                matches = [
                    row for row in evaluations[solution_id].scenarios if row.shock_set == shock_set
                ]
                if len(matches) != 1:
                    raise RuntimeError("common-scenario identity lookup failed")
                common_rows.append(
                    {
                        "common_scenario": f"C_{source}",
                        "scenario_source_solution": source,
                        "evaluated_solution": solution_id,
                        **scenario_row(matches[0]),
                    }
                )

        with (output / "recovery_identity.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=recovery_rows[0].keys())
            writer.writeheader()
            writer.writerows(recovery_rows)
        with (output / "table_a5_common_evaluation.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=unified_rows[0].keys())
            writer.writeheader()
            writer.writerows(unified_rows)
        with (output / "table_a5_common_scenario_cross_evaluation.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=common_rows[0].keys())
            writer.writeheader()
            writer.writerows(common_rows)

        x_values = {
            run_id: matrix_from_artifact(solution_artifacts[run_id], instance)
            for run_id in RECOVERY_RUN_IDS
        }
        max_difference = lambda left, right: max(
            abs(left[i][j] - right[i][j])
            for i in range(instance.num_depots)
            for j in range(instance.num_products)
        )
        comparison = {
            "max_abs_x_A3_minus_x0": max_difference(x_values["A3"], x0),
            "max_abs_x_A4_minus_x0": max_difference(x_values["A4"], x0),
            "max_abs_x_A5_minus_x0": max_difference(x_values["A5"], x0),
            "max_abs_x_A4_minus_x_A3": max_difference(x_values["A4"], x_values["A3"]),
        }
        a5_economic_improves_on_baselines = (
            evaluations["A5"].robust_recourse_cost
            <= min(
                evaluations["A3"].robust_recourse_cost,
                evaluations["A4"].robust_recourse_cost,
            )
            + manifest["objective_absolute_tolerance"]
        )
        if not a5_economic_improves_on_baselines:
            classification = "A5_BLOCK_MODEL_OR_EVALUATOR_INCONSISTENCY"
        elif (
            evaluations["A5"].worst_service_scenario.minimum_fill_rate
            < min(
                evaluations["A3"].worst_service_scenario.minimum_fill_rate,
                evaluations["A4"].worst_service_scenario.minimum_fill_rate,
            )
            - 1e-8
        ):
            classification = "A5_RESULT_VALID_METRIC_TRADEOFF"
        else:
            classification = "A5_ISSUE_RESOLVED_EVALUATION_MISMATCH"
        summary = {
            "status": (
                "RECOVERY_BLOCKED"
                if classification == "A5_BLOCK_MODEL_OR_EVALUATOR_INCONSISTENCY"
                else "RECOVERY_PASS"
            ),
            "classification": classification,
            "recovery_run_count": len(completed),
            "completed_run_ids": completed,
            "objective_identity_pass": True,
            "evaluation_Gamma": 2,
            "uncertain_items": instance.num_regions * instance.num_products,
            "scenario_count": scenario_count(instance, 2),
            "original_attempt_tree_hash_before": original_tree_hash,
            "original_attempt_tree_hash_after": verify_original_attempt(),
            "original_attempt_immutable": original_tree_hash == verify_original_attempt(),
            "nominal_reconfiguration_inactive_at_baseline": comparison[
                "max_abs_x_A4_minus_x0"
            ]
            <= 1e-6,
            "a5_worst_recourse_not_greater_than_baselines": a5_economic_improves_on_baselines,
            "FR_min_is_optimization_objective": False,
            "comparison": comparison,
            "e1_authorization": False,
            "e2_e7_authorization": False,
            "failures": [],
            "retries": 0,
        }
        write_json(output / "recovery_summary.json", summary)
        write_json(
            output / "provenance.json",
            {
                "recovery_id": manifest["recovery_id"],
                "authorization_manifest_hash": manifest_hash,
                "execution_git_commit": git_commit,
                "formal_config_hash": identity["config_hash"],
                "data_hash": identity["data_hash"],
                "x0_hash": identity["x0_hash"],
                "solver_profile": FORMAL_SOLVER_PROFILE_ID,
                "solver_version": solver_version,
                "python_version": platform.python_version(),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
            },
        )
        if summary["status"] != "RECOVERY_PASS":
            raise RuntimeError(classification)
    except Exception as exc:
        write_json(
            output / "failure.json",
            {
                "status": "RECOVERY_BLOCKED",
                "reason": str(exc),
                "completed_run_ids": completed,
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
