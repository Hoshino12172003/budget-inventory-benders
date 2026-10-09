from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.algorithm_scaling import canonical_hash, load_config
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.pure_benders import solve_pure_benders


CONDITION_ID = "ASC_L10_S20260929_PURE_BENDERS"
CONFIG = ROOT / "experiments/configs/formal/algorithm_scaling_convergence_cost.yaml"
PREPARATION_ROOT = (
    ROOT
    / "experiments/results/algorithm_scaling_convergence_cost_v1/instances/L10/20260929"
)
OUTPUT = ROOT / "artifacts/algorithm_scaling_pure_cut_diagnostic_L10_S20260929.json"


def main() -> None:
    config = load_config(CONFIG)
    instance = load_instance(PREPARATION_ROOT / "instance.json")
    preparation = json.loads((PREPARATION_ROOT / "preparation.json").read_text(encoding="utf-8"))
    if preparation["instance_id"] != "ASC_INSTANCE_L10_S20260929":
        raise RuntimeError("unexpected prepared instance identity")
    if canonical_hash(instance.to_dict()) != preparation["instance_hash"]:
        raise RuntimeError("prepared instance hash mismatch")
    tolerances = config["solver_tolerances"]
    caught = None
    try:
        solve_pure_benders(
            instance,
            instance.initial_inventory,
            float(preparation["budget"]),
            config["fixed_scientific_parameters"]["Gamma"],
            config["fixed_scientific_parameters"]["lambda_R"],
            relative_gap_tolerance=tolerances["relative_gap"],
            cut_tolerance=tolerances["cut_violation"],
            objective_certification_tolerance=tolerances["objective_certification"],
            max_iterations=config["algorithm"]["max_iterations"],
            time_limit=config["resource_policy"]["condition_time_limit_seconds"],
            cut_diagnostic_file=OUTPUT,
        )
    except RuntimeError as error:
        caught = str(error)
    if caught != "a previously added Pure Benders cut remains violated":
        raise RuntimeError(f"diagnostic did not reproduce the expected failure: {caught}")
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    payload["condition"] = {
        "condition_id": CONDITION_ID,
        "size": "L10",
        "seed": 20260929,
        "method": "pure_benders",
        "Gamma": config["fixed_scientific_parameters"]["Gamma"],
        "beta": config["fixed_scientific_parameters"]["beta"],
        "lambda_R": config["fixed_scientific_parameters"]["lambda_R"],
        "SL": config["fixed_scientific_parameters"]["SL"],
        "phi_multiplier": config["fixed_scientific_parameters"]["phi_multiplier"],
        "instance_hash": preparation["instance_hash"],
        "preparation_code_commit": preparation["code_commit"],
        "diagnostic_code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }
    payload["reproduction"] = {
        "expected_exception_reproduced": True,
        "exception": caught,
        "formal_result_written": False,
        "other_conditions_executed": 0,
    }
    payload["diagnostic_conclusion"] = {
        "classification": "CUT_RECONSTRUCTION_MISMATCH",
        "root_cause": (
            "The duplicate-cut guard validates certified fixed-scenario primal value minus theta, "
            "not the algebraic cut RHS minus theta. The stored and candidate cuts are identical "
            "and the master satisfies the offending cut exactly."
        ),
        "trigger_violation": payload["trigger"]["certified_value_minus_theta"],
        "actual_previous_cut_violation": payload["offending_cut_signed_violation"],
        "minimal_fix_proposed_not_applied": (
            "At pure_benders.py line 353, compute the cut-validity residual from "
            "evaluated.cut.value_at(xbar) - theta; retain evaluated.value for the certified upper bound."
        ),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "condition_id": CONDITION_ID,
        "max_previous_cut_violation": payload["max_previous_cut_violation"],
        "offending_cut_id": payload["offending_cut_id"],
        "iteration_added": payload["iteration_added"],
        "iteration_detected": payload["iteration_detected"],
        "trigger": payload["trigger"],
    }, indent=2))


if __name__ == "__main__":
    main()
