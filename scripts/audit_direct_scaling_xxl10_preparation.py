from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from math import comb
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_direct_scaling as runner
from scripts.freeze_direct_scaling_l10_xl10 import build_freeze, sha256


CONFIG = ROOT / "experiments/configs/formal/direct_scaling_xxl10_low_memory_pilot_v1.yaml"
DIRECT = ROOT / "experiments/results/direct_scaling_extension_v1"
SCALING = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
FROZEN_SHA_AUDIT = ROOT / "artifacts/direct_scaling_l10_xl10_sha256_audit.csv"
OUTPUT = ROOT / "artifacts/direct_scaling_xxl10_preparation_audit.json"
REPORT = ROOT / "docs/direct_scaling_xxl10_pilot_readiness.md"


def theoretical_direct_size(I: int, R: int, J: int, gamma: int) -> dict:
    scenario_patterns_per_product = sum(comb(R, value) for value in range(gamma + 1))
    risk_allocations = comb(J + gamma, gamma)
    variables = I + 3 * I * J + J * (gamma + 1) + 1
    variables += J * scenario_patterns_per_product * (I * R + R + 1)
    constraints = I + 2 * I * J + 1
    constraints += J * scenario_patterns_per_product * (R + I + 2)
    constraints += risk_allocations
    nonzeros = 9 * I * J + 2 * I
    nonzeros += J * scenario_patterns_per_product * (3 * I * R + I + 3 * R + 3)
    nonzeros += risk_allocations * (J + 1)
    return {
        "I": I,
        "R": R,
        "J": J,
        "Gamma": gamma,
        "scenario_patterns_per_product": scenario_patterns_per_product,
        "scenario_blocks": J * scenario_patterns_per_product,
        "risk_budget_allocations": risk_allocations,
        "variable_count": variables,
        "binary_variable_count": I,
        "constraint_count": constraints,
        "nonzero_count": nonzeros,
        "evidence_class": "THEORETICAL_EXACT_COUNT_FROM_CURRENT_MODEL_FORMULA_NOT_A_GUROBI_BUILD",
    }


def active_solver_processes() -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        try:
            args = process.info.get("cmdline") or []
            name = (process.info.get("name") or "").lower()
            direct_worker = "--worker" in args and any(
                str(argument).replace("\\", "/").endswith("run_direct_scaling.py")
                for argument in args
            )
            if name.startswith("gurobi") or direct_worker:
                found.append({
                    "pid": process.info["pid"],
                    "name": process.info.get("name"),
                    "rss_gib": process.info["memory_info"].rss / 2**30,
                    "cmdline": args,
                })
        except (psutil.Error, TypeError):
            continue
    return found


