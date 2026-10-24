from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/configs/formal/e2_existing_nominal_robust_authorization.json"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
POLICIES = ("EXISTING", "NOMINAL", "ROBUST")

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with (ROOT / "table_empirical_8case_identity.csv").open(encoding="utf-8", newline="") as stream:
        identities = {row["case"]: row for row in csv.DictReader(stream)}
    checks = {}
    for case in CASES:
        checks[case] = {
            "instance_hash": sha256(ROOT / f"data/formal_instances_v2/{case}.json") == identities[case]["instance_hash"],
            "x0_hash": sha256(ROOT / f"artifacts/renault_empirical_8case_v1/x0/{case}.json") == identities[case]["x0_hash"],
            "calibration_hash": sha256(ROOT / f"artifacts/renault_empirical_8case_v1/calibration/{case}.json") == identities[case]["calibration_hash"],
            "mapping_hash": identities[case]["mapping_hash"] == manifest["mapping_sha256"],
        }
    passed = all(all(values.values()) for values in checks.values()) and manifest["lambda_R"] == 0.05 and manifest["Gamma_eval"] == 2 and manifest["solver_profile"] == "gurobi-balanced-1e-8-v1"
    if not passed:
        raise RuntimeError("BLOCK_E2_IDENTITY_MISMATCH")
    manifest.update({
        "formal_run_authorized": True,
        "authorization_transition": [False, True],
        "authorized_run_ids": [f"E2-{case}-{policy}" for case in CASES for policy in POLICIES],
        "runner_sha256": sha256(ROOT / "experiments/run_e2_policy_local.py"),
        "protocol_audit_status": "PASS",
    })
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact = {
        "status": "E2_PROTOCOL_AUTHORIZED_NOT_RUN", "identity_checks": checks,
        "authorized_run_count": 24, "optimization_run_count": 8,
        "fixed_first_stage_evaluation_count": 24, "e1_robust_reuse_count": 8,
        "existing_is_fixed_x0": True, "nominal_plan_gamma": 0, "robust_plan_gamma": 2,
        "common_evaluation_gamma": 2, "direct_reruns": 0, "e2_executed": False,
        "model_changed": False, "dataset_changed": False, "e1_overwritten": False,
        "e3_e7_authorization": False,
    }
    path = ROOT / "artifacts/e2_protocol_static_audit.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
