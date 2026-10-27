from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from robust_inventory_reconfiguration.e2_stockout_common_scenario import (
    FORMAL_SCENARIO_COUNT,
    build_structural_resource_preflight,
    build_common_scenario_manifest,
    build_policy_identity_manifest,
    canonical_sha256,
    evaluate_fixed_policy_scenarios,
    file_sha256,
    policy_from_manifest,
    run_pilot,
    summarize_complete_policy_metrics,
    static_source_audit,
    validate_complete_evaluation,
    validate_formal_checkpoint,
    validate_manifest_hash,
    write_json,
    write_checkpoint,
)
from robust_inventory_reconfiguration.instance import load_instance


ROOT = Path(__file__).resolve().parents[1]
IDENTITY_MANIFEST = ROOT / "artifacts/e2_stockout_policy_identity_manifest.json"
SCENARIO_MANIFEST = ROOT / "experiments/configs/e2_stockout_common_scenario_manifest.json"
STATIC_AUDIT = ROOT / "experiments/audits/e2_stockout_common_scenario_static_audit.json"
HISTORICAL_RUNNER_AUDIT = ROOT / "experiments/audits/e2_historical_runner_hash_audit.json"
FORMAL_AUTHORIZATION = ROOT / "experiments/configs/e2_stockout_formal_authorization.json"
FORMAL_CHECKPOINT_SCHEMA = ROOT / "experiments/schemas/e2_stockout_formal_checkpoint.schema.json"
SCENARIO_RESULT_SCHEMA = ROOT / "experiments/schemas/e2_stockout_scenario_result.schema.json"
RESOURCE_PREFLIGHT = ROOT / "experiments/audits/e2_stockout_resource_preflight.json"
PILOT_ROOT = ROOT / "experiments/results/e2_stockout_common_scenario_pilot_v1"
FORMAL_ROOT = ROOT / "experiments/results/e2_stockout_common_scenario_formal_v1"
DELIVERY_HASHES = ROOT / "experiments/audits/e2_stockout_delivery_hashes.json"

FORMAL_IDENTITY_PATHS = (
    "experiments/run_e2_stockout_common_scenario.py",
    "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py",
    "src/robust_inventory_reconfiguration/first_stage_solution.py",
    "src/robust_inventory_reconfiguration/instance.py",
    "src/robust_inventory_reconfiguration/robust_service.py",
    "src/robust_inventory_reconfiguration/scenarios.py",
    "src/robust_inventory_reconfiguration/solver_profile.py",
    "docs/e2_stockout_common_scenario_protocol.md",
    "experiments/schemas/e2_stockout_scenario_result.schema.json",
    "experiments/schemas/e2_stockout_formal_checkpoint.schema.json",
    "experiments/audits/e2_stockout_resource_preflight.json",
)


def planned_formal_tasks(identity: dict) -> list[dict]:
    tasks = []
    for case_id in identity["cases"]:
        for prefix in ("EXISTING_CANONICAL_", "ROBUST_EQUIVALENT_SCAL_BASE_"):
            policy_id = f"{prefix}{case_id}"
            row = next(
                item for item in identity["policies"] if item["policy_id"] == policy_id
            )
            tasks.append(
                {
                    "task_id": f"E2S-{case_id}-{'EXISTING' if prefix.startswith('EXISTING') else 'ROBUST'}",
                    "case_id": case_id,
                    "policy_id": policy_id,
                    "policy_sha256": row["coordinates_sha256"],
                }
            )
    return tasks


def build_formal_authorization(identity: dict, scenario: dict) -> dict:
    payload = {
        "schema_version": "1.0",
        "experiment_id": "E2_STOCKOUT_COMMON_SCENARIO_V1",
        "formal_run_authorized": False,
        "authorization_transition": [False],
        "human_policy_approval": False,
        "human_scientific_scope_approval": False,
        "resource_preflight_approval": False,
        "scoped_regression_approval": False,
        "authorized_task_ids": [],
        "planned_tasks": planned_formal_tasks(identity),
        "independent_policy_count": 2,
        "excluded_policy_role": "NOMINAL_VALIDATION_LABEL_SAME_AS_EXISTING",
        "identity_manifest_payload_sha256": identity["manifest_payload_sha256"],
        "scenario_manifest_payload_sha256": scenario["manifest_payload_sha256"],
        "identity_file_sha256": {
            path: file_sha256(ROOT / path) for path in FORMAL_IDENTITY_PATHS
        },
    }
    return {**payload, "authorization_payload_sha256": canonical_sha256(payload)}


