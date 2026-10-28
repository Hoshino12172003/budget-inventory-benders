from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

from robust_inventory_reconfiguration.e2_stockout_common_scenario import (
    FORMAL_SCENARIO_COUNT,
    PeakMemoryMonitor,
    REPORTING_TIE_BREAK_TOLERANCE,
    assemble_fixed_policy_scenario_rows,
    block_key_from_payload,
    block_key_payload,
    build_structural_resource_preflight,
    build_common_scenario_manifest,
    build_policy_identity_manifest,
    canonical_sha256,
    evaluate_fixed_policy_scenarios,
    file_sha256,
    fixed_policy_block_keys,
    policy_from_manifest,
    run_pilot,
    summarize_complete_policy_metrics,
    solve_fixed_policy_block,
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
STATIC_AUDIT = ROOT / "experiments/audits/e2_stockout_common_scenario_static_audit_v2r1.json"
HISTORICAL_RUNNER_AUDIT = ROOT / "experiments/audits/e2_historical_runner_hash_audit.json"
FORMAL_AUTHORIZATION = ROOT / "experiments/configs/e2_stockout_formal_authorization_v2r1.json"
FORMAL_CHECKPOINT_SCHEMA = ROOT / "experiments/schemas/e2_stockout_formal_checkpoint.schema.json"
SCENARIO_RESULT_SCHEMA = ROOT / "experiments/schemas/e2_stockout_scenario_result.schema.json"
RESOURCE_PREFLIGHT = ROOT / "experiments/audits/e2_stockout_resource_preflight_v2r1.json"
PREFLIGHT_AUTHORIZATION = ROOT / "experiments/configs/e2_stockout_resource_preflight_authorization_v2r1.json"
PREFLIGHT_CHECKPOINT_SCHEMA = ROOT / "experiments/schemas/e2_stockout_resource_preflight_checkpoint.schema.json"
SCIENTIFIC_CONFIRMATION = ROOT / "docs/e2_stockout_scientific_policy_confirmation.md"
PILOT_ROOT = ROOT / "experiments/results/e2_stockout_common_scenario_pilot_v1"
FORMAL_ROOT = ROOT / "experiments/results/e2_stockout_common_scenario_formal_v2r1"
PREFLIGHT_ROOT = ROOT / "experiments/results/e2_stockout_resource_preflight_v2r1/PREFLIGHT-210202-EXISTING"
DELIVERY_HASHES = ROOT / "experiments/audits/e2_stockout_delivery_hashes_v2r1.json"

FORMAL_IDENTITY_PATHS = (
    "experiments/run_e2_stockout_common_scenario.py",
    "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py",
    "src/robust_inventory_reconfiguration/first_stage_solution.py",
    "src/robust_inventory_reconfiguration/instance.py",
    "src/robust_inventory_reconfiguration/robust_service.py",
    "src/robust_inventory_reconfiguration/scenarios.py",
    "src/robust_inventory_reconfiguration/solver_profile.py",
    "docs/e2_stockout_common_scenario_protocol.md",
    "docs/e2_stockout_scientific_policy_confirmation.md",
    "experiments/schemas/e2_stockout_scenario_result.schema.json",
    "experiments/schemas/e2_stockout_formal_checkpoint.schema.json",
    "experiments/configs/e2_stockout_scoped_regression_gate.json",
    "experiments/audits/e2_stockout_resource_preflight_v2r1.json",
)

PREFLIGHT_IDENTITY_PATHS = (
    "experiments/run_e2_stockout_common_scenario.py",
    "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py",
    "src/robust_inventory_reconfiguration/first_stage_solution.py",
    "src/robust_inventory_reconfiguration/instance.py",
    "src/robust_inventory_reconfiguration/robust_service.py",
    "src/robust_inventory_reconfiguration/scenarios.py",
    "src/robust_inventory_reconfiguration/solver_profile.py",
    "docs/e2_stockout_common_scenario_protocol.md",
    "docs/e2_stockout_scientific_policy_confirmation.md",
    "experiments/schemas/e2_stockout_scenario_result.schema.json",
    "experiments/schemas/e2_stockout_resource_preflight_checkpoint.schema.json",
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
        "human_policy_approval": True,
        "human_scientific_scope_approval": True,
        "resource_preflight_approval": (
            json.loads(RESOURCE_PREFLIGHT.read_text(encoding="utf-8")).get(
                "admission_status"
            )
            == "PASS_FULL_CASE_PREFLIGHT_ON_32GB_TARGET"
        ),
        "scoped_regression_approval": True,
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


def build_preflight_authorization(identity: dict, scenario: dict) -> dict:
    policy_id = "EXISTING_CANONICAL_210202"
    policy = next(row for row in identity["policies"] if row["policy_id"] == policy_id)
    case = next(row for row in scenario["cases"] if row["case_id"] == "210202")
    payload = {
        "schema_version": "1.0",
        "experiment_id": "E2_STOCKOUT_COMMON_SCENARIO_V1",
        "classification": "PREFLIGHT_AUTHORIZATION_NON_PUBLISHABLE",
        "preflight_run_authorized": True,
        "formal_run_authorized": False,
        "authorization_scope": "ONE_COMPLETE_632_BLOCK_RESOURCE_AND_RECOVERY_PREFLIGHT",
        "case_id": "210202",
        "policy_id": policy_id,
        "policy_sha256": policy["coordinates_sha256"],
        "instance_sha256": case["instance_sha256"],
        "scenario_count": FORMAL_SCENARIO_COUNT,
        "expected_block_count": 632,
        "protocol_interrupt_after_blocks": 16,
        "threads": 1,
        "identity_manifest_payload_sha256": identity["manifest_payload_sha256"],
        "scenario_manifest_payload_sha256": scenario["manifest_payload_sha256"],
        "identity_file_sha256": {
            path: file_sha256(ROOT / path) for path in PREFLIGHT_IDENTITY_PATHS
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
    preserve_completed_preflight = False
    if RESOURCE_PREFLIGHT.exists():
        current_resource = json.loads(RESOURCE_PREFLIGHT.read_text(encoding="utf-8"))
        preserve_completed_preflight = (
            current_resource.get("admission_status")
            == "PASS_FULL_CASE_PREFLIGHT_ON_32GB_TARGET"
        )
        if preserve_completed_preflight:
            validate_completed_resource_preflight_evidence()
    if not preserve_completed_preflight:
        pilot_checkpoint = json.loads(
            (
                PILOT_ROOT / "PILOT-210202-EXISTING_CANONICAL" / "checkpoint.json"
            ).read_text(encoding="utf-8")
        )
        write_json(
            RESOURCE_PREFLIGHT,
            build_structural_resource_preflight(scenario, pilot_checkpoint),
        )
    write_json(PREFLIGHT_AUTHORIZATION, build_preflight_authorization(identity, scenario))
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
        "scientific_policy_definition_is_confirmed": (
            identity["identity_freeze_status"]
            == "FROZEN_TWO_POLICY_SCIENTIFIC_DEFINITION_CONFIRMED"
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


def validate_preflight_authorization() -> tuple[dict, dict, dict]:
    identity = json.loads(IDENTITY_MANIFEST.read_text(encoding="utf-8"))
    scenario = json.loads(SCENARIO_MANIFEST.read_text(encoding="utf-8"))
    authorization = json.loads(PREFLIGHT_AUTHORIZATION.read_text(encoding="utf-8"))
    validate_manifest_hash(identity)
    validate_manifest_hash(scenario)
    payload = {
        key: value
        for key, value in authorization.items()
        if key != "authorization_payload_sha256"
    }
    if authorization.get("authorization_payload_sha256") != canonical_sha256(payload):
        raise ValueError("preflight authorization payload hash mismatch")
    expected = {
        "classification": "PREFLIGHT_AUTHORIZATION_NON_PUBLISHABLE",
        "preflight_run_authorized": True,
        "formal_run_authorized": False,
        "authorization_scope": "ONE_COMPLETE_632_BLOCK_RESOURCE_AND_RECOVERY_PREFLIGHT",
        "case_id": "210202",
        "policy_id": "EXISTING_CANONICAL_210202",
        "scenario_count": FORMAL_SCENARIO_COUNT,
        "expected_block_count": 632,
        "protocol_interrupt_after_blocks": 16,
        "threads": 1,
        "identity_manifest_payload_sha256": identity["manifest_payload_sha256"],
        "scenario_manifest_payload_sha256": scenario["manifest_payload_sha256"],
    }
    for key, value in expected.items():
        if authorization.get(key) != value:
            raise ValueError(f"preflight authorization identity mismatch: {key}")
    policy_row = next(
        row
        for row in identity["policies"]
        if row["policy_id"] == authorization["policy_id"]
    )
    case_row = next(
        row for row in scenario["cases"] if row["case_id"] == authorization["case_id"]
    )
    if authorization.get("policy_sha256") != policy_row["coordinates_sha256"]:
        raise ValueError("preflight policy identity mismatch")
    if authorization.get("instance_sha256") != case_row["instance_sha256"]:
        raise ValueError("preflight instance identity mismatch")
    file_hashes = authorization.get("identity_file_sha256", {})
    if set(file_hashes) != set(PREFLIGHT_IDENTITY_PATHS):
        raise ValueError("preflight identity file set mismatch")
    for path, expected_hash in file_hashes.items():
        if file_sha256(ROOT / path) != expected_hash:
            raise ValueError(f"preflight code/protocol identity mismatch: {path}")
    if identity.get("formal_run_authorized") is not False:
        raise PermissionError("preflight requires identity formal authorization false")
    if scenario.get("formal_run_authorized") is not False:
        raise PermissionError("preflight requires scenario formal authorization false")
    if any(row.get("formal_authorized") for row in identity["policies"]):
        raise PermissionError("preflight requires every policy formal authorization false")
    return identity, scenario, authorization


def preflight_checkpoint_identity(
    *, authorization: dict, scenario: dict, case_row: dict, policy_row: dict, block_keys: tuple
) -> dict[str, object]:
    identities = authorization["identity_file_sha256"]
    return {
        "preflight_authorization_sha256": file_sha256(PREFLIGHT_AUTHORIZATION),
        "identity_manifest_sha256": file_sha256(IDENTITY_MANIFEST),
        "scenario_manifest_sha256": file_sha256(SCENARIO_MANIFEST),
        "runner_sha256": identities["experiments/run_e2_stockout_common_scenario.py"],
        "evaluator_sha256": identities[
            "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py"
        ],
        "protocol_sha256": identities["docs/e2_stockout_common_scenario_protocol.md"],
        "scientific_confirmation_sha256": identities[
            "docs/e2_stockout_scientific_policy_confirmation.md"
        ],
        "checkpoint_schema_sha256": identities[
            "experiments/schemas/e2_stockout_resource_preflight_checkpoint.schema.json"
        ],
        "instance_sha256": case_row["instance_sha256"],
        "policy_sha256": policy_row["coordinates_sha256"],
        "scenario_order_sha256": case_row["scenario_order_sha256"],
        "scenario_id_order_sha256": case_row["scenario_id_order_sha256"],
        "block_order_sha256": canonical_sha256(
            [block_key_payload(key) for key in block_keys]
        ),
        "solver_profile_id": "gurobi-balanced-1e-8-v1",
        "solver_version": scenario["solver_version"],
        "threads": 1,
    }


def validate_preflight_checkpoint(
    checkpoint_path: Path,
    *,
    expected_identity: dict[str, object],
    instance,
    policy,
    scenario_manifest: dict,
    block_keys: tuple,
) -> dict:
    digest_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".sha256")
    if not checkpoint_path.exists() or not digest_path.exists():
        raise FileNotFoundError("preflight checkpoint or digest is missing")
    if file_sha256(checkpoint_path) != digest_path.read_text(encoding="utf-8").strip():
        raise ValueError("preflight checkpoint content hash mismatch")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    expected_header = {
        "schema_version": "1.0",
        "classification": "PREFLIGHT_NON_PUBLISHABLE",
        "experiment_id": "E2_STOCKOUT_COMMON_SCENARIO_V1",
        "task_id": "PREFLIGHT-210202-EXISTING",
        "case_id": "210202",
        "policy_id": "EXISTING_CANONICAL_210202",
        "formal_run_authorized": False,
        "scenario_count": FORMAL_SCENARIO_COUNT,
        "total_blocks": 632,
    }
    for key, value in {**expected_header, **expected_identity}.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"preflight checkpoint identity mismatch: {key}")
    results = checkpoint.get("block_results")
    completed = checkpoint.get("completed_blocks")
    if not isinstance(results, list) or completed != len(results):
        raise ValueError("preflight checkpoint completed-block count mismatch")
    if completed < 0 or completed > len(block_keys):
        raise ValueError("preflight checkpoint block count is outside the frozen plan")
    actual_keys = [block_key_from_payload(row) for row in results]
    if actual_keys != list(block_keys[:completed]):
        raise ValueError("preflight checkpoint is not the exact frozen block prefix")
    required_metrics = (
        "total_shipment",
        "total_shortage",
        "service_violation",
        "transportation_cost",
        "shortage_penalty_cost",
        "service_penalty_cost",
        "economic_optimum_cost",
        "reporting_tie_break_cost_delta",
    )
    for row in results:
        if row.get("economic_solver_status") != "OPTIMAL":
            raise ValueError("preflight economic block status is not OPTIMAL")
        if row.get("reporting_solver_status") != "OPTIMAL":
            raise ValueError("preflight reporting block status is not OPTIMAL")
        if row.get("economic_solver_status_code") != 2:
            raise ValueError("preflight economic block status code is not OPTIMAL")
        if row.get("reporting_solver_status_code") != 2:
            raise ValueError("preflight reporting block status code is not OPTIMAL")
        if any(
            not isinstance(row.get(key), (int, float))
            or not math.isfinite(float(row[key]))
            for key in required_metrics
        ):
            raise ValueError("preflight block has missing or non-finite metrics")
        component_sum = sum(
            float(row[key])
            for key in (
                "transportation_cost",
                "shortage_penalty_cost",
                "service_penalty_cost",
            )
        )
        expected_delta = component_sum - float(row["economic_optimum_cost"])
        if not math.isclose(
            float(row["reporting_tie_break_cost_delta"]),
            expected_delta,
            abs_tol=1e-6,
        ):
            raise ValueError("preflight block cost decomposition mismatch")
        if expected_delta < -1e-9 or expected_delta > (
            1e-6 + REPORTING_TIE_BREAK_TOLERANCE
        ):
            raise ValueError("preflight block exceeds the frozen tie-break band")
    if checkpoint.get("policy_coordinates_before_sha256") != policy.coordinates_sha256:
        raise ValueError("preflight initial policy coordinates mismatch")
    status = checkpoint.get("completion_status")
    if status in {"INCOMPLETE_CHECKPOINT", "INTERRUPTED_BY_PROTOCOL"}:
        if completed <= 0 or completed >= len(block_keys):
            raise ValueError("preflight interrupted checkpoint has invalid coverage")
        if (
            status == "INTERRUPTED_BY_PROTOCOL"
            and checkpoint.get("protocol_interrupt_exercised") is not True
        ):
            raise ValueError("preflight interrupted checkpoint lacks recovery evidence")
        if "evaluation" in checkpoint or "metric_summary" in checkpoint:
            raise ValueError("partial preflight checkpoint contains complete-result fields")
    elif status == "COMPLETE":
        if completed != len(block_keys):
            raise ValueError("complete preflight checkpoint does not cover all blocks")
        if checkpoint.get("policy_coordinates_after_sha256") != policy.coordinates_sha256:
            raise ValueError("preflight final policy coordinates mismatch")
        rows = validate_complete_evaluation(
            checkpoint.get("evaluation", {}),
            instance=instance,
            policy=policy,
            scenario_manifest=scenario_manifest,
        )
        recomputed = summarize_complete_policy_metrics(
            rows, scenario_manifest, policy.case_id
        )
        if checkpoint.get("metric_summary") != recomputed:
            raise ValueError("preflight complete metric summary mismatch")
        if checkpoint.get("protocol_interrupt_exercised") is not True:
            raise ValueError("complete preflight did not exercise interruption recovery")
    else:
        raise ValueError("preflight checkpoint completion status is invalid")
    return checkpoint


def _preflight_block_result_map(rows: list[dict]) -> dict:
    return {block_key_from_payload(row): row for row in rows}


def run_resource_preflight_task(*, resume: bool) -> dict:
    identity, scenario, authorization = validate_preflight_authorization()
    policy_row = next(
        row for row in identity["policies"] if row["policy_id"] == authorization["policy_id"]
    )
    case_row = next(
        row for row in scenario["cases"] if row["case_id"] == authorization["case_id"]
    )
    instance_path = ROOT / case_row["instance_path"]
    if file_sha256(instance_path) != case_row["instance_sha256"]:
        raise ValueError("preflight instance file identity mismatch")
    instance = load_instance(instance_path)
    policy = policy_from_manifest(ROOT, policy_row)
    selected_ids = [f"S{index:04d}" for index in range(FORMAL_SCENARIO_COUNT)]
    block_keys = fixed_policy_block_keys(instance, selected_ids)
    if len(block_keys) != authorization["expected_block_count"]:
        raise ValueError("preflight frozen block count mismatch")
    expected_identity = preflight_checkpoint_identity(
        authorization=authorization,
        scenario=scenario,
        case_row=case_row,
        policy_row=policy_row,
        block_keys=block_keys,
    )
    checkpoint_path = PREFLIGHT_ROOT / "checkpoint.json"
    if resume:
        checkpoint = validate_preflight_checkpoint(
            checkpoint_path,
            expected_identity=expected_identity,
            instance=instance,
            policy=policy,
            scenario_manifest=scenario,
            block_keys=block_keys,
        )
        if checkpoint["completion_status"] not in {
            "INCOMPLETE_CHECKPOINT",
            "INTERRUPTED_BY_PROTOCOL",
        }:
            raise ValueError("preflight resume requires an interrupted checkpoint")
        start_index = checkpoint["completed_blocks"]
        checkpoint["resume_validation"] = {
            "validated_completed_prefix_blocks": start_index,
            "checkpoint_digest_verified": True,
            "identity_chain_verified": True,
        }
    else:
        if checkpoint_path.exists() or checkpoint_path.with_suffix(".json.sha256").exists():
            raise FileExistsError("preflight checkpoint already exists; use preflight-resume")
        start_index = 0
        checkpoint = {
            "schema_version": "1.0",
            "classification": "PREFLIGHT_NON_PUBLISHABLE",
            "experiment_id": scenario["experiment_id"],
            "task_id": "PREFLIGHT-210202-EXISTING",
            "case_id": policy.case_id,
            "policy_id": policy.policy_id,
            "formal_run_authorized": False,
            **expected_identity,
            "scenario_count": FORMAL_SCENARIO_COUNT,
            "total_blocks": len(block_keys),
            "completed_blocks": 0,
            "completion_status": "RUNNING",
            "protocol_interrupt_exercised": False,
            "policy_coordinates_before_sha256": policy.coordinates_sha256,
            "block_results": [],
            "run_segments": [],
        }

    segment = {
        "segment_index": len(checkpoint["run_segments"]) + 1,
        "resumed": resume,
        "started_from_completed_blocks": start_index,
        "completed_blocks_at_end": start_index,
        "runtime_seconds": 0.0,
        "peak_process_rss_bytes": 0,
        "end_reason": "RUNNING",
    }
    checkpoint["run_segments"].append(segment)
    started = time.perf_counter()
    with PeakMemoryMonitor() as monitor:
        for index in range(start_index, len(block_keys)):
            result = solve_fixed_policy_block(
                instance, policy, block_keys[index], threads=authorization["threads"]
            )
            checkpoint["block_results"].append(result)
            checkpoint["completed_blocks"] = index + 1
            segment["completed_blocks_at_end"] = index + 1
            segment["runtime_seconds"] = time.perf_counter() - started
            segment["peak_process_rss_bytes"] = monitor.peak_bytes
            checkpoint["completion_status"] = "INCOMPLETE_CHECKPOINT"
            write_checkpoint(checkpoint_path, checkpoint)
            if not resume and index + 1 == authorization["protocol_interrupt_after_blocks"]:
                checkpoint["completion_status"] = "INTERRUPTED_BY_PROTOCOL"
                checkpoint["protocol_interrupt_exercised"] = True
                segment["end_reason"] = "PREDECLARED_PROTOCOL_INTERRUPT"
                segment["runtime_seconds"] = time.perf_counter() - started
                segment["peak_process_rss_bytes"] = monitor.peak_bytes
                write_checkpoint(checkpoint_path, checkpoint)
                return checkpoint

    segment["end_reason"] = "ALL_REMAINING_BLOCKS_COMPLETE"
    segment["runtime_seconds"] = time.perf_counter() - started
    segment["peak_process_rss_bytes"] = monitor.peak_bytes
    after_hash = canonical_sha256(
        {
            "y": policy.y,
            "x": policy.x,
            "a_plus": policy.a_plus,
            "a_minus": policy.a_minus,
        }
    )
    if after_hash != policy.coordinates_sha256:
        raise RuntimeError("preflight first-stage coordinates changed")
    scenario_rows = assemble_fixed_policy_scenario_rows(
        instance,
        policy,
        selected_ids,
        _preflight_block_result_map(checkpoint["block_results"]),
    )
    evaluation = {
        "policy_coordinates_before_sha256": policy.coordinates_sha256,
        "policy_coordinates_after_sha256": after_hash,
        "unique_product_local_blocks": len(block_keys),
        "scenarios": scenario_rows,
    }
    validated_rows = validate_complete_evaluation(
        evaluation, instance=instance, policy=policy, scenario_manifest=scenario
    )
    checkpoint.update(
        {
            "completion_status": "COMPLETE",
            "policy_coordinates_after_sha256": after_hash,
            "runtime_seconds": sum(
                float(row["runtime_seconds"]) for row in checkpoint["run_segments"]
            ),
            "peak_process_rss_bytes": max(
                int(row["peak_process_rss_bytes"]) for row in checkpoint["run_segments"]
            ),
            "economic_optimal_block_count": sum(
                row["economic_solver_status"] == "OPTIMAL"
                for row in checkpoint["block_results"]
            ),
            "reporting_optimal_block_count": sum(
                row["reporting_solver_status"] == "OPTIMAL"
                for row in checkpoint["block_results"]
            ),
            "evaluation": evaluation,
            "metric_summary": summarize_complete_policy_metrics(
                validated_rows, scenario, policy.case_id
            ),
        }
    )
    write_checkpoint(checkpoint_path, checkpoint)
    validate_preflight_checkpoint(
        checkpoint_path,
        expected_identity=expected_identity,
        instance=instance,
        policy=policy,
        scenario_manifest=scenario,
        block_keys=block_keys,
    )
    digest_path = checkpoint_path.with_suffix(".json.sha256")
    result_manifest = {
        "schema_version": "1.0",
        "classification": "PREFLIGHT_NON_PUBLISHABLE",
        "admission_status": "PASS_FULL_CASE_PREFLIGHT_ON_32GB_TARGET",
        "checkpoint_sha256": file_sha256(checkpoint_path),
        "checkpoint_digest_file_sha256": file_sha256(digest_path),
        "checkpoint_bytes": checkpoint_path.stat().st_size,
        "checkpoint_digest_bytes": digest_path.stat().st_size,
        "checkpoint_bundle_bytes": checkpoint_path.stat().st_size + digest_path.stat().st_size,
        "runtime_seconds": checkpoint["runtime_seconds"],
        "peak_process_rss_bytes": checkpoint["peak_process_rss_bytes"],
        "completed_blocks": checkpoint["completed_blocks"],
        "scenario_count": FORMAL_SCENARIO_COUNT,
        "protocol_interrupt_exercised": True,
        "resume_validation": checkpoint["resume_validation"],
    }
    result_manifest_path = PREFLIGHT_ROOT / "result_manifest.json"
    write_json(result_manifest_path, result_manifest)
    pilot_checkpoint = json.loads(
        (PILOT_ROOT / "PILOT-210202-EXISTING_CANONICAL" / "checkpoint.json").read_text(
            encoding="utf-8"
        )
    )
    resource = build_structural_resource_preflight(scenario, pilot_checkpoint)
    resource.update(
        {
            "classification": "VERIFIED_FULL_CASE_RESOURCE_AND_RECOVERY_PREFLIGHT",
            "admission_status": "PASS_FULL_CASE_PREFLIGHT_ON_32GB_TARGET",
            "preflight_result_manifest_path": result_manifest_path.relative_to(ROOT).as_posix(),
            "preflight_result_manifest_sha256": file_sha256(result_manifest_path),
            "preflight_checkpoint_sha256": file_sha256(checkpoint_path),
            "preflight_case_id": policy.case_id,
            "preflight_policy_id": policy.policy_id,
            "completed_blocks": checkpoint["completed_blocks"],
            "scenario_count": FORMAL_SCENARIO_COUNT,
            "runtime_seconds": checkpoint["runtime_seconds"],
            "peak_process_rss_bytes": checkpoint["peak_process_rss_bytes"],
            "output_bundle_bytes": result_manifest["checkpoint_bundle_bytes"],
            "protocol_interrupt_exercised": True,
            "formal_run_authorized": False,
        }
    )
    write_json(RESOURCE_PREFLIGHT, resource)
    return checkpoint


def validate_completed_resource_preflight_evidence() -> dict:
    identity, scenario, authorization = validate_preflight_authorization()
    policy_row = next(
        row for row in identity["policies"] if row["policy_id"] == authorization["policy_id"]
    )
    case_row = next(
        row for row in scenario["cases"] if row["case_id"] == authorization["case_id"]
    )
    instance_path = ROOT / case_row["instance_path"]
    if file_sha256(instance_path) != case_row["instance_sha256"]:
        raise ValueError("completed preflight instance file identity mismatch")
    instance = load_instance(instance_path)
    policy = policy_from_manifest(ROOT, policy_row)
    selected_ids = [f"S{index:04d}" for index in range(FORMAL_SCENARIO_COUNT)]
    block_keys = fixed_policy_block_keys(instance, selected_ids)
    expected_identity = preflight_checkpoint_identity(
        authorization=authorization,
        scenario=scenario,
        case_row=case_row,
        policy_row=policy_row,
        block_keys=block_keys,
    )
    checkpoint_path = PREFLIGHT_ROOT / "checkpoint.json"
    checkpoint = validate_preflight_checkpoint(
        checkpoint_path,
        expected_identity=expected_identity,
        instance=instance,
        policy=policy,
        scenario_manifest=scenario,
        block_keys=block_keys,
    )
    if checkpoint["completion_status"] != "COMPLETE":
        raise ValueError("resource preflight evidence is not complete")
    result_path = PREFLIGHT_ROOT / "result_manifest.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    expected_result = {
        "classification": "PREFLIGHT_NON_PUBLISHABLE",
        "admission_status": "PASS_FULL_CASE_PREFLIGHT_ON_32GB_TARGET",
        "checkpoint_sha256": file_sha256(checkpoint_path),
        "checkpoint_digest_file_sha256": file_sha256(
            checkpoint_path.with_suffix(".json.sha256")
        ),
        "checkpoint_bytes": checkpoint_path.stat().st_size,
        "checkpoint_digest_bytes": checkpoint_path.with_suffix(".json.sha256").stat().st_size,
        "runtime_seconds": checkpoint["runtime_seconds"],
        "peak_process_rss_bytes": checkpoint["peak_process_rss_bytes"],
        "completed_blocks": 632,
        "scenario_count": FORMAL_SCENARIO_COUNT,
        "protocol_interrupt_exercised": True,
        "resume_validation": checkpoint["resume_validation"],
    }
    for key, value in expected_result.items():
        if result.get(key) != value:
            raise ValueError(f"resource preflight result-manifest mismatch: {key}")
    if result.get("checkpoint_bundle_bytes") != (
        result["checkpoint_bytes"] + result["checkpoint_digest_bytes"]
    ):
        raise ValueError("resource preflight output-size identity mismatch")
    resource = json.loads(RESOURCE_PREFLIGHT.read_text(encoding="utf-8"))
    if resource.get("admission_status") != "PASS_FULL_CASE_PREFLIGHT_ON_32GB_TARGET":
        raise ValueError("resource preflight audit is not admitted")
    if resource.get("preflight_result_manifest_sha256") != file_sha256(result_path):
        raise ValueError("resource preflight audit result hash mismatch")
    if resource.get("preflight_checkpoint_sha256") != file_sha256(checkpoint_path):
        raise ValueError("resource preflight audit checkpoint hash mismatch")
    if resource.get("formal_run_authorized") is not False:
        raise ValueError("resource preflight audit changed formal authorization")
    return checkpoint


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
            "preflight-interrupt",
            "preflight-resume",
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
    elif args.command in ("preflight-interrupt", "preflight-resume"):
        result = run_resource_preflight_task(
            resume=args.command == "preflight-resume"
        )
        print(
            json.dumps(
                {
                    "classification": result["classification"],
                    "completion_status": result["completion_status"],
                    "completed_blocks": result["completed_blocks"],
                    "scenario_count": result["scenario_count"],
                    "runtime_seconds": result.get("runtime_seconds"),
                    "peak_process_rss_bytes": result.get("peak_process_rss_bytes"),
                },
                indent=2,
            )
        )
    elif args.command in ("formal-run", "resume-formal"):
        print(json.dumps(run_formal(resume=args.command == "resume-formal"), indent=2))
    else:
        pilot(resume=args.command == "resume-pilot")


if __name__ == "__main__":
    main()
