"""Read-only acceptance audit and paper-table builder for E2 V2R1.

This script deliberately does not import Gurobi or any model/runner module.  It
only reads frozen JSON artifacts, validates their identity and arithmetic, and
writes derived audit/table files.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "experiments/results/e2_stockout_common_scenario_formal_v2r1"
AUTH_PATH = ROOT / "experiments/configs/e2_stockout_formal_authorization_v2r1.json"
IDENTITY_PATH = ROOT / "artifacts/e2_stockout_policy_identity_manifest.json"
SCENARIO_PATH = ROOT / "experiments/configs/e2_stockout_common_scenario_manifest.json"
OUTPUT_CSV = ROOT / "experiments/analysis/e2_stockout_v2r1_policy_comparison.csv"
OUTPUT_AUDIT = ROOT / "experiments/audits/e2_stockout_v2r1_acceptance.json"
OUTPUT_HASHES = ROOT / "experiments/audits/e2_stockout_v2r1_archive_sha256.json"
ARCHIVE_PATH = ROOT / "artifacts/e2_stockout_common_scenario_formal_v2r1_results.zip"
RESOURCE_ARCHIVE_PATH = ROOT / "artifacts/e2_stockout_resource_preflight_v2r1.zip"
RESOURCE_RESULT_ROOT = ROOT / "experiments/results/e2_stockout_resource_preflight_v2r1"
RESOURCE_AUDIT_PATH = ROOT / "experiments/audits/e2_stockout_resource_preflight_v2r1.json"
RESOURCE_AUTH_PATH = ROOT / "experiments/configs/e2_stockout_resource_preflight_authorization_v2r1.json"

CASES = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")
POLICIES = ("EXISTING", "ROBUST")
SCENARIO_IDS = tuple(f"S{i:04d}" for i in range(4657))
TOL = 1e-6
METRICS = (
    ("total_shortage", "physical units"),
    ("shortage_penalty_cost", "cost units"),
    ("total_service_violation", "physical units"),
    ("transportation_cost", "cost units"),
    ("service_penalty_cost", "cost units"),
    ("economic_optimum_recourse_cost", "cost units"),
)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def close(left: float, right: float, tolerance: float = TOL) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=tolerance)


def representative_max(rows: list[dict], metric: str) -> tuple[float, str, list[str]]:
    maximum = max(float(row[metric]) for row in rows)
    tied = [row["scenario_id"] for row in rows if abs(float(row[metric]) - maximum) <= 1e-9]
    return maximum, tied[0], tied


def validate_checkpoint(task: dict, auth: dict, scenario_manifest: dict) -> tuple[dict, dict]:
    task_id = task["task_id"]
    checkpoint_path = RESULT_ROOT / task_id / "checkpoint.json"
    sidecar_path = checkpoint_path.with_suffix(".json.sha256")
    if not checkpoint_path.is_file() or not sidecar_path.is_file():
        raise ValueError(f"missing checkpoint or sidecar: {task_id}")
    checkpoint_hash = sha256(checkpoint_path)
    recorded_hash = sidecar_path.read_text(encoding="utf-8").strip().split()[0].lower()
    if checkpoint_hash != recorded_hash:
        raise ValueError(f"checkpoint sidecar mismatch: {task_id}")

    checkpoint = load_json(checkpoint_path)
    expected_instance = next(item for item in scenario_manifest["cases"] if item["case_id"] == task["case_id"])
    expected = {
        "classification": "FORMAL_COMMON_SCENARIO_RESULT",
        "task_id": task_id,
        "case_id": task["case_id"],
        "policy_id": task["policy_id"],
        "policy_sha256": task["policy_sha256"],
        "instance_sha256": expected_instance["instance_sha256"],
        "authorization_manifest_sha256": sha256(AUTH_PATH),
        "scenario_manifest_sha256": sha256(SCENARIO_PATH),
        "identity_manifest_sha256": sha256(IDENTITY_PATH),
        "scenario_count": 4657,
        "threads": 1,
    }
    for key, value in expected.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"{task_id}: {key} mismatch")
    for path, recorded in auth["identity_file_sha256"].items():
        if sha256(ROOT / path) != recorded:
            raise ValueError(f"authorization identity hash mismatch: {path}")
    if checkpoint["runner_sha256"] != auth["identity_file_sha256"]["experiments/run_e2_stockout_common_scenario.py"]:
        raise ValueError(f"{task_id}: runner identity mismatch")
    if checkpoint["evaluator_sha256"] != auth["identity_file_sha256"]["src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py"]:
        raise ValueError(f"{task_id}: evaluator identity mismatch")

    evaluation = checkpoint["evaluation"]
    rows = evaluation["scenarios"]
    ids = [row.get("scenario_id") for row in rows]
    counts = Counter(ids)
    if len(rows) != 4657 or set(ids) != set(SCENARIO_IDS) or ids != list(SCENARIO_IDS):
        raise ValueError(f"{task_id}: incomplete, unknown, duplicate, or out-of-order scenarios")
    if any(count != 1 for count in counts.values()):
        raise ValueError(f"{task_id}: duplicate scenario IDs")
    expected_id_hash = canonical_sha256(list(SCENARIO_IDS))
    if checkpoint["scenario_id_order_sha256"] != expected_id_hash:
        raise ValueError(f"{task_id}: frozen scenario ID order hash mismatch")
    if evaluation["policy_coordinates_before_sha256"] != task["policy_sha256"]:
        raise ValueError(f"{task_id}: pre-evaluation first-stage identity mismatch")
    if evaluation["policy_coordinates_after_sha256"] != task["policy_sha256"]:
        raise ValueError(f"{task_id}: first-stage coordinates changed")
    if evaluation["unique_product_local_blocks"] != 632:
        raise ValueError(f"{task_id}: product-local block count mismatch")

    required_metrics = {metric for metric, _ in METRICS} | {"recourse_cost"}
    for row in rows:
        if row.get("solver_status") != "OPTIMAL":
            raise ValueError(f"{task_id}/{row.get('scenario_id')}: non-OPTIMAL status")
        for metric in required_metrics:
            value = row.get(metric)
            if value is None or not math.isfinite(float(value)):
                raise ValueError(f"{task_id}/{row['scenario_id']}: missing/nonfinite {metric}")
        components = row["transportation_cost"] + row["shortage_penalty_cost"] + row["service_penalty_cost"]
        if not close(row["recourse_cost"], components):
            raise ValueError(f"{task_id}/{row['scenario_id']}: recourse decomposition mismatch")

    fallback_events = evaluation.get("fallback_events", [])
    if evaluation.get("fallback_count") != len(fallback_events):
        raise ValueError(f"{task_id}: fallback count mismatch")
    fallback_fields = {
        "case_id", "policy_id", "product_index", "shocked_region_indices",
        "original_tie_break_delta", "economic_stage_max_primal_violation",
        "frozen_feasibility_tolerance", "reported_solution_source",
    }
    for event in fallback_events:
        if not fallback_fields.issubset(event):
            raise ValueError(f"{task_id}: incomplete fallback event")
        if event["reported_solution_source"] != "ECONOMIC_STAGE":
            raise ValueError(f"{task_id}: invalid fallback solution source")
        if event["economic_stage_max_primal_violation"] > event["frozen_feasibility_tolerance"]:
            raise ValueError(f"{task_id}: fallback violates frozen feasibility tolerance")

    summary = checkpoint["metric_summary"]
    if summary.get("coverage_status") != "COMPLETE_FROZEN_SCENARIO_SET":
        raise ValueError(f"{task_id}: incomplete coverage status")
    if summary.get("scenario_id_set_sha256") != expected_id_hash or summary.get("scenario_id_order_sha256") != expected_id_hash:
        raise ValueError(f"{task_id}: summary scenario identity mismatch")
    nominal = rows[0]
    for metric, _ in METRICS:
        if not close(summary["nominal_common_scenario"][metric], nominal[metric]):
            raise ValueError(f"{task_id}: nominal {metric} mismatch")
    for metric in ("total_shortage", "total_service_violation", "shortage_penalty_cost", "economic_optimum_recourse_cost"):
        value, representative, tied = representative_max(rows, metric)
        stored = summary["worst_over_frozen_set"][metric]
        if not close(stored["value"], value) or stored["representative_scenario_id"] != representative:
            raise ValueError(f"{task_id}: worst {metric} mismatch")
        if stored["tied_scenario_ids"] != tied or stored["tie_count"] != len(tied):
            raise ValueError(f"{task_id}: worst {metric} tie metadata mismatch")

    recomputed = {
        "nominal": {metric: float(nominal[metric]) for metric, _ in METRICS},
        "mean": {metric: sum(float(row[metric]) for row in rows) / len(rows) for metric, _ in METRICS},
        "worst": {},
    }
    for metric, _ in METRICS:
        value, representative, tied = representative_max(rows, metric)
        recomputed["worst"][metric] = {
            "value": value,
            "representative_scenario_id": representative,
            "tie_count": len(tied),
        }
    record = {
        "task_id": task_id,
        "case_id": task["case_id"],
        "policy_role": "EXISTING" if "EXISTING" in task_id else "ROBUST",
        "checkpoint_path": checkpoint_path.relative_to(ROOT).as_posix(),
        "checkpoint_sha256": checkpoint_hash,
        "runtime_seconds": checkpoint["runtime_seconds"],
        "fallback_count": evaluation["fallback_count"],
        "fallback_max_primal_violation": max(
            (event["economic_stage_max_primal_violation"] for event in fallback_events), default=0.0
        ),
        "frozen_feasibility_tolerance": max(
            (event["frozen_feasibility_tolerance"] for event in fallback_events), default=None
        ),
        "status": "PASS",
    }
    return record, recomputed


def main() -> None:
    auth = load_json(AUTH_PATH)
    identity = load_json(IDENTITY_PATH)
    scenario_manifest = load_json(SCENARIO_PATH)
    if auth.get("formal_run_authorized") is not True:
        raise ValueError("V2R1 authorization record is not true")
    if auth.get("authorized_task_ids") != [f"E2S-{case}-{policy}" for case in CASES for policy in POLICIES]:
        raise ValueError("authorization task set/order mismatch")
    if auth.get("identity_manifest_payload_sha256") != identity.get("manifest_payload_sha256"):
        raise ValueError("identity manifest payload mismatch")
    if auth.get("scenario_manifest_payload_sha256") != scenario_manifest.get("manifest_payload_sha256"):
        raise ValueError("scenario manifest payload mismatch")
    if scenario_manifest.get("gamma") != 2 or scenario_manifest.get("threads") != 1:
        raise ValueError("frozen Gamma/threads mismatch")

    planned = {task["task_id"]: task for task in auth["planned_tasks"]}
    task_records: list[dict] = []
    metrics_by_task: dict[str, dict] = {}
    for task_id in auth["authorized_task_ids"]:
        record, metrics = validate_checkpoint(planned[task_id], auth, scenario_manifest)
        task_records.append(record)
        metrics_by_task[task_id] = metrics

    expected_archive_entries = {
        f"e2_stockout_common_scenario_formal_v2r1/{path.relative_to(RESULT_ROOT).as_posix()}"
        for path in RESULT_ROOT.rglob("*") if path.is_file()
    }
    with zipfile.ZipFile(ARCHIVE_PATH) as archive:
        if set(archive.namelist()) != expected_archive_entries:
            raise ValueError("formal archive entry set mismatch")
        for entry in expected_archive_entries:
            disk_path = RESULT_ROOT / Path(entry).relative_to("e2_stockout_common_scenario_formal_v2r1")
            if hashlib.sha256(archive.read(entry)).hexdigest() != sha256(disk_path):
                raise ValueError(f"formal archive byte mismatch: {entry}")
    expected_resource_entries = {
        f"e2_stockout_resource_preflight_v2r1/{path.relative_to(RESOURCE_RESULT_ROOT).as_posix()}"
        for path in RESOURCE_RESULT_ROOT.rglob("*") if path.is_file()
    }
    with zipfile.ZipFile(RESOURCE_ARCHIVE_PATH) as archive:
        if set(archive.namelist()) != expected_resource_entries:
            raise ValueError("resource preflight archive entry set mismatch")
        for entry in expected_resource_entries:
            disk_path = RESOURCE_RESULT_ROOT / Path(entry).relative_to("e2_stockout_resource_preflight_v2r1")
            if hashlib.sha256(archive.read(entry)).hexdigest() != sha256(disk_path):
                raise ValueError(f"resource preflight archive byte mismatch: {entry}")
    resource_checkpoint_path = RESOURCE_RESULT_ROOT / "PREFLIGHT-210202-EXISTING/checkpoint.json"
    resource_sidecar_path = resource_checkpoint_path.with_suffix(".json.sha256")
    resource_manifest_path = resource_checkpoint_path.parent / "result_manifest.json"
    resource_checkpoint = load_json(resource_checkpoint_path)
    resource_manifest = load_json(resource_manifest_path)
    resource_audit = load_json(RESOURCE_AUDIT_PATH)
    resource_checkpoint_hash = sha256(resource_checkpoint_path)
    if resource_sidecar_path.read_text(encoding="utf-8").strip().split()[0].lower() != resource_checkpoint_hash:
        raise ValueError("resource preflight checkpoint sidecar mismatch")
    if resource_manifest["checkpoint_sha256"] != resource_checkpoint_hash:
        raise ValueError("resource preflight result manifest checkpoint mismatch")
    if resource_audit["preflight_checkpoint_sha256"] != resource_checkpoint_hash:
        raise ValueError("resource preflight audit checkpoint mismatch")
    if resource_audit["preflight_result_manifest_sha256"] != sha256(resource_manifest_path):
        raise ValueError("resource preflight audit result-manifest mismatch")
    expected_resource_values = {
        "classification": "PREFLIGHT_NON_PUBLISHABLE",
        "formal_run_authorized": False,
        "completion_status": "COMPLETE",
        "completed_blocks": 632,
        "total_blocks": 632,
        "scenario_count": 4657,
        "threads": 1,
        "protocol_interrupt_exercised": True,
    }
    for key, value in expected_resource_values.items():
        if resource_checkpoint.get(key) != value:
            raise ValueError(f"resource preflight checkpoint mismatch: {key}")
    if resource_checkpoint["policy_coordinates_before_sha256"] != resource_checkpoint["policy_sha256"]:
        raise ValueError("resource preflight before-policy identity mismatch")
    if resource_checkpoint["policy_coordinates_after_sha256"] != resource_checkpoint["policy_sha256"]:
        raise ValueError("resource preflight changed first-stage coordinates")
    if resource_checkpoint["preflight_authorization_sha256"] != sha256(RESOURCE_AUTH_PATH):
        raise ValueError("resource preflight historical authorization mismatch")

    rows_out: list[dict] = []
    for case in CASES:
        existing = metrics_by_task[f"E2S-{case}-EXISTING"]
        robust = metrics_by_task[f"E2S-{case}-ROBUST"]
        for aggregation in ("nominal", "mean", "worst"):
            for metric, unit in METRICS:
                existing_data = existing[aggregation][metric]
                robust_data = robust[aggregation][metric]
                if aggregation == "worst":
                    existing_value = existing_data["value"]
                    robust_value = robust_data["value"]
                    existing_scenario = existing_data["representative_scenario_id"]
                    robust_scenario = robust_data["representative_scenario_id"]
                else:
                    existing_value = existing_data
                    robust_value = robust_data
                    existing_scenario = "S0000" if aggregation == "nominal" else ""
                    robust_scenario = "S0000" if aggregation == "nominal" else ""
                change = robust_value - existing_value
                percent = "NA" if abs(existing_value) <= 1e-9 else 100.0 * change / existing_value
                rows_out.append({
                    "case_id": case,
                    "metric": metric,
                    "aggregation": "arithmetic_mean_over_unweighted_enumerated_set" if aggregation == "mean" else aggregation,
                    "unit": unit,
                    "existing_value": existing_value,
                    "robust_value": robust_value,
                    "absolute_change_robust_minus_existing": change,
                    "percent_change_vs_existing": percent,
                    "existing_representative_scenario_id": existing_scenario,
                    "robust_representative_scenario_id": robust_scenario,
                    "existing_task_id": f"E2S-{case}-EXISTING",
                    "robust_task_id": f"E2S-{case}-ROBUST",
                })

        robust_source = next(
            policy for policy in identity["policies"]
            if policy["case_id"] == case and policy["policy_id"].startswith("ROBUST_EQUIVALENT")
        )
        robust_result = load_json(ROOT / robust_source["certification_source_path"])
        existing_reconfiguration = 0.0
        robust_reconfiguration = robust_result.get("reconfiguration_spending")
        percent = "NA"  # Frozen denominator is zero; no percentage is defined.
        rows_out.append({
            "case_id": case,
            "metric": "first_stage_reconfiguration_spending",
            "aggregation": "frozen_policy_source_record",
            "unit": "cost units",
            "existing_value": existing_reconfiguration,
            "robust_value": robust_reconfiguration,
            "absolute_change_robust_minus_existing": robust_reconfiguration,
            "percent_change_vs_existing": percent,
            "existing_representative_scenario_id": "",
            "robust_representative_scenario_id": "",
            "existing_task_id": f"E2S-{case}-EXISTING",
            "robust_task_id": f"E2S-{case}-ROBUST",
        })

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_out[0]))
        writer.writeheader()
        writer.writerows(rows_out)

    audit = {
        "schema_version": "1.0",
        "classification": "READ_ONLY_ACCEPTANCE_AUDIT_NO_OPTIMIZATION",
        "experiment_version": "V2R1",
        "status": "PASS",
        "task_count": len(task_records),
        "scenario_count_per_task": 4657,
        "total_scenario_rows": 4657 * len(task_records),
        "gamma": 2,
        "solver_versions": sorted({load_json(ROOT / record["checkpoint_path"])["solver_version"] for record in task_records}),
        "threads": 1,
        "authorization_manifest": {
            "path": AUTH_PATH.relative_to(ROOT).as_posix(),
            "sha256": sha256(AUTH_PATH),
            "formal_run_authorized_recorded": True,
        },
        "identity_manifest": {"path": IDENTITY_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(IDENTITY_PATH)},
        "scenario_manifest": {"path": SCENARIO_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(SCENARIO_PATH)},
        "checks": {
            "all_16_authorized_tasks_present": True,
            "checkpoint_sidecars_match": True,
            "all_tasks_have_exact_frozen_4657_id_set_and_order": True,
            "all_scenario_solver_statuses_optimal": True,
            "all_required_metrics_finite": True,
            "recourse_cost_components_reconcile": True,
            "first_stage_policy_hash_unchanged_before_after": True,
            "all_tasks_have_632_unique_product_local_blocks": True,
            "fallback_events_complete_and_feasible": True,
            "stored_nominal_and_four_formal_worst_summaries_recomputed": True,
            "formal_archive_32_entries_byte_identical_to_result_root": True,
            "resource_preflight_archive_3_entries_byte_identical_to_result_root": True,
            "resource_preflight_checkpoint_sidecar_and_result_manifest_match": True,
            "resource_preflight_complete_632_blocks_with_interrupt_resume": True,
            "resource_preflight_historical_authorization_snapshot_matches": True,
        },
        "fallback_event_total": sum(record["fallback_count"] for record in task_records),
        "maximum_fallback_original_constraint_violation": max(record["fallback_max_primal_violation"] for record in task_records),
        "task_records": task_records,
        "derived_policy_comparison": {
            "path": OUTPUT_CSV.relative_to(ROOT).as_posix(),
            "sha256": sha256(OUTPUT_CSV),
            "row_count": len(rows_out),
            "mean_semantics": "arithmetic mean over the 4,657 equally enumerated scenarios; not an expectation",
        },
    }
    OUTPUT_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    delivery_paths = (
        "artifacts/e2_stockout_common_scenario_formal_v2r1_results.zip",
        "artifacts/e2_stockout_resource_preflight_v2r1.zip",
        "artifacts/e2_stockout_policy_identity_manifest.json",
        "docs/e2_stockout_common_scenario_protocol.md",
        "docs/e2_stockout_scientific_policy_confirmation.md",
        "docs/e2_stockout_v2r1_formal_audit.md",
        "docs/section5_sensitivity_evidence_inventory.md",
        "docs/section5_2_to_5_3_narrative_bridge.md",
        "docs/section5_2_5_3_chinese_draft.md",
        "experiments/analysis/e2_stockout_v2r1_policy_comparison.csv",
        "experiments/audits/e2_stockout_resource_preflight_v2r1.json",
        "experiments/audits/e2_stockout_v2r1_acceptance.json",
        "experiments/configs/e2_stockout_common_scenario_manifest.json",
        "experiments/configs/e2_stockout_formal_authorization_v2r1.json",
        "experiments/configs/e2_stockout_resource_preflight_authorization_v2r1.json",
        "experiments/run_e2_stockout_common_scenario.py",
        "experiments/schemas/e2_stockout_formal_checkpoint.schema.json",
        "experiments/schemas/e2_stockout_scenario_result.schema.json",
        "scripts/audit_e2_stockout_v2r1_archive.py",
        "src/robust_inventory_reconfiguration/e2_stockout_common_scenario.py",
    )
    hash_manifest = {
        "schema_version": "1.0",
        "classification": "E2_V2R1_ARCHIVE_DELIVERY_SHA256",
        "files": [
            {"path": path, "size_bytes": (ROOT / path).stat().st_size, "sha256": sha256(ROOT / path)}
            for path in delivery_paths
        ],
    }
    OUTPUT_HASHES.write_text(json.dumps(hash_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "tasks": len(task_records), "rows": len(rows_out), "fallback_events": audit["fallback_event_total"]}))


if __name__ == "__main__":
    main()
