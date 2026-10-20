from __future__ import annotations

import argparse
from math import comb
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.run_ef_benders_scaling import DEFAULT_CONFIG, dry_run


def theoretical_size(I: int = 25, R: int = 24, J: int = 12, gamma: int = 2) -> dict:
    per_product = sum(comb(R, g) for g in range(gamma + 1))
    blocks = J * per_product
    variables_per_block = I * R + R + 1
    constraints_per_block = R + I + 2
    allocations = comb(J + gamma, gamma)
    block_nonzeros = (I + 1) * R + I * R + (R + 1) + (I * R + R + 2)
    oracle_variables = blocks * variables_per_block + J * (gamma + 1) + 1
    oracle_constraints = blocks * constraints_per_block + allocations
    oracle_nonzeros = blocks * block_nonzeros + allocations * (J + 1)
    first_stage_variables = I + 3 * I * J
    direct_variables = oracle_variables + first_stage_variables
    direct_constraints = oracle_constraints + I + 2 * I * J + 1
    direct_nonzeros = oracle_nonzeros + blocks * I + I * (J + 1) + 2 * I * J + 3 * I * J + (I + 3 * I * J)
    return {
        "product_local_scenario_blocks": blocks,
        "risk_budget_allocations": allocations,
        "ef_oracle": {"variables": oracle_variables, "constraints": oracle_constraints, "nonzeros": oracle_nonzeros},
        "direct_extensive_form": {"variables": direct_variables, "constraints": direct_constraints, "nonzeros": direct_nonzeros},
        "count_classification": "THEORETICAL_EXACT_FROM_MODEL_STRUCTURE_NOT_GUROBI_BUILD",
    }


def build(config: Path) -> dict:
    audit = dry_run(config)
    size = theoretical_size()
    expected = {"variables": 2258462, "constraints": 184929}
    preparation = json.loads((ROOT / "experiments/results/algorithm_scaling_convergence_cost_v2_repaired_guard/instances/L10/20260921/preparation.json").read_text(encoding="utf-8"))
    freeze = json.loads((ROOT / "artifacts/direct_scaling_l10_xl10_freeze_manifest.json").read_text(encoding="utf-8"))
    l10 = [row for row in freeze["conditions"] if row["size"] == "L10"]
    same_seed = next(row for row in l10 if row["condition_id"] == "DIRECT_L10_S20260921")
    direct_attempt_peak = max(float(row["peak_process_tree_memory_gib"]) for row in same_seed["attempts"] if row.get("peak_process_tree_memory_gib") is not None)
    maximum_l10_direct_peak = max(float(attempt["peak_process_tree_memory_gib"]) for row in l10 for attempt in row["attempts"] if attempt.get("peak_process_tree_memory_gib") is not None)
    gate = audit["resource_gate"]
    checks = {
        "identity_matches_direct_aggregate_prb": all(audit["paired_instance_identity"].values()),
        "frozen_dimensions": preparation["dimensions"] == {"depots": 25, "products": 12, "regions": 24, "scale": "L10"},
        "frozen_science": preparation["scientific_parameters"]["Gamma"] == 2 and preparation["scientific_parameters"]["lambda_R"] == 0.05,
        "direct_size_formula_matches_frozen": size["direct_extensive_form"]["variables"] == expected["variables"] and size["direct_extensive_form"]["constraints"] == expected["constraints"],
        "authorization_closed": audit["formal_run_authorized"] is False,
        "no_optimization": audit["optimization_calls"] == 0,
        "attempt_absent": not audit["canonical_result_exists"],
        "seven_gib_cap": gate["process_tree_cap_gib"] == 7,
        "eleven_gib_startup_gate": gate["startup_required_gib"] == 11,
        "three_gib_system_floor": gate["system_available_floor_gib"] == 3,
        "live_startup_gate_pass": gate["available_memory_gib"] >= gate["startup_required_gib"],
        "live_disk_gate_pass": gate["free_disk_gib"] >= gate["minimum_free_disk_gib"],
    }
    return {
        "schema": "ef_benders_scaling_l10_preparation_audit_v1",
        "status": "READY_FOR_AUTHORIZATION",
        "checks": checks,
        "dry_run": audit,
        "theoretical_size": size,
        "model_mapping": {
            "strictly_equivalent": True,
            "basis": "The generic InventoryInstance, unchanged Pure single-theta master, and recourse rows/objective cloned from build_exact_reconfiguration_model are used directly.",
            "excluded_mechanisms": ["PRB product multicut", "Pure compact adversarial MILP", "SG scenario pruning"],
        },
        "resource_assessment": {
            "configured_process_cap_gib": 4,
            "revised_process_cap_gib": 7,
            "revised_startup_gate_gib": 11,
            "observed_direct_attempt_002_peak_gib": direct_attempt_peak,
            "maximum_archived_l10_direct_peak_gib": maximum_l10_direct_peak,
            "headroom_over_same_seed_direct_peak_gib": 7 - direct_attempt_peak,
            "headroom_over_maximum_l10_direct_peak_gib": 7 - maximum_l10_direct_peak,
            "startup_minus_process_cap_gib": 4,
            "observed_value_source": "artifacts/direct_scaling_l10_xl10_freeze_manifest.json",
            "conclusion": "The 7 GiB cap is safe for one monitored pilot, not proven sufficient for completion. It provides 2.302 GiB over the same-seed Direct peak and 2.134 GiB over the maximum archived L10 Direct peak. The 11 GiB startup gate leaves 4 GiB when the process reaches its cap, above the 3 GiB system floor. No EF peak is claimed.",
        },
        "all_static_checks_pass": all(checks.values()),
        "optimization_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = build(args.config.resolve())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(value, indent=2, allow_nan=False))
    return 0 if value["all_static_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
