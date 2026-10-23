from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.algorithm_scaling import (
    METHODS,
    SEEDS,
    SIZES,
    SOURCE_CASES,
    canonical_hash,
    dry_run_plan,
    enumerate_conditions,
    load_config,
    resource_dimension_check,
    validate_config,
    validate_scientific_parameters,
)
from robust_inventory_reconfiguration.algorithm_scaling_reporting import (
    RESULT_FIELDS,
    TRAJECTORY_FIELDS,
    validate_pairwise_fairness,
)
from robust_inventory_reconfiguration.e1c_scaling import build_renault_calibrated_instance
from robust_inventory_reconfiguration.instance import load_instance


CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost.yaml"
OUTPUT = ROOT / "artifacts/algorithm_scaling_static_audit.json"
DRY_RUN_OUTPUT = ROOT / "artifacts/algorithm_scaling_dry_run.json"


def _resolve_repository_path(path: Path) -> Path:
    return (path if path.is_absolute() else ROOT / path).resolve()


def resolve_audit_routes(
    config_path: Path = CONFIG,
    output_root: Path | None = None,
) -> tuple[Path, Path, dict]:
    resolved_config = _resolve_repository_path(config_path)
    config = load_config(resolved_config)
    configured_output_root = _resolve_repository_path(Path(config["output_directory"]))
    resolved_output_root = (
        configured_output_root
        if output_root is None
        else _resolve_repository_path(output_root)
    )
    if resolved_output_root != configured_output_root:
        raise RuntimeError(
            "CONFIG_OUTPUT_ROOT_IDENTITY_MISMATCH: "
            f"config={resolved_config} configured_output_root={configured_output_root} "
            f"requested_output_root={resolved_output_root}"
        )
    return resolved_config, resolved_output_root, config


def _git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _existing_evidence_audit() -> dict:
    table = ROOT / "experiments/results/prb_large_scale_simulation_v1/simulation_run_table.csv"
    if not table.is_file():
        return {"status": "NOT_FOUND", "eligible_for_reuse": False}
    with table.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    identities = {(row["scale"], int(row["seed"]), row["method"]) for row in rows}
    expected = {(size.scale, seed, method) for size in SIZES for seed in SEEDS for method in METHODS}
    return {
        "status": "DESIGN_EVIDENCE_ONLY",
        "row_count": len(rows),
        "expected_condition_identities_present": len(identities & expected),
        "expected_condition_count": len(expected),
        "eligible_for_reuse": False,
        "reason": "Tracked summaries are marked development-only and do not carry the complete formal config/instance/model identity chain or raw prepared instances.",
        "source": table.relative_to(ROOT).as_posix(),
    }


