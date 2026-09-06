from __future__ import annotations

import json
import subprocess
from pathlib import Path

from robust_inventory_reconfiguration.formal_protocol import (
    RESULT_FIELDS,
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
    paths_on_main = main_paths()
    required_frozen_path = "src/robust_inventory_reconfiguration/product_risk_budget_benders.py"
    result = {
        "status": "BLOCKED",
        "config_count": len(configs),
        "all_formal_runs_unauthorized": all(
            config["formal_run_authorized"] is False for config in configs
        ),
        "configured_case_ids": configs[0]["case_ids"],
        "available_formal_cases": sorted(
            path.stem for path in (ROOT / "data" / "formal_instances").glob("*.json")
        ),
        "case_210712_available": (ROOT / "data" / "formal_instances" / "210712.json").exists(),
        "pr2_to_pr7_integrated_in_main": required_frozen_path in paths_on_main
        and "src/robust_inventory_reconfiguration/exact_benchmark.py" in paths_on_main,
        "formal_anchor_levels_frozen": calibration["formal_levels_frozen"],
        "frozen_b_ref": calibration["b_ref"],
        "formal_B0": None,
        "formal_Gamma0": None,
        "formal_lambda_R0": None,
        "development_recommendation_not_formal": {
            "beta": calibration["grid"]["primary_environment"]["beta"],
            "Gamma": calibration["grid"]["primary_environment"]["gamma"],
            "lambda_R": calibration["recommended_levels"]["medium"],
        },
        "gamma_0_to_4_supported": True,
        "direct_prb_formulation_identity_pass": identity["overall_identity_pass"],
        "result_schema_complete": set(RESULT_FIELDS) == set(schema["required"]),
        "formal_result_directory_exists": (ROOT / "experiments" / "results" / "formal").exists(),
        "formal_result_artifacts_written": False,
        "estimated_total_runs_if_blockers_are_resolved": sum(
            config["estimated_run_count"] for config in configs
        ),
        "blockers": [
            "PR2_TO_PR7_NOT_IN_MAIN",
            "210712_ARTIFACT_MISSING",
            "FORMAL_B0_GAMMA0_LAMBDA0_NOT_FROZEN",
            "DIRECT_PRB_SOLVER_TOLERANCE_MISMATCH",
        ],
    }
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