def frozen_evidence_audit() -> dict:
    manifest, generated_sha_rows, pairs, summaries = build_freeze()
    with FROZEN_SHA_AUDIT.open(encoding="utf-8", newline="") as stream:
        frozen_rows = list(csv.DictReader(stream))
    frozen_hashes = {(row["path"], row["sha256"]) for row in frozen_rows}
    generated_hashes = {(row["path"], row["sha256"]) for row in generated_sha_rows}
    checks = {
        "sha256_audit_unchanged": frozen_hashes == generated_hashes and len(frozen_rows) == len(generated_sha_rows) == 179,
        "frozen_counts": manifest["counts"] == {"CERTIFIED": 19, "RESOURCE_FAILURE": 1, "TIME_FAILURE": 0, "NUMERICAL_CERTIFICATION_FAILURE": 0, "UNEXECUTED": 0},
        "valid_pairs": len(pairs) == 19,
        "scale_completion": {row["size"]: row["direct_completion_rate"] for row in summaries} == {"L10": 1.0, "XL10": 0.9},
        "xl10_terminal_attempts": manifest["xl10_terminal_failure"]["attempts"] == ["attempt-001", "attempt-002"],
        "xl10_terminal_stops": manifest["xl10_terminal_failure"]["stop_reasons"] == ["RESOURCE_PROCESS_CAP", "RESOURCE_PROCESS_CAP"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"frozen L10/XL10 evidence changed: {checks}")
    return {"status": "PASS", "checks": checks, "sha256_records": len(frozen_rows)}


def input_audit(config: dict) -> list[dict]:
    rows = []
    for condition in runner.conditions(config):
        if condition["size"] != "XXL10":
            continue
        instance, preparation, hashes = runner.verified_input(config, condition)
        rows.append({
            "condition_id": condition["condition_id"],
            "seed": condition["seed"],
            "instance_id": preparation["instance_id"],
            "instance_hash": preparation["instance_hash"],
            "x0_hash": preparation["x0_hash"],
            "instance_sha256": hashes["instance_sha256"],
            "preparation_sha256": hashes["preparation_sha256"],
            "Gamma": preparation["scientific_parameters"]["Gamma"],
            "beta": preparation["scientific_parameters"]["beta"],
            "lambda_R": preparation["scientific_parameters"]["lambda_R"],
            "dimensions": {"I": instance.num_depots, "R": instance.num_regions, "J": instance.num_products},
            "identity_status": "PASS",
        })
    if len(rows) != 10:
        raise RuntimeError(f"expected 10 XXL10 frozen inputs, found {len(rows)}")
    return rows


def historical_count_validation() -> dict:
    expected = {
        "L10": theoretical_direct_size(25, 24, 12, 2),
        "XL10": theoretical_direct_size(30, 30, 14, 2),
    }
    checks = {}
    for size, theoretical in expected.items():
        actual = []
        for seed in range(20260921, 20260931):
            path = DIRECT / "runs" / f"DIRECT_{size}_S{seed}" / "result.json"
            if path.is_file():
                result = json.loads(path.read_text(encoding="utf-8"))
                actual.append((result["variable_count"], result["constraint_count"], result["nonzero_count"]))
        target = (theoretical["variable_count"], theoretical["constraint_count"], theoretical["nonzero_count"])
        checks[size] = {
            "theoretical": target,
            "actual_unique_counts": sorted(set(actual)),
            "matching_archives": sum(row == target for row in actual),
            "formula_matches_all_available_archives": bool(actual) and all(row == target for row in actual),
        }
    if not all(row["formula_matches_all_available_archives"] for row in checks.values()):
        raise RuntimeError(f"Direct model-size formula validation failed: {checks}")
    return checks


def pure_pairing_exception() -> dict:
    status = json.loads((SCALING / "algorithm_scaling_formal_status.json").read_text(encoding="utf-8"))
    failure = next(row for row in status["documented_non_certified"] if row["condition_id"] == "ASC_XXL10_S20260925_PURE_BENDERS")
    checks = {
        "attempted": failure["attempted"] is True,
        "exact_certification_false": failure["exact_certification"] is False,
        "cut_validity_false": failure["cut_validity_certification"] is False,
        "not_resource_failure": failure["resource_stop_reason"] is None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Pure XXL10 pairing exception changed: {checks}")
    return {
        "condition_id": failure["condition_id"],
        "status": "EXCLUDED_FROM_VALID_FOUR_METHOD_PAIRING",
        "failure_category": failure["failure_category"],
        "checks": checks,
    }


def build_audit() -> dict:
    config = runner.load_config(CONFIG)
    authorized = runner.authorized_conditions(config)
    if [row["condition_id"] for row in authorized] != ["DIRECT_XXL10_S20260921"]:
        raise RuntimeError("XXL10 pilot scope changed")
    frozen = frozen_evidence_audit()
    inputs = input_audit(config)
    validation = historical_count_validation()
    model_size = theoretical_direct_size(36, 36, 16, 2)
    xl_size = validation["XL10"]["theoretical"]
    model_size["relative_to_xl10"] = {
        "variables_ratio": model_size["variable_count"] / xl_size[0],
        "constraints_ratio": model_size["constraint_count"] / xl_size[1],
        "nonzeros_ratio": model_size["nonzero_count"] / xl_size[2],
    }
    memory = psutil.virtual_memory()
    resource = config["resource_policy"]
    available_gib = memory.available / 2**30
    free_disk_gib = shutil.disk_usage(DIRECT.parent).free / 2**30
    processes = active_solver_processes()
    preflight = {
        "total_ram_gib": memory.total / 2**30,
        "available_ram_gib": available_gib,
        "audit_process_rss_gib": psutil.Process(os.getpid()).memory_info().rss / 2**30,
        "free_disk_gib": free_disk_gib,
        "active_direct_or_gurobi_processes": processes,
        "startup_memory_gate_gib": resource["minimum_available_memory_gib_by_size"]["XXL10"],
        "process_tree_cap_gib": resource["maximum_process_tree_memory_gib_by_size"]["XXL10"],
        "system_available_floor_gib": resource["minimum_system_available_memory_gib"],
        "minimum_free_disk_gib": resource["minimum_free_disk_gib"],
        "time_limit_seconds": resource["condition_time_limit_seconds"],
        "monitor_interval_seconds": resource["memory_monitor_interval_seconds"],
        "parallel_workers": resource["parallel_workers"],
        "memory_gate_pass": available_gib >= resource["minimum_available_memory_gib_by_size"]["XXL10"],
        "disk_gate_pass": free_disk_gib >= resource["minimum_free_disk_gib"],
        "process_gate_pass": not processes,
    }
    decision = "READY_FOR_SINGLE_PILOT" if preflight["memory_gate_pass"] and preflight["disk_gate_pass"] and preflight["process_gate_pass"] else "BLOCKED_BY_RESOURCE"
    environment = runner.validate_environment(config)
    result = {
        "schema": "direct_scaling_xxl10_preparation_audit_v1",
        "protocol_id": config["resource_protocol_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "optimization_calls": 0,
        "decision": decision,
        "decision_note": "The snapshot decision does not authorize execution. Every future launch must repeat all gates.",
        "frozen_l10_xl10_evidence": frozen,
        "xxl10_inputs": inputs,
        "candidate_condition": authorized[0],
        "next_attempt": f"attempt-{runner.next_attempt_number(DIRECT, authorized[0]['condition_id']):03d}",
        "candidate_config_sha256": sha256(CONFIG),
        "candidate_config_hash": runner.canonical_hash(config),
        "current_model_identity": runner.model_identity(),
        "model_size": model_size,
        "model_size_formula_validation": validation,
        "model_size_evidence_note": "XXL10 counts are algebraic counts from the current model formula. No XXL10 Direct model was built, and no XXL10 Direct memory peak is claimed.",
        "hardware_preflight": preflight,
        "environment": environment,
        "solver_parameters": config["solver_parameters"],
        "resource_policy": resource,
        "low_memory_strategy": {
            "selected": {"Method": 2, "Threads": 2},
            "basis": "The same explicit pair reduced XL10 automatic-concurrent root-relaxation memory enough for nine certified runs; it does not prove XXL10 feasibility.",
            "risks": [
                "Barrier factorization at the MIP root can dominate memory for the 43-million-nonzero matrix.",
                "Crossover can require additional basis and working memory after Barrier.",
                "Threads=2 limits parallel work but does not cap Barrier factorization storage.",
                "XXL10 has about 2.34 times the XL10 variables and nonzeros, so the unchanged 13-GiB cap may still stop the pilot.",
            ],
            "separate_unselected_candidates": [
                "Crossover=0 would be a distinct solver protocol and is not included or authorized here.",
                "NodefileStart would be a distinct protocol and is unlikely to address root-node Barrier memory; it is not included or authorized here.",
            ],
        },
        "historical_scaling_environment_limit": "Scaling V2 historical Gurobi and Python versions remain NOT_VERIFIABLE; exact environment identity is not claimed.",
        "pure_xxl10_seed20260925": pure_pairing_exception(),
    }
    if config["formal_run_authorized"] is not False or result["next_attempt"] != "attempt-001":
        raise RuntimeError("XXL10 pilot authorization or attempt identity is unsafe")
    return result


def write_outputs() -> dict:
    audit = build_audit()
    OUTPUT.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    size = audit["model_size"]
    hardware = audit["hardware_preflight"]
    REPORT.write_text("\n".join([
        "# XXL10 Direct single-pilot preparation",
        "",
        "## Decision",
        "",
        f"`{audit['decision']}`",
        "",
        f"The read-only snapshot found {hardware['available_ram_gib']:.3f} GiB available versus the unchanged 16-GiB startup gate. Authorization remains false and no optimization attempt was created.",
        "",
        "## Scope and identity",
        "",
        "- Candidate: `DIRECT_XXL10_S20260921`, next identity `attempt-001`.",
        "- Frozen XXL10 inputs: 10/10 identity checks pass; I=36, R=36, J=16, Gamma=2.",
        "- Historical Pure `ASC_XXL10_S20260925_PURE_BENDERS` remains non-certified and excluded from valid four-method pairing.",
        "- L10/XL10 frozen evidence: 179/179 SHA-256 records unchanged.",
        "",
        "## Static model size",
        "",
        f"The current model formula gives {size['variable_count']:,} variables ({size['binary_variable_count']} binary), {size['constraint_count']:,} constraints, and {size['nonzero_count']:,} constraint-matrix nonzeros across {size['scenario_blocks']:,} product-scenario blocks. These are algebraic counts, not a Gurobi build or measured memory result.",
        "",
        "## Candidate protocol",
        "",
        "- Method=2, Threads=2, MIPGap=0; all frozen tolerances and scientific parameters unchanged.",
        "- 13-GiB process-tree cap, 16-GiB startup gate, 3-GiB system floor, 20-GiB disk gate, 900-second limit, 0.25-second monitoring, one process.",
        "- Method=2 avoids automatic concurrent LP selection, but Barrier factorization and Crossover remain material root-node memory risks.",
        "- Historical Scaling V2 software versions remain `NOT_VERIFIABLE`; exact environment identity is not claimed.",
        "",
        "No Gurobi model construction, optimization, or historical algorithm rerun was performed.",
    ]) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    audit = write_outputs()
    print(json.dumps({
        "decision": audit["decision"],
        "formal_run_authorized": audit["formal_run_authorized"],
        "condition_id": audit["candidate_condition"]["condition_id"],
        "next_attempt": audit["next_attempt"],
        "available_ram_gib": audit["hardware_preflight"]["available_ram_gib"],
        "optimization_calls": 0,
    }, indent=2))
