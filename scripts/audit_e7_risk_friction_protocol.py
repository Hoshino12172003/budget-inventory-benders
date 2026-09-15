from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import experiments.run_e7_risk_friction_local as runner


REUSE_OUTPUT = ROOT / "artifacts/e7_reuse_plan.json"
AUDIT_OUTPUT = ROOT / "artifacts/e7_static_audit.json"
PROTECTED_ROOTS = {
    name: ROOT / f"experiments/results/{path}"
    for name, path in {
        "E1": "e1_empirical_8case_v1",
        "E2": "e2_existing_nominal_robust_v1",
        "E3": "e3_budget_sensitivity_v1",
        "E4": "e4_gamma_sensitivity_v1",
        "E5": "e5_reconfiguration_friction_v1",
        "E6": "e6_budget_risk_interaction_v1",
    }.items()
}


def tree_identity(root: Path) -> str:
    return runner.canonical_hash({
        str(path.relative_to(root)).replace("\\", "/"): runner.sha256(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    })


def overwrite_protection_passes() -> bool:
    with TemporaryDirectory(dir=ROOT) as directory:
        output_root = Path(directory)
        run_id = runner.enumerate_conditions()[0].run_id
        (output_root / run_id).mkdir()
        try:
            runner.check_output_target(run_id, output_root)
        except FileExistsError:
            return True
    return False


def result_root_ignore_audit() -> dict[str, bool]:
    narrow = subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e7_risk_friction_interaction_v1/probe/result.json"],
        cwd=ROOT, check=False,
    ).returncode == 0
    broad = subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e7-not-in-scope/probe/result.json"],
        cwd=ROOT, check=False,
    ).returncode == 0
    return {"narrow_E7_root_ignored": narrow, "unrelated_result_root_not_ignored": not broad}


def build_audit() -> tuple[dict, dict]:
    before = {name: tree_identity(path) for name, path in PROTECTED_ROOTS.items()}
    manifest = runner.load_manifest()
    runner.validate_manifest(manifest)
    plan = runner.build_reuse_plan(manifest)
    reuse = [row for row in plan if row["classification"] == "REUSE"]
    new = [row for row in plan if row["classification"] == "NEW_SOLVE"]
    overlaps = [row for row in plan if len(row["source_candidates"]) == 2]
    expected_cells = sorted(f"{g}-{value}" for g, value in runner.expected_reuse_cells_from_source_design())
    actual_cells = sorted({f"{row['Gamma_token']}-{row['lambda_token']}" for row in reuse})
    preflight = [
        runner.static_feasibility(
            runner.Condition(row["case"], row["Gamma_token"], row["lambda_token"]), manifest
        ) for row in new
    ]
    g4_l2000 = [row for row in preflight if row["Gamma"] == 4 and row["lambda_R"] == 0.2]
    existing_outputs = sorted(path.name for path in runner.RESULT_ROOT.iterdir()) if runner.RESULT_ROOT.exists() else []
    future_outputs = [ROOT / path for path in manifest["future_tables"]]
    future_outputs.extend(ROOT / f"{stem}.{extension}" for stem in manifest["future_figures"] for extension in ("png", "pdf"))
    ignore = result_root_ignore_audit()
    after = {name: tree_identity(path) for name, path in PROTECTED_ROOTS.items()}
    checks = {
        "grid_72_of_72": len(plan) == len({row["run_id"] for row in plan}) == 72,
        "reuse_40_new_32": len(reuse) == 40 and len(new) == 32,
        "reuse_cells_derived": actual_cells == expected_cells,
        "reuse_map_deterministic": plan == runner.build_reuse_plan(manifest),
        "overlap_G2_L0500_once_per_case": len(overlaps) == 8 and all(
            row["Gamma_token"] == "G2" and row["lambda_token"] == "L0500"
            and row["selected_source_experiment"] == "E4" for row in overlaps
        ),
        "all_new_cells_static_feasible": all(row["feasible"] for row in preflight),
        "G4_L2000_static_feasible_8_of_8": len(g4_l2000) == 8 and all(row["feasible"] for row in g4_l2000),
        "authorization_false": manifest["formal_run_authorized"] is False,
        "authorization_scope_E7_only": manifest["authorization_scope"] == [manifest["experiment_id"]],
        "result_root_isolated": all(ignore.values()),
        "no_E7_primary_outputs": not existing_outputs,
        "no_future_tables_or_figures": not any(path.exists() for path in future_outputs),
        "overwrite_protection": overwrite_protection_passes(),
        "timing_contract_frozen": set(manifest["timing_fields"]) == set(
            json.loads((ROOT / manifest["result_schema"]).read_text(encoding="utf-8"))["properties"]["timing"]["required"]
        ),
        "exhaustive_reporting_retained": manifest["reporting_evaluator_contract"]["acceleration_status"] == "NOT_IMPLEMENTED",
        "protected_E1_E6_hashes_preserved": before == after,
    }
    status = "E7_PROTOCOL_STATIC_AUDIT_PASS" if all(checks.values()) else "E7_PROTOCOL_STATIC_AUDIT_BLOCKED"
    reuse_artifact = {
        "schema": "e7_reuse_plan_v1", "status": "PASS" if checks["reuse_40_new_32"] else "BLOCKED",
        "total_conditions": len(plan), "reusable_conditions": len(reuse), "new_solve_conditions": len(new),
        "reuse_parameter_cells": actual_cells,
        "expected_reuse_parameter_cells_from_source_design": expected_cells,
        "overlap_policy": "validate E4/E5 G2-L0500 identity, select E4 once, retain E5 corroboration",
        "conditions": plan,
    }
    audit = {
        "schema": "e7_protocol_static_audit_v1", "status": status, "checks": checks,
        "manifest_sha256": runner.sha256(runner.MANIFEST), "runner_sha256": runner.sha256(Path(runner.__file__)),
        "reuse_plan_canonical_sha256": runner.canonical_hash(reuse_artifact),
        "total_conditions": len(plan), "reusable_conditions": len(reuse), "new_solve_conditions": len(new),
        "overlap_condition_count": len(overlaps), "new_parameter_cells": sorted({f"{r['Gamma_token']}-{r['lambda_token']}" for r in new}),
        "G4_L2000_preflight": g4_l2000, "existing_E7_outputs": existing_outputs,
        "reporting_complexity_G4": {"product_risk_blocks": 6352, "global_scenarios": 3469497},
        "reporting_acceleration": "NOT_IMPLEMENTED_WITHOUT_FULL_EQUIVALENCE_PROOF",
        "protected_result_root_identities": after, "formal_run_authorized": False,
        "formal_first_stage_optimization_solves_executed": 0, "fixed_first_stage_evaluations_executed": 0,
    }
    return reuse_artifact, audit


def main() -> None:
    reuse, audit = build_audit()
    REUSE_OUTPUT.write_text(json.dumps(reuse, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    AUDIT_OUTPUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(audit["status"])
    if audit["status"] != "E7_PROTOCOL_STATIC_AUDIT_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
