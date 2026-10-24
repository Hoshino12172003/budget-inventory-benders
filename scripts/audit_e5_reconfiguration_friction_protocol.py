from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.run_e5_lambda_local import (
    BETA,
    CASES,
    GAMMA,
    LAMBDA_BY_TOKEN,
    MANIFEST,
    REPORTING_FILE,
    RESULT_ROOT,
    expected_run_ids,
    incumbent_feasibility,
    load_identities,
    load_manifest,
    sha256,
    source_model_identity,
    validate_case_identity,
    validate_l0500_reuse,
    validate_manifest,
)
from robust_inventory_reconfiguration.e5_reporting import (
    canonical_adjustment,
    maximum_adjustment_difference,
)
from robust_inventory_reconfiguration.first_stage_solution import (
    load_first_stage_solution_artifact,
    matrix_from_artifact,
)
from robust_inventory_reconfiguration.instance import load_instance


OUTPUT = ROOT / "artifacts/e5_reconfiguration_friction_protocol_static_audit.json"
FORMAL_ROOTS = (
    ROOT / "experiments/results/e1_empirical_8case_v1",
    ROOT / "experiments/results/e2_existing_nominal_robust_v1",
    ROOT / "experiments/results/e3_budget_sensitivity_v1",
    ROOT / "experiments/results/e4_gamma_sensitivity_v1",
)


def file_hashes() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for result_root in FORMAL_ROOTS
        for path in sorted(result_root.glob("*/*"))
        if path.is_file()
    }


def positive_friction_adjustment_audit(case: str) -> dict:
    instance = load_instance(ROOT / f"data/formal_instances_v2/{case}.json")
    x0 = json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json").read_text(encoding="utf-8"))["x0"]
    artifact = load_first_stage_solution_artifact(
        ROOT / f"experiments/results/e4_gamma_sensitivity_v1/E4-{case}-G2/first_stage_solution.json",
        instance,
    )
    x = matrix_from_artifact(artifact, instance, "x")
    solver_plus = matrix_from_artifact(artifact, instance, "a_plus")
    solver_minus = matrix_from_artifact(artifact, instance, "a_minus")
    canonical = canonical_adjustment(x, x0)
    return {
        "case": case,
        "maximum_coordinate_difference": maximum_adjustment_difference(
            canonical, solver_plus, solver_minus
        ),
        "canonical_RI": canonical.reconfiguration_index,
        "stored_RI": artifact["RI"],
    }


def other_formal_reuse_candidates() -> list[dict]:
    candidates = []
    other_levels = {0.0, 0.0025, 0.01, 0.20}
    for result_root in FORMAL_ROOTS:
        for path in sorted(result_root.glob("*/result.json")):
            result = json.loads(path.read_text(encoding="utf-8"))
            value = result.get("lambda_R")
            if value in other_levels and result.get("dataset_id") == "RENAULT_EMPIRICAL_8CASE_V1":
                candidates.append({
                    "run_id": result.get("run_id"),
                    "lambda_R": value,
                    "path": path.relative_to(ROOT).as_posix(),
                })
    return candidates


