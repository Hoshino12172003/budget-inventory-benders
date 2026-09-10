from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from robust_inventory_reconfiguration.first_stage_solution import load_first_stage_solution_artifact, matrix_from_artifact
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.robust_service import evaluate_robust_service_detailed
from robust_inventory_reconfiguration.solver_profile import FORMAL_SOLVER_PROFILE_ID

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/configs/formal/e2_existing_nominal_robust_authorization.json"
IDENTITY = ROOT / "table_empirical_8case_identity.csv"
RESULT_ROOT = ROOT / "experiments/results/e2_existing_nominal_robust_v1"
E1_ROOT = ROOT / "experiments/results/e1_empirical_8case_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_gate(case: str, policy: str, output_root: Path) -> tuple[dict, dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    run_id = f"E2-{case}-{policy}"
    if manifest.get("formal_run_authorized") is not True or run_id not in manifest.get("authorized_run_ids", []):
        raise PermissionError("E2_FORMAL_RUN_NOT_AUTHORIZED")
    if manifest.get("e3_e7_authorization") is not False:
        raise RuntimeError("E3-E7 authorization changed")
    if sha256(Path(__file__)) != manifest.get("runner_sha256"):
        raise RuntimeError("E2 runner hash mismatch")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E2 requires a clean committed worktree")
    target = output_root / run_id
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {run_id}")
    with IDENTITY.open(encoding="utf-8", newline="") as stream:
        identities = {row["case"]: row for row in csv.DictReader(stream)}
    identity = identities[case]
    instance_path = ROOT / f"data/formal_instances_v2/{case}.json"
    x0_path = ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json"
    calibration_path = ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json"
    for key, path in (("instance_hash", instance_path), ("x0_hash", x0_path), ("calibration_hash", calibration_path)):
        if sha256(path) != identity[key]:
            raise RuntimeError(f"BLOCK_E2_IDENTITY_MISMATCH: {key}")
    return manifest, identity


def components(instance, y, x, a_plus, a_minus, lambda_r):
    fixed = sum(instance.fixed_depot_cost[i] * y[i] for i in range(instance.num_depots))
    inventory = sum(instance.inventory_cost[i][j] * x[i][j] for i in range(instance.num_depots) for j in range(instance.num_products))
    reconfiguration = lambda_r * sum(instance.inventory_cost[i][j] * (a_plus[i][j] + a_minus[i][j]) for i in range(instance.num_depots) for j in range(instance.num_products))
    return fixed, inventory, reconfiguration


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--policy", required=True, choices=("EXISTING", "NOMINAL", "ROBUST"))
    parser.add_argument("--output-root", type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    manifest, identity = validate_gate(args.case, args.policy, args.output_root)
    instance = load_instance(ROOT / f"data/formal_instances_v2/{args.case}.json")
    x0_artifact = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{args.case}.json").read_text(encoding="utf-8"))
    x0, y0 = x0_artifact["x0"], x0_artifact["y0"]
    budget = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{args.case}.json").read_text(encoding="utf-8"))["B_ref"]
    reused = False
    if args.policy == "EXISTING":
        y, x = y0, x0
        a_plus = [[0.0] * instance.num_products for _ in range(instance.num_depots)]
        a_minus = [[0.0] * instance.num_products for _ in range(instance.num_depots)]
        gamma_plan = None
    elif args.policy == "NOMINAL":
        solved = solve_prb_benders(instance, x0, budget, 0, manifest["lambda_R"])
        if solved.status != "OPTIMAL" or not solved.exact_certification_pass:
            raise RuntimeError("nominal planning solve not certified")
        y, x, a_plus, a_minus = solved.solution.y, solved.solution.x, solved.solution.a_plus, solved.solution.a_minus
        gamma_plan = 0
    else:
        e1_dir = E1_ROOT / f"E1-{args.case}-PRB"
        e1_result = json.loads((e1_dir / "result.json").read_text(encoding="utf-8"))
        required = {"Gamma": 2, "beta": 1.0, "lambda_R": 0.05, "instance_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"], "calibration_hash": identity["calibration_hash"], "solver_profile": FORMAL_SOLVER_PROFILE_ID}
        if any(e1_result.get(key) != value for key, value in required.items()):
            raise RuntimeError("BLOCK_E2_IDENTITY_MISMATCH: E1 reuse")
        artifact = load_first_stage_solution_artifact(e1_dir / "first_stage_solution.json", instance)
        x = matrix_from_artifact(artifact, instance)
        y = [entry["value"] for entry in artifact["y"]]
        a_plus = matrix_from_artifact(artifact, instance, "a_plus")
        a_minus = matrix_from_artifact(artifact, instance, "a_minus")
        gamma_plan, reused = 2, True
    service = evaluate_robust_service_detailed(instance, x, 2)
    fixed, inventory, reconfiguration = components(instance, y, x, a_plus, a_minus, manifest["lambda_R"])
    first_stage = fixed + inventory + reconfiguration
    total_adjustment = sum(map(sum, a_plus)) + sum(map(sum, a_minus))
    x0_total = sum(map(sum, x0))
    opened = [instance.depot_ids[i] for i in range(instance.num_depots) if y[i] and not y0[i]]
    closed = [instance.depot_ids[i] for i in range(instance.num_depots) if y0[i] and not y[i]]
    result = {
        "run_id": f"E2-{args.case}-{args.policy}", "case": args.case, "policy": args.policy,
        "Gamma_plan": gamma_plan, "Gamma_eval": 2, "objective_eval": first_stage + service.robust_recourse_cost,
        "fixed_cost": fixed, "inventory_cost": inventory, "reconfiguration_cost": reconfiguration,
        "robust_recourse_cost": service.robust_recourse_cost, "budget_used": first_stage,
        "budget_utilization": first_stage / budget, "RI": total_adjustment / x0_total,
        "RS": reconfiguration / budget, "total_a_plus": sum(map(sum, a_plus)),
        "total_a_minus": sum(map(sum, a_minus)), "total_adjustment": total_adjustment,
        "changed_pair_count": sum(abs(x[i][j] - x0[i][j]) > 1e-6 for i in range(instance.num_depots) for j in range(instance.num_products)),
        "active_depots": sum(y), "opened_depots": opened, "closed_depots": closed,
        "worst_recourse_shortage_cost": service.worst_recourse_scenario.shortage_cost,
        "worst_recourse_total_shortage": service.worst_recourse_scenario.total_shortage,
        "worst_recourse_service_penalty_cost": service.worst_recourse_scenario.service_penalty_cost,
        "minimum_fill_rate": service.worst_service_scenario.minimum_fill_rate,
        "average_fill_rate": service.worst_service_scenario.average_fill_rate,
        "worst_region": service.worst_service_scenario.worst_region_id,
        "reused_from_E1": reused, "instance_hash": identity["instance_hash"], "x0_hash": identity["x0_hash"],
        "mapping_hash": manifest["mapping_sha256"], "solver_profile": manifest["solver_profile"], "status": "OPTIMAL",
    }
    target = args.output_root / result["run_id"]
    target.mkdir(parents=True)
    (target / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