def freeze() -> None:
    if FORMAL_AUTHORIZATION.exists():
        existing = json.loads(FORMAL_AUTHORIZATION.read_text(encoding="utf-8"))
        if existing.get("formal_run_authorized") is True:
            raise PermissionError("refusing to overwrite an authorized supplemental protocol")
    identity = build_policy_identity_manifest(ROOT)
    scenario = build_common_scenario_manifest(ROOT, identity)
    write_json(IDENTITY_MANIFEST, identity)
    write_json(SCENARIO_MANIFEST, scenario)
    pilot_checkpoint = json.loads(
        (
            PILOT_ROOT / "PILOT-210202-EXISTING_CANONICAL" / "checkpoint.json"
        ).read_text(encoding="utf-8")
    )
    write_json(
        RESOURCE_PREFLIGHT,
        build_structural_resource_preflight(scenario, pilot_checkpoint),
    )
    write_json(FORMAL_AUTHORIZATION, build_formal_authorization(identity, scenario))


def validate_formal_authorization(*, require_authorized: bool) -> tuple[dict, dict, dict]:
    identity = json.loads(IDENTITY_MANIFEST.read_text(encoding="utf-8"))
    scenario = json.loads(SCENARIO_MANIFEST.read_text(encoding="utf-8"))
    authorization = json.loads(FORMAL_AUTHORIZATION.read_text(encoding="utf-8"))
    validate_manifest_hash(identity)
    validate_manifest_hash(scenario)
    recorded = authorization.get("authorization_payload_sha256")
    payload = {
        key: value
        for key, value in authorization.items()
        if key != "authorization_payload_sha256"
    }
    if recorded != canonical_sha256(payload):
        raise ValueError("formal authorization payload hash mismatch")
    if authorization.get("identity_manifest_payload_sha256") != identity["manifest_payload_sha256"]:
        raise ValueError("formal authorization identity-manifest hash mismatch")
    if authorization.get("scenario_manifest_payload_sha256") != scenario["manifest_payload_sha256"]:
        raise ValueError("formal authorization scenario-manifest hash mismatch")
    if authorization.get("planned_tasks") != planned_formal_tasks(identity):
        raise ValueError("formal authorization task plan mismatch")
    if len(authorization["planned_tasks"]) != 16:
        raise ValueError("formal task plan must contain exactly 16 unique tasks")
    if any("NOMINAL" in task["policy_id"] for task in authorization["planned_tasks"]):
        raise ValueError("Nominal validation labels cannot be formal tasks")
    for path, expected in authorization.get("identity_file_sha256", {}).items():
        if path not in FORMAL_IDENTITY_PATHS or file_sha256(ROOT / path) != expected:
            raise ValueError(f"formal code/protocol identity mismatch: {path}")
    if set(authorization.get("identity_file_sha256", {})) != set(FORMAL_IDENTITY_PATHS):
        raise ValueError("formal identity file set mismatch")
    if not require_authorized:
        return identity, scenario, authorization
    approvals = (
        "human_policy_approval",
        "human_scientific_scope_approval",
        "resource_preflight_approval",
        "scoped_regression_approval",
    )
    if authorization.get("formal_run_authorized") is not True:
        raise PermissionError("E2 stockout formal run is not authorized")
    if authorization.get("authorization_transition") != [False, True]:
        raise PermissionError("E2 stockout authorization transition is invalid")
    if not all(authorization.get(key) is True for key in approvals):
        raise PermissionError("E2 stockout human approvals are incomplete")
    resource = json.loads(RESOURCE_PREFLIGHT.read_text(encoding="utf-8"))
    if resource.get("admission_status") != "PASS_FULL_CASE_PREFLIGHT_ON_32GB_TARGET":
        raise PermissionError("E2 stockout full-case resource preflight is incomplete")
    task_ids = [task["task_id"] for task in authorization["planned_tasks"]]
    if authorization.get("authorized_task_ids") != task_ids:
        raise PermissionError("E2 stockout authorized task list is incomplete")
    if scenario.get("formal_run_authorized") is not True or identity.get("formal_run_authorized") is not True:
        raise PermissionError("E2 stockout manifests remain formally locked")
    selected = {task["policy_id"] for task in authorization["planned_tasks"]}
    for row in identity["policies"]:
        expected = row["policy_id"] in selected
        if row.get("formal_authorized") is not expected:
            raise PermissionError(f"policy authorization mismatch: {row['policy_id']}")
    return identity, scenario, authorization


