from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import experiments.run_e4_gamma_local as runner


OUTPUT = ROOT / "artifacts/e4_gamma_protocol_static_audit.json"


def build_audit() -> dict:
    manifest = runner.load_manifest()
    runner.validate_manifest(manifest)
    identities = runner.load_identities()
    case_checks = {}
    g2_checks = {}
    g0_audits = {}
    for case in runner.CASES:
        runner.validate_case_identity(case, manifest, identities[case])
        case_checks[case] = True
        g2_checks[case] = runner.validate_g2_reuse(case, manifest, identities[case])["checks"]
        g0_audits[case] = runner.classify_g0_reuse(case, manifest, identities[case])

    result_probe = "experiments/results/e4_gamma_sensitivity_v1/audit-probe/result.json"
    ignored = subprocess.run(["git", "check-ignore", "-q", result_probe], cwd=ROOT, check=False).returncode == 0
    broad_probe = "experiments/results/e4-not-in-scope/audit-probe/result.json"
    broad_ignored = subprocess.run(["git", "check-ignore", "-q", broad_probe], cwd=ROOT, check=False).returncode == 0
    existing_outputs = sorted(path.name for path in runner.RESULT_ROOT.iterdir()) if runner.RESULT_ROOT.exists() else []
    verified_g2 = sum(all(checks.values()) for checks in g2_checks.values())
    verified_g0 = sum(audit["eligible"] for audit in g0_audits.values())
    checks = {
        "run_ids_40_of_40": len(manifest["authorized_run_ids"]) == len(set(manifest["authorized_run_ids"])) == 40,
        "cases_8_exact": manifest["cases"] == list(runner.CASES),
        "Gamma_grid_exact": manifest["Gamma_grid"] == list(runner.GAMMA_GRID),
        "beta_frozen": manifest["beta"] == 1.0,
        "lambda_R_frozen": manifest["lambda_R"] == 0.05,
        "B_ref_identity": all(manifest["B_ref_by_case"][case] == json.loads((ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json").read_text(encoding="utf-8"))["B_ref"] for case in runner.CASES),
        "dataset_identity": manifest["dataset_id"] == "RENAULT_EMPIRICAL_8CASE_V1",
        "mapping_identity": all(identity["mapping_hash"] == manifest["mapping_sha256"] for identity in identities.values()),
        "model_identity": runner.source_model_identity() == manifest["model_identity_sha256"],
        "PRB_identity": runner.sha256(runner.PRB_FILE) == manifest["prb_identity_sha256"],
        "solver_profile": manifest["solver_profile"] == runner.FORMAL_SOLVER_PROFILE_ID,
        "runner_identity": runner.sha256(Path(runner.__file__)) == manifest["runner_sha256"],
        "result_root_isolated": ignored and not broad_ignored,
        "no_formal_outputs": not existing_outputs,
        "all_case_identities": all(case_checks.values()),
        "G2_reuse_8_of_8": verified_g2 == 8,
        "G0_reuse_safely_classified": verified_g0 == 0 and all(audit["classification"] == "E4_G0_REUSE_NOT_IDENTITY_SAFE" for audit in g0_audits.values()),
        "authorization_state_valid": manifest["authorization_transition"][-1] is manifest["formal_run_authorized"],
    }
    passed = all(checks.values())
    return {
        "status": "E4_PROTOCOL_STATIC_AUDIT_PASS" if passed else "E4_PROTOCOL_BLOCKED",
        "checks": checks,
        "case_identity_checks": case_checks,
        "Gamma2_reuse_checks": g2_checks,
        "Gamma0_reuse_audits": g0_audits,
        "verified_Gamma2_reuse_count": verified_g2,
        "Gamma0_reuse_classification": "E4_G0_REUSE_NOT_IDENTITY_SAFE",
        "verified_Gamma0_reuse_count": verified_g0,
        "required_new_solve_count": 40 - verified_g2 - verified_g0,
        "existing_E4_outputs": existing_outputs,
        "formal_run_authorized": manifest["formal_run_authorized"],
        "optimization_solves_executed_during_preparation": 0,
        "fixed_first_stage_evaluations_executed_during_preparation": 0,
    }


def main() -> None:
    audit = build_audit()
    OUTPUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(audit["status"])
    if audit["status"] != "E4_PROTOCOL_STATIC_AUDIT_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