def main() -> None:
    before = file_hashes()
    manifest = load_manifest()
    validate_manifest(manifest, require_authorized=False)
    identities = load_identities()
    for case in CASES:
        validate_case_identity(case, manifest, identities[case])

    reuse = []
    for case in CASES:
        source = validate_l0500_reuse(case, manifest, identities[case])
        reuse.append({
            "case": case,
            "source_run": source["result"]["run_id"],
            "identity_complete": all(source["checks"].values()),
            "checks": source["checks"],
        })

    incumbent = [incumbent_feasibility(case, manifest) for case in CASES]
    positive_adjustment = [positive_friction_adjustment_audit(case) for case in CASES]
    other_reuse = other_formal_reuse_candidates()
    synthetic_x0 = [[2.0, 5.0], [3.0, 7.0]]
    synthetic_x = [[4.0, 1.0], [3.0, 8.0]]
    zero_friction = canonical_adjustment(synthetic_x, synthetic_x0)
    zero_friction_expected_plus = [[2.0, 0.0], [0.0, 1.0]]
    zero_friction_expected_minus = [[0.0, 4.0], [0.0, 0.0]]
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e5_reconfiguration_friction_v1/probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    output_count = 0 if not RESULT_ROOT.exists() else sum(1 for path in RESULT_ROOT.iterdir() if path.is_dir())
    e4_manifest = json.loads((ROOT / "experiments/configs/formal/e4_gamma_sensitivity_authorization.json").read_text(encoding="utf-8"))
    after = file_hashes()
    checks = {
        "exact_40_run_ids": len(expected_run_ids()) == len(set(expected_run_ids())) == 40,
        "exact_8_cases": len(CASES) == len(set(CASES)) == 8,
        "exact_5_lambda_levels": list(LAMBDA_BY_TOKEN.values()) == [0.0, 0.0025, 0.01, 0.05, 0.20],
        "beta_fixed": BETA == manifest["beta"] == 1.0,
        "Gamma_fixed": GAMMA == manifest["Gamma"] == 2,
        "B_ref_unchanged": manifest["B_ref_by_case"] == e4_manifest["B_ref_by_case"],
        "dataset_unchanged": manifest["dataset_id"] == e4_manifest["dataset_id"],
        "mapping_unchanged": manifest["mapping_sha256"] == e4_manifest["mapping_sha256"],
        "model_unchanged": source_model_identity() == manifest["model_identity_sha256"] == e4_manifest["model_identity_sha256"],
        "solver_profile_unchanged": manifest["solver_profile"] == e4_manifest["solver_profile"],
        "L0500_reuse_identity_8_of_8": len(reuse) == 8 and all(row["identity_complete"] for row in reuse),
        "other_formal_reuse_zero": not other_reuse and manifest["reuse_policy"]["other_grid_levels_reuse"] is False,
        "lambda_zero_canonical_adjustment": zero_friction.a_plus == zero_friction_expected_plus and zero_friction.a_minus == zero_friction_expected_minus,
        "lambda_zero_canonical_RI": zero_friction.reconfiguration_index == 7.0 / 17.0,
        "lambda_zero_RS_zero": manifest["reporting_canonicalization"]["RS_at_lambda_zero"] == 0.0,
        "positive_friction_canonical_consistency": all(row["maximum_coordinate_difference"] <= 1e-6 and abs(row["canonical_RI"] - row["stored_RI"]) <= 1e-6 for row in positive_adjustment),
        "incumbent_feasibility_backstop_8_of_8": all(row["feasible"] for row in incumbent),
        "result_root_isolated": ignored,
        "no_new_formal_outputs": output_count == 0,
        "runner_hash": sha256(ROOT / "experiments/run_e5_lambda_local.py") == manifest["runner_sha256"],
        "reporting_hash": sha256(REPORTING_FILE) == manifest["reporting_contract_sha256"],
        "prior_formal_results_preserved": before == after,
        "authorization_state_valid": manifest["authorization_transition"] in ([False], [False, True]) and manifest["authorization_transition"][-1] is manifest["formal_run_authorized"],
    }
    ready = all(checks.values())
    payload = {
        "schema": "e5_reconfiguration_friction_protocol_static_audit_v1",
        "status": "E5_PROTOCOL_STATIC_AUDIT_PASS" if ready else "E5_PROTOCOL_BLOCKED",
        "checks": checks,
        "cases": list(CASES),
        "lambda_levels": [{"token": token, "value": value} for token, value in LAMBDA_BY_TOKEN.items()],
        "total_formal_conditions": 40,
        "L0500_reuse_count": sum(row["identity_complete"] for row in reuse),
        "L0500_reuse_source": "E4-<case>-G2",
        "L0500_reuse_audit": reuse,
        "other_reuse_count": len(other_reuse),
        "other_reuse_candidates": other_reuse,
        "formal_roots_scanned_for_other_reuse": [path.relative_to(ROOT).as_posix() for path in FORMAL_ROOTS],
        "required_new_solves": 32,
        "incumbent_feasibility": incumbent,
        "positive_friction_adjustment_audit": positive_adjustment,
        "lambda_zero_degeneracy": {
            "present_in_economic_model": True,
            "effect": "a_plus and a_minus can increase together without cost at lambda_R=0",
            "resolved_in_primary_model": False,
            "reporting_resolution": "canonical adjustment derived deterministically from x-x0",
            "canonical_total_adjustment": zero_friction.total_adjustment,
            "canonical_RI": zero_friction.reconfiguration_index,
            "RS": 0.0,
        },
        "formal_run_authorized": manifest["formal_run_authorized"],
        "ready_for_authorization": ready,
        "formal_output_count": output_count,
        "optimization_solves_executed_during_preparation": 0,
        "blocked_items": [] if ready else [name for name, passed in checks.items() if not passed],
        "E1_overwritten": False,
        "E2_overwritten": False,
        "E3_overwritten": False,
        "E4_overwritten": False,
        "model_changed": False,
        "dataset_changed": False,
        "B_ref_changed": False,
        "beta_changed": False,
        "Gamma_changed": False,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["status"])
    if not ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