def audit() -> None:
    identity, scenario, authorization = validate_formal_authorization(
        require_authorized=False
    )
    source_audit = static_source_audit(
        ROOT
        / "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py"
    )
    checks = {
        "identity_manifest_hash_valid": True,
        "scenario_manifest_hash_valid": True,
        "formal_run_authorized_is_false": scenario["formal_run_authorized"] is False,
        "identity_requires_human_confirmation": (
            identity["identity_freeze_status"]
            == "PARTIAL_REQUIRES_HUMAN_CONFIRMATION"
        ),
        "all_scenario_counts_are_4657": all(
            row["scenario_count"] == 4657 for row in scenario["cases"]
        ),
        "all_dimensions_are_12_by_8": all(
            row["num_regions"] == 12
            and row["num_products"] == 8
            and row["uncertain_components"] == 96
            for row in scenario["cases"]
        ),
        "no_first_stage_solver_call_path": source_audit["pass"],
        "only_existing_is_pilot_authorized": all(
            row["pilot_authorized"] == row["policy_id"].startswith("EXISTING")
            for row in identity["policies"]
        ),
        "no_policy_is_formal_authorized": not any(
            row["formal_authorized"] for row in identity["policies"]
        ),
        "supplemental_authorization_is_false": (
            authorization["formal_run_authorized"] is False
            and authorization["authorization_transition"] == [False]
        ),
        "formal_task_plan_has_16_unique_non_nominal_tasks": (
            len({row["task_id"] for row in authorization["planned_tasks"]}) == 16
            and not any("NOMINAL" in row["policy_id"] for row in authorization["planned_tasks"])
        ),
        "all_scenario_id_order_hashes_are_frozen": all(
            row["scenario_id_order_sha256"]
            == canonical_sha256([f"S{index:04d}" for index in range(FORMAL_SCENARIO_COUNT)])
            for row in scenario["cases"]
        ),
    }
    audit_result = {
        "schema_version": "1.0",
        "experiment_id": "E2_STOCKOUT_COMMON_SCENARIO_V1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "source_audit": source_audit,
    }
    write_json(STATIC_AUDIT, audit_result)
    if audit_result["status"] != "PASS":
        raise RuntimeError("E2 stockout static audit failed")
    write_historical_runner_audit()


def formal_checkpoint_identity(
    *,
    authorization: dict,
    scenario_case: dict,
    scenario_manifest: dict,
    policy_row: dict,
) -> dict[str, object]:
    identities = authorization["identity_file_sha256"]
    return {
        "authorization_manifest_sha256": file_sha256(FORMAL_AUTHORIZATION),
        "identity_manifest_sha256": file_sha256(IDENTITY_MANIFEST),
        "scenario_manifest_sha256": file_sha256(SCENARIO_MANIFEST),
        "runner_sha256": identities["experiments/run_e2_stockout_common_scenario.py"],
        "evaluator_sha256": identities[
            "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py"
        ],
        "protocol_sha256": identities["docs/e2_stockout_common_scenario_protocol.md"],
        "scenario_result_schema_sha256": identities[
            "experiments/schemas/e2_stockout_scenario_result.schema.json"
        ],
        "formal_checkpoint_schema_sha256": identities[
            "experiments/schemas/e2_stockout_formal_checkpoint.schema.json"
        ],
        "instance_sha256": scenario_case["instance_sha256"],
        "policy_sha256": policy_row["coordinates_sha256"],
        "scenario_order_sha256": scenario_case["scenario_order_sha256"],
        "scenario_id_order_sha256": scenario_case["scenario_id_order_sha256"],
        "solver_profile_id": "gurobi-balanced-1e-8-v1",
        "solver_version": scenario_manifest["solver_version"],
        "threads": 1,
    }