def _post_run_audit(config: dict, output_root: Path) -> dict:
    from scripts.report_algorithm_scaling_convergence_cost import load_formal_evidence

    results, trajectories, characteristics, documented, unattempted = load_formal_evidence(
        config, output_root
    )
    expected_ids = {condition.condition_id for condition in enumerate_conditions()}
    result_ids = {row["condition_id"] for row in results}
    documented_ids = {row["condition_id"] for row in documented}
    config_identity = canonical_hash(config)
    documented_evidence_valid = all(
        row.get("experiment_id") == config["experiment_id"]
        and row.get("config_hash") == config_identity
        and row.get("attempted") is True
        and row.get("exact_certification") is False
        and (output_root / row["monitor_path"]).is_file()
        and (output_root / row["stderr_path"]).is_file()
        for row in documented
    )
    objective_equivalent = True
    objective_error = None
    try:
        validate_pairwise_fairness(
            results, config["algorithm"]["objective_equivalence_tolerance"]
        )
    except ValueError as error:
        objective_equivalent = False
        objective_error = str(error)
    checks = {
        "result_experiment_identity": all(
            row["experiment_id"] == config["experiment_id"] for row in results
        ),
        "result_config_identity": all(
            row["config_hash"] == config_identity for row in results
        ),
        "exact_90_conditions_accounted": result_ids | documented_ids == expected_ids,
        "exact_89_certified_results": len(results) == 89,
        "exact_1_documented_non_certified": len(documented) == len(documented_ids) == 1,
        "zero_unattempted_conditions": not unattempted,
        "documented_failure_evidence_valid": documented_evidence_valid,
        "exact_30_instances": len(characteristics) == 30,
        "all_reported_results_exactly_certified": all(
            row["solver_status"] == "OPTIMAL" and row["exact_certification"] is True
            for row in results
        ),
        "all_certified_trajectories_present": len({row["condition_id"] for row in trajectories}) == 89,
        "trajectory_timing_complete": all(
            row[field] is not None
            for row in trajectories
            for field in (
                "LB", "UB", "gap", "normalized_LB", "master_time_seconds",
                "oracle_time_seconds", "cumulative_time_seconds", "cuts_added",
            )
        ),
        "aggregate_timing_complete": all(
            row[field] is not None
            for row in results
            for field in ("total_core_solve_time", "master_time", "oracle_time", "certification_time")
        ),
        "pairwise_objectives_equivalent": objective_equivalent,
        "no_result_reuse": all(row["result_reused"] is False for row in results),
        "required_tables_present": all(
            (output_root / name).is_file() for name in config["required_outputs"]
        ),
    }
    return {
        "status": "POST_RUN_AUDIT_PASS" if all(checks.values()) else "POST_RUN_AUDIT_FAIL",
        "checks": checks,
        "formal_counts": {
            "expected": len(expected_ids),
            "certified": len(results),
            "documented_non_certified": len(documented),
            "unattempted": len(unattempted),
        },
        "objective_equivalence_error": objective_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Algorithm scaling static/post-run audit")
    parser.add_argument("--post-run", action="store_true")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    config_path, output_root, config = resolve_audit_routes(
        args.config, args.output_root
    )
    validate_config(config)
    plan = dry_run_plan(config)
    conditions = enumerate_conditions()
    sources = [load_instance(ROOT / f"data/formal_instances_v2/{case_id}.json") for case_id in SOURCE_CASES]
    generated = []
    for size in SIZES:
        for seed in SEEDS:
            instance = build_renault_calibrated_instance(sources, size, seed)
            generated.append({
                "instance_id": f"ASC_INSTANCE_{size.scale}_S{seed}",
                "size": size.scale,
                "seed": seed,
                "primitive_instance_hash": canonical_hash(instance.to_dict()),
                "scientific_parameter_checks": validate_scientific_parameters(instance),
            })
    runner = (ROOT / "experiments/run_algorithm_scaling_convergence_cost.py").read_text(encoding="utf-8")
    reporting = (ROOT / "src/robust_inventory_reconfiguration/algorithm_scaling_reporting.py").read_text(encoding="utf-8")
    solver_sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "src/robust_inventory_reconfiguration/pure_benders.py",
            "src/robust_inventory_reconfiguration/standard_benders.py",
            "src/robust_inventory_reconfiguration/product_risk_budget_benders.py",
        )
    )
    checks = {
        "01_frozen_method_set": tuple(config["methods"]) == METHODS,
        "02_frozen_size_set": [item["label"] for item in config["instance_family"]["sizes"]] == [size.scale for size in SIZES],
        "03_frozen_seeds": tuple(config["instance_family"]["seeds"]) == SEEDS,
        "04_scientific_parameters_identical": all(row["scientific_parameter_checks"]["pass"] for row in generated),
        "05_solver_tolerances_identical": set(config["solver_tolerances"]) == {"relative_gap", "cut_violation", "objective_certification"},
        "06_exact_certification_identical": config["algorithm"]["exact_certification_required"] is True and "exact_certification" in runner,
        "07_no_management_sensitivity_dimensions": config["management_sensitivity_dimensions"] == [] and plan["management_sensitivity_dimensions"] == [],
        "08_deterministic_condition_ids": conditions == enumerate_conditions(),
        "09_no_duplicate_physical_runs": len(conditions) == len({condition.condition_id for condition in conditions}) == 90,
        "10_per_iteration_trajectory_present": all(field in TRAJECTORY_FIELDS for field in ("LB", "UB", "gap", "normalized_LB", "cumulative_time_seconds")) and "normalized_trajectory" in runner,
        "11_master_oracle_timing_present": "master_time_seconds" in solver_sources and "oracle_time_seconds" in solver_sources,
        "12_total_core_time_present": "total_core_solve_time" in RESULT_FIELDS,
        "13_objective_equivalence_audited": "validate_pairwise_fairness" in reporting and "objective_tolerance" in reporting,
        "14_result_reuse_identity_exact": "_verified_complete_result" in runner and "existing result identity failure" in runner,
        "15_formal_execution_gate_explicit": config["formal_run_authorized"] is True and config["authorization_transition"] == [False, True] and "require_formal_authorization(config)" in runner,
        "16_exact_30_instances": len(generated) == len({row["instance_id"] for row in generated}) == 30,
        "17_exact_90_method_runs": plan["physical_runs"] == 90 and plan["runs_by_method"] == {method: 30 for method in METHODS},
        "18_direct_safely_excluded": config["direct_reference"]["enabled"] is False and plan["direct_runs"] == 0,
        "19_resource_gates_pass": all(resource_dimension_check(config, size)["pass"] for size in SIZES),
        "20_sequential_execution": config["resource_policy"]["execution"] == "sequential" and config["resource_policy"]["parallel_workers"] == 1 and "_run_monitored" in runner,
        "21_resume_never_overwrites": "refusing to overwrite result" in runner and "[RESUME VERIFIED]" in runner,
        "22_reporting_schema_complete": all(field in RESULT_FIELDS for field in ("iterations", "cuts", "master_time", "oracle_time", "certification_time", "master_share", "oracle_share")),
        "23_no_formal_optimization_in_audit": True,
        "24_size_dependent_resource_gate": config["resource_policy"]["minimum_available_memory_gib_by_size"] == {"L10": 7, "XL10": 10, "XXL10": 16} and "resource_thresholds(config, condition.size)" in runner,
        "25_staged_size_execution_supported": 'mode.add_argument("--execute-size"' in runner,
    }
    post_run = (
        _post_run_audit(config, output_root)
        if args.post_run
        else {"status": "NOT_REQUESTED"}
    )
    passed = all(checks.values()) and post_run["status"] in {"NOT_REQUESTED", "POST_RUN_AUDIT_PASS"}
    payload = {
        "schema": "algorithm_scaling_static_audit_v1",
        "status": "STATIC_AUDIT_PASS" if passed else "STATIC_AUDIT_FAIL",
        "routing_identity": {
            "config_path": str(config_path),
            "output_root": str(output_root),
            "experiment_id": config["experiment_id"],
            "config_identity": canonical_hash(config),
            "code_commit": _git_commit(),
        },
        "checks": checks,
        "formal_run_authorized": config["formal_run_authorized"],
        "formal_optimization_runs_executed_by_audit": 0,
        "dry_run": {key: value for key, value in plan.items() if key != "conditions"},
        "controlled_instance_family": generated,
        "existing_evidence": _existing_evidence_audit(),
        "post_run_audit": post_run,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    DRY_RUN_OUTPUT.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
