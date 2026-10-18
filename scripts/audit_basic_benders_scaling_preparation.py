from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sys
from math import comb
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_basic_benders_scaling as basic_runner
from experiments import run_direct_scaling as direct_runner
from scripts.audit_direct_scaling_xxl10_preparation import frozen_evidence_audit


CONFIG = ROOT / "experiments/configs/development/basic_benders_scaling_l10_pilot_v1.yaml"
SCALING = ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard"
RENAULT_PILOT = ROOT / "experiments/results/renault_vanilla_bd_pilot_210202_development_v1"
RENAULT_REST = ROOT / "experiments/results/renault_vanilla_bd_remaining7_development_v1"
DIRECT_CONFIG = ROOT / "experiments/configs/formal/direct_scaling_xxl10_low_memory_pilot_v1.yaml"
OUTPUT = ROOT / "artifacts/basic_benders_scaling_preparation_audit.json"
REPORT = ROOT / "docs/basic_benders_scaling_and_xxl10_direct_readiness.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(root: Path) -> dict:
    manifest = root / "sha256.txt"
    failures = []
    count = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = root / relative
        count += 1
        if not path.is_file() or sha256(path) != expected:
            failures.append(relative)
    return {"manifest": str(manifest.relative_to(ROOT)), "entries": count, "failures": failures, "pass": not failures}