def run_formal(*, resume: bool) -> dict:
    identity, scenario, authorization = validate_formal_authorization(
        require_authorized=True
    )
    completed = []
    baseline_rows_by_case: dict[str, list[dict]] = {}
    for task in authorization["planned_tasks"]:
        case_id = task["case_id"]
        policy_row = next(
            row for row in identity["policies"] if row["policy_id"] == task["policy_id"]
        )
        scenario_case = next(row for row in scenario["cases"] if row["case_id"] == case_id)
        instance_path = ROOT / scenario_case["instance_path"]
        if file_sha256(instance_path) != scenario_case["instance_sha256"]:
            raise ValueError(f"formal instance identity mismatch: {case_id}")
        instance = load_instance(instance_path)
        policy = policy_from_manifest(ROOT, policy_row)
        expected_identity = formal_checkpoint_identity(
            authorization=authorization,
            scenario_case=scenario_case,
            scenario_manifest=scenario,
            policy_row=policy_row,
        )
        output_dir = FORMAL_ROOT / task["task_id"]
        checkpoint_path = output_dir / "checkpoint.json"
        baseline_rows = baseline_rows_by_case.get(case_id)
        if checkpoint_path.exists():
            if not resume:
                raise FileExistsError(f"formal checkpoint already exists: {checkpoint_path}")
            checkpoint = validate_formal_checkpoint(
                checkpoint_path,
                expected_identity=expected_identity,
                instance=instance,
                policy=policy,
                scenario_manifest=scenario,
                baseline_rows=baseline_rows,
            )
        else:
            selected_ids = [f"S{index:04d}" for index in range(FORMAL_SCENARIO_COUNT)]
            started = time.perf_counter()
            evaluation = evaluate_fixed_policy_scenarios(
                instance, policy, selected_ids, threads=1
            )
            runtime = time.perf_counter() - started
            rows = validate_complete_evaluation(
                evaluation,
                instance=instance,
                policy=policy,
                scenario_manifest=scenario,
            )
            summary = summarize_complete_policy_metrics(
                rows,
                scenario,
                case_id,
                baseline_rows=baseline_rows,
            )
            checkpoint = {
                "schema_version": "1.0",
                "classification": "FORMAL_COMMON_SCENARIO_RESULT",
                "experiment_id": scenario["experiment_id"],
                "task_id": task["task_id"],
                "case_id": case_id,
                "policy_id": policy.policy_id,
                **expected_identity,
                "runtime_seconds": runtime,
                "scenario_count": len(rows),
                "evaluation": evaluation,
                "metric_summary": summary,
            }
            write_checkpoint(checkpoint_path, checkpoint)
            validate_formal_checkpoint(
                checkpoint_path,
                expected_identity=expected_identity,
                instance=instance,
                policy=policy,
                scenario_manifest=scenario,
                baseline_rows=baseline_rows,
            )
        if policy.policy_id.startswith("EXISTING"):
            baseline_rows_by_case[case_id] = checkpoint["evaluation"]["scenarios"]
        completed.append(task["task_id"])
    return {
        "classification": "FORMAL_COMMON_SCENARIO_RUN_COMPLETE",
        "completed_task_ids": completed,
    }


def resource_preflight() -> dict:
    _, scenario, _ = validate_formal_authorization(require_authorized=False)
    pilot_checkpoint = json.loads(
        (
            PILOT_ROOT
            / "PILOT-210202-EXISTING_CANONICAL"
            / "checkpoint.json"
        ).read_text(encoding="utf-8")
    )
    result = build_structural_resource_preflight(scenario, pilot_checkpoint)
    write_json(RESOURCE_PREFLIGHT, result)
    return result


def _git_blob_sha256(revision: str, path: str) -> str:
    content = subprocess.check_output(
        ["git", "cat-file", "blob", f"{revision}:{path}"], cwd=ROOT
    )
    return hashlib.sha256(content).hexdigest()


def write_historical_runner_audit() -> None:
    runner_path = "experiments/run_e2_policy_local.py"
    historical_commit = "4b1547296013c498cf4353c49c791cf1baf3566d"
    freeze_commit = "0631111342bdf663dfef943bb20c6fe708df3359"
    historical_manifest_path = (
        ROOT / "experiments/configs/formal/e2_existing_nominal_robust_authorization.json"
    )
    historical_manifest = json.loads(historical_manifest_path.read_text(encoding="utf-8"))
    manifest_hash = historical_manifest["runner_sha256"]
    historical_hash = _git_blob_sha256(historical_commit, runner_path)
    current_committed_hash = _git_blob_sha256("HEAD", runner_path)
    current_worktree_hash = file_sha256(ROOT / runner_path)
    write_json(
        HISTORICAL_RUNNER_AUDIT,
        {
            "schema_version": "1.0",
            "status": "HISTORICAL_IDENTITY_MISMATCH_CONFIRMED",
            "historical_manifest_path": historical_manifest_path.relative_to(ROOT).as_posix(),
            "historical_manifest_runner_sha256": manifest_hash,
            "historical_runner_commit": historical_commit,
            "historical_runner_blob_sha256": historical_hash,
            "historical_blob_matches_manifest": historical_hash == manifest_hash,
            "freeze_guard_commit": freeze_commit,
            "current_committed_runner_blob_sha256": current_committed_hash,
            "current_worktree_runner_file_sha256": current_worktree_hash,
            "current_committed_runner_matches_manifest": current_committed_hash == manifest_hash,
            "current_worktree_runner_matches_manifest": current_worktree_hash == manifest_hash,
            "semantic_change": {
                "changed": True,
                "description": (
                    "The current runner adds require_protocol_not_frozen before the historical "
                    "authorization gate. This changes execution admissibility but not the E2 "
                    "economic model, policy definitions, or recourse evaluator."
                ),
            },
            "historical_e2_raw_results_present": False,
            "closure_requirement": (
                "The historical runner blob is tested by pinned commit/hash. Restore the "
                "original E2 result/provenance archive only if complete historical execution "
                "lineage must be certified."
            ),
        },
    )


