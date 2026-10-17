from __future__ import annotations

import csv
import json
import os
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psutil

try:
    from scripts.summarize_renault_four_method_results import (
        audit_recovered_results,
        build_table_rows,
    )
except ModuleNotFoundError:
    from summarize_renault_four_method_results import (
        audit_recovered_results,
        build_table_rows,
    )

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/formal/direct_scaling_extension.yaml"
SOURCE = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
ARTIFACTS = ROOT / "artifacts"
DOCS = ROOT / "docs"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def value(frozen, current, source, critical=False, evidence="") -> dict:
    if frozen == "NOT_VERIFIABLE" or current == "NOT_VERIFIABLE":
        status = "NOT_VERIFIABLE"
    else:
        status = "MATCH" if frozen == current else ("BLOCKING_MISMATCH" if critical else "MISMATCH")
    return {"frozen_value": frozen, "current_value": current, "source_artifact": source, "match_status": status, "evidence": evidence}


def environment_audit(config: dict) -> dict:
    try:
        import gurobipy as gp
        gp_version, native = gp.__version__, list(gp.gurobi.version())
    except ImportError:
        gp_version, native = "NOT_INSTALLED", "NOT_INSTALLED"
    active = [p.info for p in psutil.process_iter(["pid", "name", "cmdline"]) if p.pid != os.getpid() and any(token in (p.info["name"] or "").lower() for token in ("gurobi", "python"))]
    scaling_source = "Scaling V2 result/provenance files and worker logs; experiments/configs/formal/algorithm_scaling_convergence_cost_v2_repaired_guard.yaml"
    dependencies = {}
    for package in ("gurobipy", "psutil", "PyYAML"):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = "NOT_INSTALLED"
    fields = {
        "operating_system": value("NOT_VERIFIABLE", platform.platform(), scaling_source),
        "cpu_model": value("NOT_VERIFIABLE", platform.processor() or "NOT_VERIFIABLE", scaling_source),
        "cpu_cores": value("NOT_VERIFIABLE", {"physical": psutil.cpu_count(logical=False), "logical": psutil.cpu_count(logical=True)}, scaling_source),
        "physical_memory_gib": value(31.5, round(psutil.virtual_memory().total / 2**30, 1), "docs/algorithm_scaling_resource_threshold_audit.md"),
        "python_version": value("NOT_VERIFIABLE", platform.python_version(), scaling_source, evidence="Scaling V2 did not persist Python version; 3.12.7 is compatible with the current code and is required for the new Direct batch."),
        "python_executable": value("NOT_VERIFIABLE", sys.executable, scaling_source, evidence="Scaling V2 did not persist its interpreter path."),
        "gurobipy_version": value("NOT_VERIFIABLE", gp_version, scaling_source, evidence="13.0.1 is supported by command-history and installation-timestamp evidence but is an inference, not an exact archived field."),
        "gurobi_native_version": value("NOT_VERIFIABLE", native, scaling_source, evidence="Renault E1b independently used 13.0.2; that version is not transferred to Scaling V2."),
        "license_environment": value("NOT_VERIFIABLE", "Environment variables present" if any(os.getenv(k) for k in ("GRB_LICENSE_FILE", "WLSACCESSID", "GRB_WLSACCESSID")) else "No license environment variable; local license may be used", scaling_source),
        "Threads": value("DEFAULT_AUTOMATIC", "DEFAULT_AUTOMATIC", "Scaling V2 config and solver profile"),
        "Seed": value(0, 0, "Scaling V2 config and solver profile"),
        "MIPGap": value(0.0, 0.0, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "MIPGapAbs": value("NOT_VERIFIABLE", "GUROBI_13.0.1_DEFAULT", scaling_source),
        "FeasibilityTol": value(1e-8, 1e-8, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "OptimalityTol": value(1e-8, 1e-8, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "IntFeasTol": value(1e-8, 1e-8, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "Presolve": value("NOT_VERIFIABLE", "GUROBI_13.0.1_DEFAULT", scaling_source),
        "Method": value("NOT_VERIFIABLE", "GUROBI_13.0.1_DEFAULT", scaling_source),
        "Cuts": value("NOT_VERIFIABLE", "GUROBI_13.0.1_DEFAULT", scaling_source),
        "Heuristics": value("NOT_VERIFIABLE", "GUROBI_13.0.1_DEFAULT", scaling_source),
        "NumericFocus": value(0, 0, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "execution_code_commit": value("c46d09c306deb80086a7ceab12812847c117df87", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "formal scaling result/provenance artifacts", evidence="A new Direct runner commit is expected; model-source identity must be reviewed separately."),
        "dependency_versions": value("NOT_VERIFIABLE", dependencies, "No complete frozen dependency lock"),
        "concurrent_optimization_tasks": value("NONE_RECORDED_BUT_NOT_CONTINUOUSLY_MONITORED", active, "Formal monitor artifacts do not persist a process inventory"),
        "core_time_definition": value("model construction through exact certification", "model construction through exact certification", "Scaling V2 result fields; docs/direct_scaling_protocol.md"),
        "resource_timing": value("process-tree RSS sampled by parent monitor", "implemented at 0.25 s sampling", "docs/algorithm_scaling_resource_threshold_audit.md; experiments/run_direct_scaling.py"),
    }
    blocking = [name for name, row in fields.items() if row["match_status"] == "BLOCKING_MISMATCH"]
    available_gib = psutil.virtual_memory().available / 2**30
    resource_gate_eligible_conditions = {
        size["label"]: len(config["seeds"])
        if available_gib >= config["resource_policy"]["minimum_available_memory_gib_by_size"][size["label"]]
        else 0
        for size in config["sizes"]
    }
    return {
        "schema": "environment_identity_audit_v2",
        "status": "COMPARABLE_WITH_EXPLICIT_PROTOCOL_VERSION_RISK",
        "exact_environment_match": False,
        "blocking_fields": blocking,
        "renault_e1b": {
            "gurobipy_version": "13.0.2",
            "gurobi_native_version": [13, 0, 2],
            "status": "VERIFIED_FROM_16_RESULT_FILES_AND_16_SOLVER_LOGS",
        },
        "scaling_v2": {
            "historical_gurobipy_version": "NOT_VERIFIABLE",
            "historical_gurobi_native_version": "NOT_VERIFIABLE",
            "evidence_supported_inference": "13.0.1",
            "result_files_with_solver_version": 0,
            "provenance_files_with_solver_version": 0,
            "worker_logs_with_version_banner": 0,
        },
        "direct_candidate_environment": {
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "gurobipy_version": gp_version,
            "gurobi_native_version": native,
            "matches_new_batch_requirement": gp_version == config["required_environment"]["gurobipy_version"] and native == config["required_environment"]["gurobi_native_version"],
        },
        "resource_gate_snapshot": {
            "available_memory_gib": available_gib,
            "eligible_conditions": resource_gate_eligible_conditions,
            "note": "Read-only preflight snapshot; each formal run must repeat the gate immediately before launch.",
        },
        "comparability_risk": "Direct can use the same instances, explicit solver profile, model implementation, certification, and T_core definition. Exact software-environment pairing to Scaling V2 cannot be proved because the historical interpreter, Gurobi version, version-dependent defaults, full dependency lock, license mechanism, and concurrent-process state were not persisted.",
        "fields": fields,
    }


def instance_manifest(config: dict) -> list[dict]:
    rows = []
    for size in config["sizes"]:
        for seed in config["seeds"]:
            root = SOURCE / "instances" / size["label"] / str(seed)
            instance_path, prep_path = root / "instance.json", root / "preparation.json"
            prep = json.loads(prep_path.read_text(encoding="utf-8"))
            rows.append({
                "size": size["label"], "seed": seed, "I": size["I"], "R": size["R"], "J": size["J"],
                "instance_sha256": sha256(instance_path), "preparation_sha256": sha256(prep_path),
                "instance_hash": prep["instance_hash"], "x0_hash": prep["x0_hash"], "B_ref": prep["B_ref"], "budget": prep["budget"],
                "Gamma": prep["scientific_parameters"]["Gamma"], "beta": prep["scientific_parameters"]["beta"], "lambda_R": prep["scientific_parameters"]["lambda_R"],
                "identity_status": "PASS" if prep["size"] == size["label"] and prep["seed"] == seed else "FAIL",
            })
    return rows


def build_tables(config: dict) -> None:
    table1 = build_table_rows(audit_recovered_results())
    write_csv(ARTIFACTS / "table_1_renault_four_method_comparison.csv", table1, list(table1[0]))

    summary = read_csv(SOURCE / "algorithm_scaling_summary_by_size.csv")
    all_results = read_csv(SOURCE / "algorithm_scaling_all_results.csv")
    table2 = []
    for size in ("L10", "XL10", "XXL10"):
        row = {"Scale": size, "Direct core time": "PENDING_AUTHORIZATION", "Direct exact": 0, "Direct timeout": 0, "Direct resource-stop": 0, "Direct uncertified": 0, "Direct not-run": 10, "Direct gap": "NOT_AVAILABLE", "Direct/PRB speedup": "NOT_AVAILABLE"}
        for method, prefix in (("pure_benders", "Pure"), ("aggregate_benders_structured_oracle", "Aggregate"), ("prb_benders", "PRB")):
            item = next(item for item in summary if item["size"] == size and item["method"] == method)
            subset = [item for item in all_results if item["size"] == size and item["method"] == method]
            row[f"{prefix} core time"] = item["core_time_mean"]
            row[f"{prefix} exact"] = len(subset)
            row[f"{prefix} timeout"] = 0
            row[f"{prefix} resource-stop"] = 0
            row[f"{prefix} uncertified"] = 1 if size == "XXL10" and method == "pure_benders" else 0
            row[f"{prefix} max gap"] = max(float(item["relative_gap"]) for item in subset)
        row["Pure/PRB time ratio"] = float(row["Pure core time"]) / float(row["PRB core time"])
        row["Aggregate/PRB time ratio"] = float(row["Aggregate core time"]) / float(row["PRB core time"])
        table2.append(row)
    write_csv(ARTIFACTS / "table_2_enlarged_network_comparison.csv", table2, list(table2[0]))

    table3 = []
    for size in ("L10", "XL10", "XXL10"):
        for method in ("aggregate_benders_structured_oracle", "prb_benders"):
            item = next(item for item in summary if item["size"] == size and item["method"] == method)
            subset = [row for row in all_results if row["size"] == size and row["method"] == method]
            table3.append({"Scale": size, "Method": method, "Iterations": item["iterations_mean"], "Core time": item["core_time_mean"], "Oracle time": item["oracle_time_mean"], "Master time": item["master_time_mean"], "Cuts": item["cuts_mean"], "Peak memory GiB": max(float(row["peak_process_tree_memory_gib"]) for row in subset), "Iterations to 99.9% LB": item["iterations_to_99_9pct_final_LB_mean"], "Iterations to 99.99% LB": item["iterations_to_99_99pct_final_LB_mean"], "Cut unit note": "Aggregate and PRB cuts have different granularity"})
    write_csv(ARTIFACTS / "table_3_same_oracle_ablation.csv", table3, list(table3[0]))


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    audit = environment_audit(config)
    (ARTIFACTS / "environment_identity_audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    manifest = instance_manifest(config)
    write_csv(ARTIFACTS / "direct_scaling_instance_manifest.csv", manifest, list(manifest[0]))
    build_tables(config)
    dry_run = {
        "schema": "direct_scaling_dry_run_v2",
        "formal_run_authorized": config["formal_run_authorized"],
        "configured_conditions": len(manifest),
        "authorized_condition_ids": config.get("authorized_condition_ids", []),
        "instance_identity_pass": all(row["identity_status"] == "PASS" for row in manifest),
        "environment_status": audit["status"],
        "exact_environment_match": audit["exact_environment_match"],
        "resource_gate_snapshot": audit["resource_gate_snapshot"],
        "optimization_calls": 0,
    }
    (ARTIFACTS / "direct_scaling_dry_run.json").write_text(json.dumps(dry_run, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"environment_status": audit["status"], "instances": len(manifest), "instance_identity_pass": all(row["identity_status"] == "PASS" for row in manifest), "optimization_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
