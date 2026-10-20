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
    direct_attempt_peak = 4.698249816894531
    checks = {
        "identity_matches_direct_aggregate_prb": all(audit["paired_instance_identity"].values()),
        "frozen_dimensions": preparation["dimensions"] == {"depots": 25, "products": 12, "regions": 24, "scale": "L10"},
        "frozen_science": preparation["scientific_parameters"]["Gamma"] == 2 and preparation["scientific_parameters"]["lambda_R"] == 0.05,
        "direct_size_formula_matches_frozen": size["direct_extensive_form"]["variables"] == expected["variables"] and size["direct_extensive_form"]["constraints"] == expected["constraints"],
        "authorization_closed": audit["formal_run_authorized"] is False,
        "no_optimization": audit["optimization_calls"] == 0,
        "attempt_absent": not audit["canonical_result_exists"],
    }
    return {
        "schema": "ef_benders_scaling_l10_preparation_audit_v1",
        "status": "BLOCKED_RESOURCE_DESIGN",
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
            "observed_direct_attempt_002_peak_gib": direct_attempt_peak,
            "observed_value_source": "artifacts/direct_scaling_l10_xl10_freeze_manifest.json",
            "conclusion": "The EF oracle retains 99.96% of Direct variables and nearly the entire recourse matrix. A 4 GiB cap is clearly not supported by the observed 4.698 GiB Direct peak; no EF peak is claimed.",
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
