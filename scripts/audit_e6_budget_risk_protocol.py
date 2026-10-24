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

import experiments.run_e6_budget_risk_local as runner


REUSE_OUTPUT = ROOT / "artifacts/e6_reuse_plan.json"
AUDIT_OUTPUT = ROOT / "artifacts/e6_static_audit.json"
PROTECTED_ROOTS = {
    experiment: ROOT / f"experiments/results/{path}"
    for experiment, path in {
        "E1": "e1_empirical_8case_v1",
        "E2": "e2_existing_nominal_robust_v1",
        "E3": "e3_budget_sensitivity_v1",
        "E4": "e4_gamma_sensitivity_v1",
        "E5": "e5_reconfiguration_friction_v1",
    }.items()
}


def tree_identity(root: Path) -> str:
    files = {
        str(path.relative_to(root)).replace("\\", "/"): runner.sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    return runner.canonical_hash(files)


def overwrite_protection_passes() -> bool:
    with TemporaryDirectory(dir=ROOT) as directory:
        temporary_root = Path(directory)
        run_id = runner.enumerate_conditions()[0].run_id
        (temporary_root / run_id).mkdir()
        try:
            runner.check_output_target(run_id, temporary_root)
        except FileExistsError:
            return True
    return False


def result_root_ignore_audit() -> dict[str, bool]:
    narrow = subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e6_budget_risk_interaction_v1/probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    broad = subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e6-not-in-scope/probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    return {"narrow_E6_root_ignored": narrow, "unrelated_result_root_not_ignored": not broad}


def build_audit() -> tuple[dict, dict]:
    before = {name: tree_identity(path) for name, path in PROTECTED_ROOTS.items()}
    manifest = runner.load_manifest()
    runner.validate_manifest(manifest)
    plan = runner.build_reuse_plan(manifest)
    identities = runner.load_identities()
    case_identity_checks = {}
    for case in runner.CASES:
        runner.validate_case_identity(case, manifest, identities[case])
        case_identity_checks[case] = True
    preflight = [runner.static_feasibility(case, manifest) for case in runner.CASES]
    new_cells = [row for row in plan if row["classification"] == "NEW_SOLVE"]
    reuse_cells = [row for row in plan if row["classification"] == "REUSE"]
    overlap = [row for row in plan if len(row["source_candidates"]) == 2]
    reuse_parameter_cells = sorted(
        {f"{row['beta_token']}-{row['Gamma_token']}" for row in reuse_cells}
    )
    expected_reuse_parameter_cells = sorted(
        f"{beta}-{gamma}" for beta, gamma in runner.expected_reuse_cells_from_source_design()
    )
    source_counts = {
        experiment: sum(row["selected_source_experiment"] == experiment for row in reuse_cells)
        for experiment in ("E3", "E4")
    }
    existing_outputs = (
        sorted(path.name for path in runner.RESULT_ROOT.iterdir())
        if runner.RESULT_ROOT.exists()
        else []
    )
    ignore_checks = result_root_ignore_audit()
    after = {name: tree_identity(path) for name, path in PROTECTED_ROOTS.items()}
    checks = {
        "grid_72_of_72": len(plan) == len({row["run_id"] for row in plan})
        == len(runner.CASES) * len(runner.BETA_BY_TOKEN) * len(runner.GAMMA_BY_TOKEN),
        "reuse_map_deterministic": plan == runner.build_reuse_plan(manifest),
        "reuse_identity_verified": all(row["selected_source_run"] for row in reuse_cells)
        and len(reuse_cells) == len(runner.CASES) * len(expected_reuse_parameter_cells),
        "reuse_cells_derived": reuse_parameter_cells == expected_reuse_parameter_cells,
        "overlap_B100_G2_once_per_case": len(overlap) == len(runner.CASES)
        and all(row["beta_token"] == "B100" and row["Gamma_token"] == "G2" for row in overlap),
        "new_solve_set_deterministic": len(new_cells) + len(reuse_cells) == len(plan),
        "all_case_identities": all(case_identity_checks.values()),
        "all_new_cells_static_feasible": all(row["feasible"] for row in preflight),
        "B080_G4_corner_static_feasible_8_of_8": sum(row["feasible"] for row in preflight) == len(runner.CASES),
        "result_root_isolated": all(ignore_checks.values()),
        "no_E6_primary_outputs": not existing_outputs,
        "overwrite_protection": overwrite_protection_passes(),
        "reporting_schema_frozen": runner.sha256(ROOT / manifest["result_schema"])
        == manifest["result_schema_sha256"],
        "reporting_pipeline_frozen": runner.sha256(ROOT / manifest["reporting_script"])
        == manifest["reporting_script_sha256"],
        "plotting_pipeline_frozen": runner.sha256(ROOT / manifest["plotting_script"])
        == manifest["plotting_script_sha256"],
        "protocol_document_frozen": runner.sha256(ROOT / manifest["protocol_document"])
        == manifest["protocol_document_sha256"],
        "static_audit_script_frozen": runner.sha256(ROOT / manifest["static_audit_script"])
        == manifest["static_audit_script_sha256"],
        "reuse_plan_frozen": runner.sha256(ROOT / manifest["reuse_plan"])
        == manifest["reuse_plan_sha256"],
        "preauthorization_audit_frozen": runner.git_file_sha256(
            manifest["authorization_basis_commit"], manifest["preauthorization_static_audit"]
        )
        == manifest["preauthorization_static_audit_sha256"],
        "formal_authorization_true": manifest["formal_run_authorized"] is True,
        "authorization_scope_E6_only": manifest["authorization_scope"] == [manifest["experiment_id"]],
        "protected_E1_E5_hashes_preserved": before == after,
    }
    status = "E6_PROTOCOL_STATIC_AUDIT_PASS" if all(checks.values()) else "E6_PROTOCOL_STATIC_AUDIT_BLOCKED"
    reuse_artifact = {
        "schema": "e6_reuse_plan_v1",
        "status": "PASS" if checks["reuse_identity_verified"] else "BLOCKED",
        "total_conditions": len(plan),
        "reusable_conditions": len(reuse_cells),
        "new_solve_conditions": len(new_cells),
        "reuse_parameter_cells": reuse_parameter_cells,
        "expected_reuse_parameter_cells_from_source_design": expected_reuse_parameter_cells,
        "selected_source_counts": source_counts,
        "overlap_policy": "B100-G2 validates E3 and E4 identity, selects E3 once",
        "conditions": plan,
    }
    audit = {
        "schema": "e6_protocol_static_audit_v1",
        "status": status,
        "checks": checks,
        "manifest_sha256": runner.sha256(runner.MANIFEST),
        "runner_sha256": runner.sha256(Path(runner.__file__)),
        "result_schema_sha256": runner.sha256(ROOT / manifest["result_schema"]),
        "reporting_script_sha256": runner.sha256(ROOT / manifest["reporting_script"]),
        "plotting_script_sha256": runner.sha256(ROOT / manifest["plotting_script"]),
        "protocol_document_sha256": runner.sha256(ROOT / manifest["protocol_document"]),
        "static_audit_script_sha256": runner.sha256(ROOT / manifest["static_audit_script"]),
        "reuse_plan_sha256": runner.sha256(ROOT / manifest["reuse_plan"]),
        "authorization_basis_commit": manifest["authorization_basis_commit"],
        "preauthorization_static_audit_sha256": runner.git_file_sha256(
            manifest["authorization_basis_commit"], manifest["preauthorization_static_audit"]
        ),
        "total_conditions": len(plan),
        "reusable_conditions": len(reuse_cells),
        "new_solve_conditions": len(new_cells),
        "reuse_parameter_cells": reuse_parameter_cells,
        "expected_reuse_parameter_cells_from_source_design": expected_reuse_parameter_cells,
        "selected_source_counts": source_counts,
        "overlap_condition_count": len(overlap),
        "case_identity_checks": case_identity_checks,
        "B080_G4_preflight": preflight,
        "existing_E6_outputs": existing_outputs,
        "protected_result_root_identities": after,
        "formal_run_authorized": manifest["formal_run_authorized"],
        "formal_first_stage_optimization_solves_executed": 0,
        "fixed_first_stage_evaluations_executed": 0,
    }
    return reuse_artifact, audit


def main() -> None:
    reuse, audit = build_audit()
    REUSE_OUTPUT.write_text(json.dumps(reuse, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    AUDIT_OUTPUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(audit["status"])
    if audit["status"] != "E6_PROTOCOL_STATIC_AUDIT_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
