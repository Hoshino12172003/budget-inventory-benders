from __future__ import annotations

import json
import subprocess
from pathlib import Path

import experiments.run_e3_budget_local as runner


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/e3_budget_sensitivity_static_audit.json"


def main() -> None:
    manifest = runner.load_manifest()
    runner.validate_manifest(manifest)
    identities = runner.load_identities()
    case_checks = {}
    reuse_checks = {}
    for case in manifest["cases"]:
        runner.validate_case_identity(case, manifest, identities[case])
        case_checks[case] = True
        reuse_checks[case] = runner.validate_b100_reuse(case, manifest, identities[case])["checks"]

    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "experiments/results/e3_budget_sensitivity_v1/audit-probe/result.json"],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    checks = {
        "manifest_initially_unauthorized": manifest["formal_run_authorized"] is False,
        "run_ids_40_of_40": len(manifest["authorized_run_ids"]) == len(set(manifest["authorized_run_ids"])) == 40,
        "beta_grid_exact": manifest["beta_grid"] == ["0.80", "0.90", "1.00", "1.10", "1.20"],
        "case_B_ref_8_of_8": len(manifest["B_ref_by_case"]) == 8,
        "instance_hashes_8_of_8": len(manifest["instance_hashes"]) == 8,
        "x0_hashes_8_of_8": len(manifest["x0_hashes"]) == 8,
        "calibration_hashes_8_of_8": len(manifest["calibration_hashes"]) == 8,
        "identity_table_hash": runner.sha256(runner.IDENTITY_TABLE) == manifest["identity_table_sha256"],
        "runner_hash": runner.sha256(Path(runner.__file__)) == manifest["runner_sha256"],
        "model_identity": runner.source_model_identity() == manifest["model_identity_sha256"],
        "result_root_gitignored": ignored,
        "all_case_identities": all(case_checks.values()),
        "all_B100_reuse_identities": all(all(value.values()) for value in reuse_checks.values()),
        "e4_e7_unauthorized": manifest["e4_e7_authorization"] is False,
    }
    status = "E3_PROTOCOL_STATIC_AUDIT_PASS" if all(checks.values()) else "E3_PROTOCOL_STATIC_AUDIT_FAIL"
    payload = {
        "status": status,
        "checks": checks,
        "case_identity_checks": case_checks,
        "B100_reuse_checks": reuse_checks,
        "verified_B100_reuse_count": sum(all(value.values()) for value in reuse_checks.values()),
        "required_new_solve_count": 40 - sum(all(value.values()) for value in reuse_checks.values()),
        "formal_optimization_solves_executed": 0,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(status)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
