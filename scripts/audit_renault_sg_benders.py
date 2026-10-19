from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
CONFIG = ROOT / "experiments/configs/development/renault_sg_benders_v1_draft.yaml"
REFERENCE = ROOT / "experiments/configs/development/renault_enhanced_basic_benders_v1.yaml"
RESULT_ROOT = ROOT / "experiments/results/renault_enhanced_basic_benders_development_v1/runs"
OUTPUT = ROOT / "artifacts/renault_sg_bd_static_audit.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit() -> dict:
    from experiments.run_renault_vanilla_bd_pilot import load_frozen_renault_case
    from robust_inventory_reconfiguration.scenario_generation_single_cut import (
        static_pruning_screen,
    )

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    identity_reference_ok = (
        sha256(REFERENCE) == config["frozen_identity_reference"]["sha256"]
    )
    rows = []
    for case in config["case_ids"]:
        loaded = load_frozen_renault_case(case)
        expected_identity = reference["frozen_case_identity"][case]
        identity_ok = loaded["identity"] == expected_identity
        canonical = RESULT_ROOT / f"EB_RENAULT_{case}"
        result = json.loads((canonical / "result.json").read_text(encoding="utf-8"))
        first_stage = json.loads(
            (canonical / "first_stage_solution.json").read_text(encoding="utf-8")
        )
        incumbent = result["independent_global_certification"]["certified_recourse"]
        started = perf_counter()
        screen = static_pruning_screen(
            loaded["instance"], first_stage["x"], loaded["gamma"], incumbent
        )
        rows.append({
            "case": case,
            "identity_ok": identity_ok,
            "instance_hash": loaded["identity"]["instance_hash"],
            "certified_final_recourse_incumbent": incumbent,
            "screen_seconds": perf_counter() - started,
            **screen,
        })
    gates = {
        "formal_run_authorized_false": config["formal_run_authorized"] is False,
        "oracle_diagnostic_authorized_false": config["oracle_diagnostic_authorized"] is False,
        "frozen_identity_reference": identity_reference_ok,
        "all_eight_identities": len(rows) == 8 and all(row["identity_ok"] for row in rows),
        "all_scenario_counts": all(row["total_scenarios"] == 4657 for row in rows),
        "static_pruning_potential": all(row["leaf_pruning_fraction"] > 0.99 for row in rows),
    }
    return {
        "schema": "renault_sg_bd_static_audit_v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "decision": "READY_FOR_ORACLE_DIAGNOSTIC" if all(gates.values()) else "NO_GO",
        "interpretation": (
            "Optimistic final-solution screen using an already-certified incumbent; "
            "not an Oracle runtime result and not evidence of full-run speedup."
        ),
        "gates": gates,
        "cases": rows,
        "config_sha256": sha256(CONFIG),
        "implementation_sha256": sha256(
            ROOT / "src/robust_inventory_reconfiguration/scenario_generation_single_cut.py"
        ),
        "optimization_calls": 0,
    }


if __name__ == "__main__":
    audit = build_audit()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    raise SystemExit(0 if audit["status"] == "PASS" else 1)
