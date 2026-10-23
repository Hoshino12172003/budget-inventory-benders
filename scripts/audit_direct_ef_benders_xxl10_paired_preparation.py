from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_direct_scaling_xxl10_preparation import theoretical_direct_size
from scripts.audit_ef_benders_scaling_l10_preparation import theoretical_size
from scripts.run_direct_scaling_xxl10_paired_pilot import build_dry_run as direct_dry_run
from scripts.run_ef_benders_scaling_xxl10_paired_pilot import build_dry_run as ef_dry_run


DEFAULT_OUTPUT = ROOT / "artifacts/direct_ef_benders_xxl10_paired_preparation_audit.json"


def _worker_peaks(root: Path, prefix: str) -> list[dict]:
    rows = []
    for path in sorted(root.glob(f"worker_logs/{prefix}*/attempt-*/resource_monitor.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        rows.append({
            "path": path.relative_to(ROOT).as_posix(),
            "peak_process_tree_memory_gib": row.get("peak_process_tree_memory_gib"),
            "stop_reason": row.get("stop_reason"),
            "worker_return_code": row.get("worker_return_code"),
        })
    return rows


def build_audit() -> dict:
    direct = direct_dry_run()
    ef = ef_dry_run()
    direct_size = theoretical_direct_size(36, 36, 16, 2)
    ef_size = theoretical_size(36, 36, 16, 2)
    direct_xl = theoretical_direct_size(30, 30, 14, 2)
    ef_xl = theoretical_size(30, 30, 14, 2)
    direct_history = _worker_peaks(ROOT / "experiments/results/direct_scaling_extension_v1", "DIRECT_XL10_S")
    ef_history = [
        *_worker_peaks(ROOT / "experiments/results/ef_benders_scaling_xl10_pilot_v1", "EF_XL10_S"),
        *_worker_peaks(ROOT / "experiments/results/ef_benders_scaling_xl10_remaining9_v1", "EF_XL10_S"),
    ]
    direct_success_peaks = [row["peak_process_tree_memory_gib"] for row in direct_history if row["stop_reason"] is None and row["worker_return_code"] == 0]
    ef_success_peaks = [row["peak_process_tree_memory_gib"] for row in ef_history if row["stop_reason"] is None and row["worker_return_code"] == 0]
    identity_checks = {
        "same_instance_hash": direct["input_identity"]["instance_hash"] == ef["condition"]["instance_hash"],
        "same_x0_hash": direct["input_identity"]["x0_hash"] == ef["condition"]["x0_hash"],
        "same_instance_file": direct["input_identity"]["instance_sha256"] == ef["condition"]["instance_sha256"],
        "same_preparation_file": direct["input_identity"]["preparation_sha256"] == ef["condition"]["preparation_sha256"],
        "same_source_instance": direct["input_identity"]["source_instance_id"] == ef["condition"]["source_instance_id"],
        "direct_identity": all(direct["identity_checks"].values()),
        "ef_identity": all(ef["identity_checks"].values()),
        "authorization_separate_and_closed": direct["formal_run_authorized"] is False and ef["formal_run_authorized"] is False,
        "output_roots_separate": direct["condition"]["condition_id"].startswith("DIRECT_") and ef["condition"]["condition"]["condition_id"].startswith("EF_"),
        "zero_optimization": direct["optimization_calls"] == ef["optimization_calls"] == 0,
    }
    return {
        "schema": "direct_ef_benders_xxl10_paired_preparation_audit_v1",
        "optimization_calls": 0,
        "identity_checks": identity_checks,
        "frozen_instance": {
            "source_instance_id": "ASC_INSTANCE_XXL10_S20260921",
            "instance_hash": "81739c07edea3babcb62bbaf91ac6ac37eb13c3201052071c5610c4e8a328f94",
            "x0_hash": "65813dd3712757d9e6f4fa742525041ea32667b6ded2afda8096b1665aedda03",
            "instance_sha256": "2ebc009d6f00065ecd948070210075b715154257d17c1701acf1b937b821088f",
            "preparation_sha256": "17030da831a58cecce755bade73b245b4cdc8db18ebb1f4d5b4171e1e01ca39a",
            "dimensions": {"I": 36, "R": 36, "J": 16},
            "Gamma": 2,
        },
        "model_size": {
            "Direct": {
                "variables": direct_size["variable_count"],
                "binary_variables": direct_size["binary_variable_count"],
                "constraints": direct_size["constraint_count"],
                "nonzeros": direct_size["nonzero_count"],
                "scenario_blocks": direct_size["scenario_blocks"],
                "relative_to_xl10_nonzeros": direct_size["nonzero_count"] / direct_xl["nonzero_count"],
            },
            "EF-BD": {
                **ef_size["ef_oracle"],
                "binary_variables": 0,
                "scenario_blocks": ef_size["product_local_scenario_blocks"],
                "relative_to_xl10_nonzeros": ef_size["ef_oracle"]["nonzeros"] / ef_xl["ef_oracle"]["nonzeros"],
            },
            "evidence_class": "THEORETICAL_EXACT_COUNTS_FROM_MODEL_FORMULAS_NO_GUROBI_MODEL_BUILD",
        },
        "historical_memory": {
            "Direct_XL10": {
                "attempts": len(direct_history),
                "maximum_certified_peak_gib": max(direct_success_peaks),
                "maximum_all_attempt_peak_gib": max(row["peak_process_tree_memory_gib"] for row in direct_history),
                "linear_nonzero_scaled_certified_peak_gib": max(direct_success_peaks) * direct_size["nonzero_count"] / direct_xl["nonzero_count"],
                "warning": "The scaled value exceeds the 13-GiB cap and is not a memory prediction; Direct completion risk is high.",
            },
            "EF_BD_XL10": {
                "attempts": len(ef_history),
                "maximum_certified_peak_gib": max(ef_success_peaks),
                "linear_nonzero_scaled_peak_gib": max(ef_success_peaks) * ef_size["ef_oracle"]["nonzeros"] / ef_xl["ef_oracle"]["nonzeros"],
                "warning": "The scaled value is only a risk reference; Barrier factorization, Crossover, Python objects, and allocator behavior are nonlinear.",
            },
        },
        "Direct": direct,
        "EF-BD": ef,
        "recommendation": {
            "current_machine": "DO_NOT_EXECUTE_WHILE_LIVE_STARTUP_GATES_FAIL",
            "Direct": "RESOURCE_BLOCKED; even after 16 GiB becomes available, one monitored attempt has high probability of hitting the unchanged 13-GiB cap.",
            "EF-BD": "RESOURCE_BLOCKED; reconsider one monitored attempt only after at least 17 GiB is available. Completion is not guaranteed.",
            "pairing": "Never run both methods concurrently; authorize and execute each protocol separately.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    audit = build_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "direct_decision": audit["Direct"]["decision"],
        "ef_benders_decision": audit["EF-BD"]["decision"],
        "optimization_calls": audit["optimization_calls"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