def pilot(resume: bool) -> None:
    output_dir = PILOT_ROOT / "PILOT-210202-EXISTING_CANONICAL"
    result = run_pilot(
        ROOT,
        IDENTITY_MANIFEST,
        SCENARIO_MANIFEST,
        output_dir,
        resume=resume,
    )
    print(
        json.dumps(
            {
                "classification": result["classification"],
                "case_id": result["case_id"],
                "policy_id": result["policy_id"],
                "runtime_seconds": result["runtime_seconds"],
                "peak_process_rss_bytes": result["peak_process_rss_bytes"],
                "scenario_count": len(result["evaluation"]["scenarios"]),
            },
            indent=2,
        )
    )


def hashes() -> None:
    paths = (
        "artifacts/e2_stockout_policy_identity_manifest.json",
        "docs/e2_stockout_policy_identity_audit.md",
        "docs/e2_stockout_common_scenario_protocol.md",
        "docs/e2_stockout_pilot_report.md",
        "docs/e2_stockout_independent_review.md",
        "docs/e2_historical_runner_hash_audit.md",
        "docs/e2_stockout_formal_admission_review.md",
        "docs/e2_stockout_blocker_remediation_review.md",
        "experiments/configs/e2_stockout_common_scenario_manifest.json",
        "experiments/configs/e2_stockout_formal_authorization.json",
        "experiments/audits/e2_stockout_common_scenario_static_audit.json",
        "experiments/audits/e2_historical_runner_hash_audit.json",
        "experiments/audits/e2_stockout_resource_preflight.json",
        "experiments/run_e2_stockout_common_scenario.py",
        "experiments/schemas/e2_stockout_scenario_result.schema.json",
        "experiments/schemas/e2_stockout_checkpoint.schema.json",
        "experiments/schemas/e2_stockout_formal_checkpoint.schema.json",
        "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py",
        "tests/test_e2_stockout_common_scenario.py",
        "tests/test_e2_stockout_formal_gate.py",
        "tests/test_e2_stockout_historical_runner_audit.py",
        "tests/test_e2_protocol.py",
        "experiments/results/e2_stockout_common_scenario_pilot_v1/PILOT-210202-EXISTING_CANONICAL/checkpoint.json",
        "experiments/results/e2_stockout_common_scenario_pilot_v1/PILOT-210202-EXISTING_CANONICAL/checkpoint.json.sha256",
        "experiments/results/e2_stockout_common_scenario_pilot_v1/PILOT-210202-EXISTING_CANONICAL/hashes.json",
    )
    write_json(
        DELIVERY_HASHES,
        {
            "schema_version": "1.0",
            "classification": "AUDIT_AND_PILOT_DELIVERABLES_NOT_FORMAL_RESULTS",
            "files": {
                path: file_sha256(ROOT / path)
                for path in paths
            },
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "freeze",
            "audit",
            "pilot",
            "resume-pilot",
            "resource-preflight",
            "formal-run",
            "resume-formal",
            "hashes",
        ),
    )
    args = parser.parse_args()
    if args.command == "freeze":
        freeze()
    elif args.command == "audit":
        audit()
    elif args.command == "hashes":
        hashes()
    elif args.command == "resource-preflight":
        print(json.dumps(resource_preflight(), indent=2))
    elif args.command in ("formal-run", "resume-formal"):
        print(json.dumps(run_formal(resume=args.command == "resume-formal"), indent=2))
    else:
        pilot(resume=args.command == "resume-pilot")


if __name__ == "__main__":
    main()
