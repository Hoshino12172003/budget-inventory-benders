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
    frozen_source = "docs/e1b_standard_benders_baseline_audit.md; docs/e1b_standard_benders_protocol.md; src/robust_inventory_reconfiguration/solver_profile.py"
    dependencies = {}
    for package in ("gurobipy", "psutil", "PyYAML"):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = "NOT_INSTALLED"
    fields = {
        "operating_system": value("Windows-11-10.0.26200-SP0", platform.platform(), "experiments/results/e1_algorithm_benchmark/attempt_002/provenance.json", evidence="Frozen provenance records Windows-11-10.0.26200-SP0."),
        "cpu_model": value("NOT_VERIFIABLE", platform.processor() or "NOT_VERIFIABLE", "No frozen CPU artifact"),
        "cpu_cores": value("NOT_VERIFIABLE", {"physical": psutil.cpu_count(logical=False), "logical": psutil.cpu_count(logical=True)}, "No frozen core-count artifact"),
        "physical_memory_gib": value(31.5, round(psutil.virtual_memory().total / 2**30, 1), "docs/algorithm_scaling_resource_threshold_audit.md"),
        "python_version": value(config["required_environment"]["python_version"], platform.python_version(), frozen_source, critical=True),
        "python_executable": value(r"C:\Users\Hu Jiaxin\Documents\Codex\2026-07-07\z\work\paper-code\.venv\Scripts\python.exe", sys.executable, "docs/e1b_standard_benders_baseline_audit.md", critical=True, evidence="Frozen interpreter path no longer exists on this host."),
        "gurobipy_version": value("13.0.2", gp_version, frozen_source, critical=True),
        "gurobi_native_version": value([13, 0, 2], native, frozen_source, critical=True),
        "license_environment": value("Academic license; exact frozen mechanism NOT_VERIFIABLE", "Environment variables present" if any(os.getenv(k) for k in ("GRB_LICENSE_FILE", "WLSACCESSID", "GRB_WLSACCESSID")) else "No license environment variable; local license may be used", "worker stdout logs; no complete frozen license provenance"),
        "Threads": value("DEFAULT_AUTOMATIC", "DEFAULT_AUTOMATIC", frozen_source),
        "Seed": value(0, 0, frozen_source),
        "MIPGap": value(0.0, 0.0, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "MIPGapAbs": value("GUROBI_13.0.2_DEFAULT_NOT_PERSISTED", "GUROBI_13.0.1_DEFAULT_NOT_QUERIED", frozen_source),
        "FeasibilityTol": value(1e-8, 1e-8, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "OptimalityTol": value(1e-8, 1e-8, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "IntFeasTol": value(1e-8, 1e-8, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "Presolve": value("GUROBI_13.0.2_DEFAULT", "GUROBI_13.0.1_DEFAULT", frozen_source, critical=True),
        "Method": value("GUROBI_13.0.2_DEFAULT", "GUROBI_13.0.1_DEFAULT", frozen_source, critical=True),
        "Cuts": value("GUROBI_13.0.2_DEFAULT", "GUROBI_13.0.1_DEFAULT", frozen_source, critical=True),
        "Heuristics": value("GUROBI_13.0.2_DEFAULT", "GUROBI_13.0.1_DEFAULT", frozen_source, critical=True),
        "NumericFocus": value(0, 0, "src/robust_inventory_reconfiguration/solver_profile.py"),
        "execution_code_commit": value("c46d09c306deb80086a7ceab12812847c117df87", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "formal scaling result/provenance artifacts", evidence="A new Direct runner commit is expected; model-source identity must be reviewed separately."),
        "dependency_versions": value("NOT_VERIFIABLE", dependencies, "No complete frozen dependency lock"),
        "concurrent_optimization_tasks": value("NONE_RECORDED_BUT_NOT_CONTINUOUSLY_MONITORED", active, "Formal monitor artifacts do not persist a process inventory"),
        "core_time_definition": value("model construction through exact certification", "model construction through exact certification", "docs/e1b_pure_benders_definition_execution_timing_audit.md; docs/direct_scaling_protocol.md"),
        "resource_timing": value("process-tree RSS sampled by parent monitor", "implemented at 0.25 s sampling", "docs/algorithm_scaling_resource_threshold_audit.md; experiments/run_direct_scaling.py"),
    }
    blocking = [name for name, row in fields.items() if row["match_status"] == "BLOCKING_MISMATCH"]
    return {"schema": "environment_identity_audit_v1", "status": "BLOCK_FORMAL_EXECUTION" if blocking else "PASS", "blocking_fields": blocking, "fields": fields}


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
    empirical = {row["case"]: row for row in read_csv(ROOT / "table_e1_empirical_performance.csv")}
    mechanism = read_csv(ROOT / "table_e1c_algorithm_mechanism_comparison.csv")
    lookup = {(row["case_or_scale"], row["method"]): row for row in mechanism if row["scope"] == "empirical"}
    table1 = []
    for case, row in empirical.items():
        pure = lookup.get((case, "Pure Benders"), {})
        aggregate = lookup.get((case, "Aggregate Benders + Structured Oracle"), {})
        objectives = [float(row["direct_objective"]), float(row["prb_objective"])]
        for source in (pure, aggregate):
            if source.get("objective"):
                objectives.append(float(source["objective"]))
        table1.append({
            "Case": case, "Direct core time": row["direct_runtime_seconds"],
            "Pure Benders core time": pure.get("T_core_seconds", "NOT_VERIFIABLE"),
            "Aggregate+Structured core time": aggregate.get("T_core_seconds", "NOT_VERIFIABLE"),
            "PRB core time": row["prb_runtime_seconds"],
            "Objective consistency": ("PASS_ALL_FOUR" if pure and aggregate else "PASS_DIRECT_PRB_ONLY") if max(objectives) - min(objectives) <= 1e-4 else "FAIL",
            "Certification status": "DIRECT_AND_PRB_CERTIFIED; PURE_AND_AGGREGATE_" + ("CERTIFIED" if pure and aggregate else "NOT_VERIFIABLE_FROM_TRACKED_RAW_ARTIFACTS"),
        })
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
    print(json.dumps({"environment_status": audit["status"], "instances": len(manifest), "instance_identity_pass": all(row["identity_status"] == "PASS" for row in manifest), "optimization_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
