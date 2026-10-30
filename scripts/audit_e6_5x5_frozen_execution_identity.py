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

from experiments import run_e6_budget_risk_5x5_local as extension
from experiments import run_e6_budget_risk_local as frozen_e6


OUTPUT = ROOT / "artifacts/e6_budget_risk_5x5_frozen_execution_identity.json"
BASE_COMMIT = "cc87b68363fa9cc444046f7823a6807412bb7ca8"
INSTANCE_GENERATION_FILES = (
    "scripts/build_renault_instances.py",
    "scripts/build_renault_empirical_8case_v1.py",
    "scripts/freeze_e1_empirical_cases.py",
    "src/robust_inventory_reconfiguration/renault_empirical.py",
    "src/robust_inventory_reconfiguration/instance.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def main() -> None:
    manifest = extension.load_manifest()
    extension.validate_manifest(manifest)
    instance_hashes = {
        case: sha256(ROOT / f"data/formal_instances_v2/{case}.json") for case in extension.CASES
    }
    generator_hashes = {path: sha256(ROOT / path) for path in INSTANCE_GENERATION_FILES}
    identity = {
        "schema": "e6_budget_risk_5x5_frozen_execution_identity_v1",
        "BASE_MODEL_IDENTITY": "HISTORICAL_E6_FROZEN",
        "EXPERIMENT_LAYER": "E6_5X5_EXTENSION",
        "frozen_execution_checkout": ROOT.as_posix(),
        "base_historical_commit": BASE_COMMIT,
        "experiment_layer_parent_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "frozen_model_sha256": frozen_e6.source_model_identity(),
        "expected_frozen_model_sha256": manifest["model_identity_sha256"],
        "frozen_prb_sha256": sha256(frozen_e6.PRB_FILE),
        "expected_frozen_prb_sha256": manifest["prb_identity_sha256"],
        "new_e6_5x5_runner_sha256": sha256(ROOT / manifest["runner"]),
        "authorization_manifest_sha256": sha256(extension.MANIFEST),
        "reuse_map_sha256": sha256(ROOT / manifest["reuse_map"]),
        "missing_cells_manifest_sha256": sha256(ROOT / manifest["missing_cells"]),
        "identity_table_sha256": sha256(ROOT / manifest["identity_table"]),
        "mapping_sha256": manifest["mapping_sha256"],
        "instance_hashes": instance_hashes,
        "dataset_bundle_sha256": canonical_hash(instance_hashes),
        "instance_generation_file_hashes": generator_hashes,
        "instance_generation_identity_sha256": canonical_hash(generator_hashes),
        "solver_profile": manifest["solver_profile"],
        "solver_tolerance_contract": {
            key: manifest[key]
            for key in (
                "budget_feasibility_tolerance",
                "budget_binding_tolerance",
                "objective_certification_tolerance",
                "reporting_tolerance",
                "materiality_tolerance",
            )
        },
        "formal_run_authorized": manifest["formal_run_authorized"],
        "source_inventory_ready": manifest["source_inventory_ready"],
        "verified_reuse_cells": len(extension.planned_reuse_conditions()),
        "missing_solve_cells": len(extension.planned_new_solve_conditions()),
        "optimization_calls": 0,
    }
    checks = {
        "base_commit_exists": subprocess.run(
            ["git", "cat-file", "-e", f"{BASE_COMMIT}^{{commit}}"], cwd=ROOT
        ).returncode
        == 0,
        "model": identity["frozen_model_sha256"] == identity["expected_frozen_model_sha256"],
        "prb": identity["frozen_prb_sha256"] == identity["expected_frozen_prb_sha256"],
        "instances": instance_hashes == manifest["instance_hashes"],
        "authorization_false": manifest["formal_run_authorized"] is False,
        "reuse_ready": manifest["source_inventory_ready"] is True,
        "counts": identity["verified_reuse_cells"] == 104
        and identity["missing_solve_cells"] == 96,
    }
    identity["checks"] = checks
    identity["status"] = "PASS" if all(checks.values()) else "FAIL"
    OUTPUT.write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(identity, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