def renault_audit() -> dict:
    pilot_manifest = verify_manifest(RENAULT_PILOT)
    rest_manifest = verify_manifest(RENAULT_REST)
    micro = json.loads((RENAULT_PILOT / "micro/result.json").read_text(encoding="utf-8"))
    cases = {"210202": json.loads((RENAULT_PILOT / "vanilla/result.json").read_text(encoding="utf-8"))}
    for case in ("210628", "210129", "210310", "210330", "210323", "210428", "210611"):
        cases[case] = json.loads((RENAULT_REST / case / "vanilla/result.json").read_text(encoding="utf-8"))
    summary = json.loads((RENAULT_REST / "renault_vanilla_prb_8case_summary.json").read_text(encoding="utf-8"))
    source = (ROOT / "experiments/run_renault_vanilla_bd_pilot.py").read_text(encoding="utf-8")
    oracle_source = source.split("class GlobalEnumeratedLPOracle", 1)[1].split("def _tiny_inputs", 1)[0]
    checks = {
        "pilot_manifest": pilot_manifest["pass"],
        "remaining_manifest": rest_manifest["pass"],
        "micro_direct_equivalence": micro["status"] == "PASS" and micro["objective_difference"] <= 1e-4,
        "micro_dual_feasibility": micro["dual_feasibility_pass"] is True,
        "micro_strong_duality": micro["maximum_strong_duality_residual"] <= 1e-4,
        "micro_cut_validity": micro["maximum_cut_validity_excess"] <= 1e-4,
        "basic_exact_8_of_8": all(row["exact_certification_pass"] is True for row in cases.values()),
        "one_aggregate_cut_per_iteration": all(row["cut_count"] <= row["iterations"] for row in cases.values()),
        "no_product_risk_composition": "compose_risk_budget" not in oracle_source and "ProductRiskSubproblem" not in oracle_source,
        "no_global_adversarial_milp_construction": "GlobalRobustAdversarialSubproblem(" not in oracle_source,
        "known_prb_210330_excluded": summary["valid_exact_pairs"] == 7 and next(row for row in summary["pairs"] if row["case"] == "210330")["valid_exact_pair"] is False,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Renault Basic-BD audit failed: {checks}")
    return {
        "status": "PASS",
        "checks": checks,
        "manifests": [pilot_manifest, rest_manifest],
        "basic_exact_cases": len(cases),
        "valid_basic_prb_pairs": summary["valid_exact_pairs"],
        "implementation_sha256": sha256(ROOT / "experiments/run_renault_vanilla_bd_pilot.py"),
    }


def basic_workload(I: int, R: int, J: int, gamma: int) -> dict:
    scenarios = sum(comb(R * J, value) for value in range(gamma + 1))
    return {
        "I": I,
        "R": R,
        "J": J,
        "Gamma": gamma,
        "global_scenarios_per_oracle_call": scenarios,
        "reusable_recourse_lp_variables": I * R * J + R * J + J,
        "reusable_recourse_lp_constraints": R * J + I * J + J,
        "maximum_scenario_lp_solves_at_500_iterations_plus_two_certifications": scenarios * 502,
        "evidence_class": "THEORETICAL_COUNT_NO_MODEL_BUILD_NO_OPTIMIZATION",
        "primary_risk": "TIME_FROM_SEQUENTIAL_SCENARIO_LP_ENUMERATION",
        "memory_note": "The implementation reuses one recourse LP, so memory does not scale by materializing all scenarios.",
    }


def input_audit(config: dict) -> list[dict]:
    rows = []
    for size in config["sizes"]:
        for seed in config["seeds"]:
            condition = {"size": size["label"], "seed": seed}
            instance, preparation, hashes = direct_runner.verified_input(config, condition)
            rows.append({
                "size": size["label"],
                "seed": seed,
                "instance_id": preparation["instance_id"],
                "instance_hash": preparation["instance_hash"],
                "x0_hash": preparation["x0_hash"],
                **hashes,
                "dimensions": [instance.num_depots, instance.num_regions, instance.num_products],
                "identity_status": "PASS",
            })
    if len(rows) != 30:
        raise RuntimeError(f"expected 30 frozen inputs, found {len(rows)}")
    return rows


def convergence_audit() -> dict:
    trajectory_path = SCALING / "algorithm_scaling_iteration_trajectory.csv"
    with trajectory_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    conditions = {row["condition_id"] for row in rows}
    required = {"LB", "UB", "gap", "cumulative_time_seconds", "cuts_added"}
    fields = set(rows[0]) if rows else set()
    non_certified = "ASC_XXL10_S20260925_PURE_BENDERS"
    checks = {
        "required_fields": required <= fields,
        "certified_condition_trajectories": len(conditions) == 89,
        "non_certified_not_misrepresented": non_certified not in conditions,
        "no_nan": all(all(row[name].strip().lower() not in {"", "nan"} for name in required) for row in rows),
    }
    if not all(checks.values()):
        raise RuntimeError(f"trajectory audit failed: {checks}")
    return {
        "status": "PARTIAL_FOR_FUTURE_FIVE_METHOD_COMPARISON",
        "checks": checks,
        "persisted_rows": len(rows),
        "persisted_conditions": len(conditions),
        "scaling_v2_methods": sorted({row["method"] for row in rows}),
        "basic_scaling_conditions": 0,
        "gap_thresholds_supported": [0.01, 0.001, 0.0001],
        "fairness_conclusion": "Existing certified Scaling V2 Benders trajectories are sufficient within those three methods; no Basic-BD scaling trajectory exists yet, so a four-Benders gap comparison is not yet possible.",
    }


def scaling_result_integrity() -> dict:
    runs = sorted(path for path in (SCALING / "runs").iterdir() if path.is_dir())
    failures = []
    for run in runs:
        result_path = run / "result.json"
        trajectory_path = run / "iteration_trajectory.json"
        provenance_path = run / "provenance.json"
        if not all(path.is_file() for path in (result_path, trajectory_path, provenance_path)):
            failures.append(f"{run.name}: incomplete canonical archive")
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if result.get("condition_id") != run.name:
            failures.append(f"{run.name}: condition identity mismatch")
        if result.get("exact_certification") is not True:
            failures.append(f"{run.name}: canonical result is not certified")
        if provenance.get("result_sha256") != sha256(result_path):
            failures.append(f"{run.name}: result SHA-256 mismatch")
        if provenance.get("trajectory_sha256") != sha256(trajectory_path):
            failures.append(f"{run.name}: trajectory SHA-256 mismatch")
    if len(runs) != 89 or failures:
        raise RuntimeError(f"Scaling V2 canonical archive integrity failed: count={len(runs)}, failures={failures}")
    return {"canonical_certified_archives": len(runs), "sha256_failures": failures, "status": "PASS"}


def active_solver_processes() -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (process.info.get("name") or "").lower()
            command = " ".join(process.info.get("cmdline") or []).lower()
            if name.startswith("gurobi") or "run_direct_scaling.py --worker" in command:
                found.append({"pid": process.info["pid"], "name": process.info.get("name")})
        except psutil.Error:
            continue
    return found


def direct_readiness() -> dict:
    config = json.loads(DIRECT_CONFIG.read_text(encoding="utf-8"))
    memory = psutil.virtual_memory()
    available = memory.available / 2**30
    disk = shutil.disk_usage(ROOT).free / 2**30
    policy = config["resource_policy"]
    processes = active_solver_processes()
    checks = {
        "authorization_closed": config["formal_run_authorized"] is False,
        "single_candidate": config["authorized_condition_ids"] == ["DIRECT_XXL10_S20260921"],
        "process_cap_13_gib": policy["maximum_process_tree_memory_gib_by_size"]["XXL10"] == 13,
        "startup_gate_16_gib": policy["minimum_available_memory_gib_by_size"]["XXL10"] == 16,
        "system_floor_3_gib": policy["minimum_system_available_memory_gib"] == 3,
        "timeout_900_seconds": policy["condition_time_limit_seconds"] == 900,
        "disk_gate_20_gib": policy["minimum_free_disk_gib"] == 20,
    }
    if not all(checks.values()):
        raise RuntimeError(f"XXL10 Direct protocol changed: {checks}")
    gates = {
        "memory": available >= 16,
        "disk": disk >= 20,
        "no_active_solver": not processes,
    }
    return {
        "status": "READY_BUT_UNAUTHORIZED" if all(gates.values()) else "BLOCKED_BY_RESOURCE",
        "checks": checks,
        "live": {
            "total_ram_gib": memory.total / 2**30,
            "available_ram_gib": available,
            "free_disk_gib": disk,
            "audit_process_rss_gib": psutil.Process(os.getpid()).memory_info().rss / 2**30,
            "active_solver_processes": processes,
        },
        "gates": gates,
        "model_size": {
            "variables": 14227589,
            "binary_variables": 36,
            "constraints": 791070,
            "nonzeros": 43069377,
            "evidence_class": "THEORETICAL_FORMULA_PREVIOUSLY_VALIDATED_ON_L10_XL10_NO_XXL10_BUILD",
        },
        "migration_requirements": [
            "At least 16 GiB available RAM at every launch and enough total RAM to retain the 13 GiB process cap plus the 3 GiB system floor.",
            "Python 3.12.7, gurobipy/native Gurobi 13.0.1, the frozen solver profile, model identity, config hash, and all instance hashes must match the candidate protocol.",
            "Single-process execution, 20 GiB free disk, 0.25-second monitoring, 900-second timeout, fail-closed archival, and independent certification must remain enabled.",
            "Historical Scaling V2 solver version remains NOT_VERIFIABLE, so migration can preserve the new Direct protocol identity but cannot establish exact historical software identity.",
        ],
    }


def build_audit() -> dict:
    config = basic_runner.load_config(CONFIG)
    dry = basic_runner.dry_run(CONFIG)
    inputs = input_audit(config)
    workloads = {
        size["label"]: basic_workload(size["I"], size["R"], size["J"], 2)
        for size in config["sizes"]
    }
    status = json.loads((SCALING / "algorithm_scaling_formal_status.json").read_text(encoding="utf-8"))
    scaling_checks = {
        "expected_90": status["expected_conditions"] == 90,
        "certified_89": status["certified_conditions"] == 89,
        "documented_failure_1": status["documented_non_certified_conditions"] == 1,
        "unattempted_0": status["unattempted_conditions"] == 0,
        "known_global_failure": status["documented_non_certified"][0]["condition_id"] == "ASC_XXL10_S20260925_PURE_BENDERS",
    }
    if not all(scaling_checks.values()):
        raise RuntimeError(f"Scaling V2 status changed: {scaling_checks}")
    pilot_ready = (
        dry["resource_gate"]["available_memory_gib"] >= dry["resource_gate"]["startup_required_gib"]
        and dry["resource_gate"]["free_disk_gib"] >= dry["resource_gate"]["minimum_free_disk_gib"]
        and not dry["canonical_result_exists"]
        and dry["git_status_clean"]
    )
    return {
        "schema": "basic_benders_scaling_preparation_audit_v1",
        "optimization_calls": 0,
        "basic_protocol": {
            "protocol_id": config["protocol_id"],
            "formal_run_authorized": config["formal_run_authorized"],
            "authorized_condition_ids": config["authorized_condition_ids"],
            "config_sha256": sha256(CONFIG),
            "dry_run": dry,
            "decision": "READY_FOR_SINGLE_PILOT_AUTHORIZATION" if pilot_ready else "BLOCKED_BY_RESOURCE",
        },
        "preparation_code_identity": {
            "basic_runner_sha256": sha256(ROOT / "experiments/run_basic_benders_scaling.py"),
            "audit_script_sha256": sha256(ROOT / "scripts/audit_basic_benders_scaling_preparation.py"),
            "gap_plot_script_sha256": sha256(ROOT / "scripts/plot_algorithm_gap_trajectories.py"),
        },
        "renault_basic_evidence": renault_audit(),
        "frozen_l10_xl10_direct_evidence": frozen_evidence_audit(),
        "scaling_v2": {"checks": scaling_checks, "status": status},
        "scaling_v2_archive_integrity": scaling_result_integrity(),
        "frozen_inputs": inputs,
        "workloads": workloads,
        "convergence_trajectory": convergence_audit(),
        "xxl10_direct": direct_readiness(),
        "known_exclusions": [
            "ASC_XXL10_S20260925_PURE_BENDERS: historical cut-validity certification failure",
            "DIRECT_XL10_S20260924: frozen resource failure",
            "Renault PRB 210330: internal global-risk-budget coupling certification failure",
        ],
    }


def write_outputs() -> dict:
    audit = build_audit()
    OUTPUT.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    workload = audit["workloads"]
    basic = audit["basic_protocol"]
    direct = audit["xxl10_direct"]
    REPORT.write_text("\n".join([
        "# Basic-BD scaling and XXL10 Direct readiness",
        "",
        "## Decisions",
        "",
        f"- Basic-BD L10 seed 20260921: `{basic['decision']}`; authorization remains false.",
        f"- XXL10 Direct seed 20260921: `{direct['status']}`; authorization remains false.",
        "- Optimization calls made by this preparation: 0.",
        "",
        "## Basic-BD identity and frozen evidence",
        "",
        "The reused implementation enumerates every admissible global shock scenario, solves one reusable all-product recourse LP per scenario, and adds at most one aggregate optimality cut per Benders iteration. Static source checks confirm that its oracle does not instantiate the Global-BD adversarial MILP and does not call Aggregate/PRB product-risk composition. The Renault micro Direct comparison, dual feasibility, strong duality, cut validity, 8/8 Basic certifications, and archived SHA manifests all pass.",
        "",
        "## Theoretical workload",
        "",
        "| Size | Global scenarios/oracle call | Reusable LP variables | Reusable LP constraints | Max scenario LP solves (502 calls) |",
        "|---|---:|---:|---:|---:|",
        *[
            f"| {name} | {row['global_scenarios_per_oracle_call']:,} | {row['reusable_recourse_lp_variables']:,} | {row['reusable_recourse_lp_constraints']:,} | {row['maximum_scenario_lp_solves_at_500_iterations_plus_two_certifications']:,} |"
            for name, row in workload.items()
        ],
        "",
        "These are formula counts, not measured runtimes or memory peaks. Sequential scenario-LP enumeration is the dominant expected bottleneck; the implementation reuses one LP, so it does not materialize all scenarios in memory.",
        "",
        "## Frozen pilot resource contract",
        "",
        "- One allowlisted development condition only: `BASIC_L10_S20260921`.",
        "- 900 seconds total, 4 GiB process tree, 7 GiB startup availability, 3 GiB system floor, 20 GiB disk gate, 0.25-second monitoring, one process, no automatic retry.",
        "- Scaling V2 tolerances and maximum 500 iterations are unchanged; the scenario safety cap is frozen once at 166,177.",
        "",
        "## Convergence comparability",
        "",
        "The archived Scaling V2 CSV contains complete LB/UB/gap/cumulative-time trajectories for 89 certified conditions. It correctly excludes the non-certified Global-BD XXL10 seed 20260925. No Basic-BD scaling trajectory exists yet, so a fair four-Benders gap comparison cannot be produced until an authorized Basic-BD run persists the same fields. Direct MIP progress is not treated as a Benders LB/UB trajectory.",
        "",
        "## XXL10 Direct",
        "",
        f"Live available RAM is {direct['live']['available_ram_gib']:.3f} GiB and free disk is {direct['live']['free_disk_gib']:.3f} GiB. The unchanged gate is 16 GiB available RAM, 13 GiB process-tree cap, 3 GiB system floor, 20 GiB disk, and 900 seconds. The static model estimate remains 14,227,589 variables, 791,070 constraints, and 43,069,377 nonzeros; no XXL10 Direct model was built.",
        "",
        "A larger-RAM migration must preserve Python/Gurobi, solver-profile, code/config/instance hashes, single-process monitoring, resource gates, archival, and certification. Because the historical Scaling V2 solver version is not verifiable, exact historical software identity must not be claimed.",
    ]) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    result = write_outputs()
    print(json.dumps({
        "optimization_calls": 0,
        "basic_decision": result["basic_protocol"]["decision"],
        "basic_authorized": result["basic_protocol"]["formal_run_authorized"],
        "direct_decision": result["xxl10_direct"]["status"],
        "direct_authorized": result["xxl10_direct"]["checks"]["authorization_closed"] is False,
    }, indent=2))
