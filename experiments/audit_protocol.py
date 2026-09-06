from __future__ import annotations

import json
import subprocess
from pathlib import Path

from robust_inventory_reconfiguration.formal_protocol import (
    RESULT_FIELDS,
    file_sha256,
    load_formal_config,
    validate_formal_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "experiments" / "configs" / "formal"


def main_paths() -> set[str]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "origin/main"], cwd=ROOT, text=True
    )
    return set(output.splitlines())


def audit() -> dict[str, object]:
    configs = []
    for path in sorted(CONFIG_DIR.glob("e*.yaml")):
        config = load_formal_config(path)
        validate_formal_config(config)
        configs.append(config)
    schema = json.loads(
        (ROOT / "experiments" / "schemas" / "formal_result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    identity = json.loads(
        (ROOT / "experiments" / "audits" / "direct_prb_formulation_identity.json").read_text(
            encoding="utf-8"
        )
    )
    calibration = json.loads(
        (ROOT / "artifacts" / "lambda_calibration_summary.json").read_text(encoding="utf-8")
    )
    freeze = json.loads(
        (CONFIG_DIR / "formal_parameter_freeze.json").read_text(encoding="utf-8")
    )
    freeze_hash = file_sha256(CONFIG_DIR / "formal_parameter_freeze.json")
    freeze_hash_references_pass = all(
        config["formal_parameter_freeze_sha256"] == freeze_hash for config in configs
    )
    paths_on_main = main_paths()
    required_frozen_path = "src/robust_inventory_reconfiguration/product_risk_budget_benders.py"
    evidence_hashes_pass = all(
        file_sha256(ROOT / item["path"]) == item["sha256"]
        for item in freeze["evidence"].values()
        if isinstance(item, dict) and "path" in item
    )
    formal_case_hashes_pass = all(
        file_sha256(ROOT / "data" / "formal_instances" / f"{case}.json") == digest
        for case, digest in freeze["evidence"]["formal_instance_sha256"].items()
    )
    x0_hashes_pass = all(
        file_sha256(ROOT / "artifacts" / f"nominal_baseline_{case}.csv") == digest
        for case, digest in freeze["evidence"]["nominal_baseline_x0_sha256"].items()
    )
    instances = {
        case: json.loads(
            (ROOT / "data" / "formal_instances" / f"{case}.json").read_text(
                encoding="utf-8"
            )
        )
        for case in freeze["formal_case_ids"]
    }
    uncertainty_item_counts = {
        case: len(instance["region_ids"]) * len(instance["product_ids"])
        for case, instance in instances.items()
    }
    gamma_0_to_4_supported = all(
        count == 96 and len(instances[case]["region_ids"]) >= 4
        for case, count in uncertainty_item_counts.items()
    )
    budget_baseline_freeze_pass = all(
        freeze["baseline"]["B"][case]
        == freeze["baseline"]["beta"] * freeze["B_ref"][case]
        for case in freeze["formal_case_ids"]
    )
    lambda_baseline_freeze_pass = (
        calibration["ready_to_freeze_formal_levels"]
        and calibration["response_nondegenerate_in_both_cases"]
        and calibration["recommended_levels"]["medium"]
        == freeze["baseline"]["lambda_R"]
    )
    level_freeze_pass = freeze["levels"] == {
        "E3_beta": [0.8, 0.9, 1.0, 1.1, 1.2],
        "E4_Gamma": [0, 1, 2, 3, 4],
        "E5_lambda_R": [0.0, 0.0025, 0.01, 0.05, 0.2],
        "E6_beta": [0.8, 1.0, 1.2],
        "E6_Gamma": [0, 2, 4],
        "E7_Gamma": [0, 2, 4],
        "E7_lambda_R": [0.0025, 0.05, 0.2],
    }
    ready = (
        len(configs) == 7
        and all(config["protocol_status"] == "PROTOCOL_READY" for config in configs)
        and all(config["formal_run_authorized"] is False for config in configs)
        and all(config["case_ids"] == ["210202", "210628"] for config in configs)
        and identity["overall_identity_pass"]
        and evidence_hashes_pass
        and formal_case_hashes_pass
        and x0_hashes_pass
        and freeze_hash_references_pass
        and gamma_0_to_4_supported
        and budget_baseline_freeze_pass
        and freeze["baseline"]["Gamma"] == 2
        and lambda_baseline_freeze_pass
        and level_freeze_pass
    )
    result = {
        "status": "PROTOCOL_READY" if ready else "BLOCKED",
        "config_count": len(configs),
        "all_formal_runs_unauthorized": all(
            config["formal_run_authorized"] is False for config in configs
        ),
        "configured_case_ids": configs[0]["case_ids"],
        "available_formal_cases": sorted(
            path.stem for path in (ROOT / "data" / "formal_instances").glob("*.json")
        ),
        "formal_case_identity_pass": all(
            config["case_ids"] == ["210202", "210628"] for config in configs
        ),
        "case_210712_in_formal_chain": False,
        "case_210712_note": (
            "raw archive available but outside the current formal processing/calibration chain"
        ),
        "pr2_to_pr7_integrated_in_main": required_frozen_path in paths_on_main
        and "src/robust_inventory_reconfiguration/exact_benchmark.py" in paths_on_main,
        "formal_anchor_levels_frozen": freeze["status"] == "FORMAL_PARAMETER_FREEZE_PASS",
        "frozen_b_ref": freeze["B_ref"],
        "formal_beta0": freeze["baseline"]["beta"],
        "formal_B0": freeze["baseline"]["B"],
        "formal_Gamma0": freeze["baseline"]["Gamma"],
        "formal_lambda_R0": freeze["baseline"]["lambda_R"],
        "development_evidence_ready_to_freeze": calibration["ready_to_freeze_formal_levels"],
        "uncertainty_item_counts": uncertainty_item_counts,
        "gamma_0_to_4_supported": gamma_0_to_4_supported,
        "budget_baseline_freeze_pass": budget_baseline_freeze_pass,
        "gamma_baseline_freeze_pass": freeze["baseline"]["Gamma"] == 2,
        "lambda_baseline_freeze_pass": lambda_baseline_freeze_pass,
        "e3_to_e7_level_freeze_pass": level_freeze_pass,
        "direct_prb_formulation_identity_pass": identity["overall_identity_pass"],
        "solver_tolerance_identity_pass": identity["checks"]["same_solver_tolerances"]["pass"],
        "evidence_hashes_pass": evidence_hashes_pass,
        "formal_case_hashes_pass": formal_case_hashes_pass,
        "x0_hashes_pass": x0_hashes_pass,
        "parameter_freeze_hash_references_pass": freeze_hash_references_pass,
        "result_schema_complete": set(RESULT_FIELDS) == set(schema["required"]),
        "formal_result_directory_exists": (ROOT / "experiments" / "results" / "formal").exists(),
        "formal_result_artifacts_written": False,
        "formal_total_run_count": sum(
            config["estimated_run_count"] for config in configs
        ),
        "blockers": [] if ready else ["PROTOCOL_VALIDATION_FAILED"],
    }
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
