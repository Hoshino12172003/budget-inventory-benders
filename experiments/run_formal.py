from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from robust_inventory_reconfiguration.formal_protocol import (
    RunIdentity,
    canonical_hash,
    file_sha256,
    load_formal_config,
    require_formal_authorization,
    validate_formal_config,
    validate_resume_identity,
)


ROOT = Path(__file__).resolve().parents[1]


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def identity_for(config_path: Path, case_id: str) -> RunIdentity:
    data_path = ROOT / "data" / "formal_instances" / f"{case_id}.json"
    x0_path = ROOT / "artifacts" / f"nominal_baseline_{case_id}.csv"
    if not data_path.exists() or not x0_path.exists():
        raise FileNotFoundError(f"formal identity artifacts are missing for {case_id}")
    config = load_formal_config(config_path)
    source = json.loads(
        (ROOT / "artifacts" / "renault_x0_compatibility_summary.json").read_text(
            encoding="utf-8"
        )
    )["source"]
    parameter_freeze_path = ROOT / config["formal_parameter_freeze"]
    if file_sha256(parameter_freeze_path) != config["formal_parameter_freeze_sha256"]:
        raise ValueError("formal parameter freeze hash mismatch")
    instance_hash = file_sha256(data_path)
    return RunIdentity(
        config_hash=canonical_hash(config),
        source_data_hash=source["official_archive_sha256"],
        data_hash=instance_hash,
        parameter_hash=file_sha256(parameter_freeze_path),
        x0_hash=file_sha256(x0_path),
        git_commit=git_commit(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded formal experiment runner skeleton")
    parser.add_argument("config", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = load_formal_config(config_path)
    validate_formal_config(config)
    freeze_path = ROOT / config["formal_parameter_freeze"]
    if file_sha256(freeze_path) != config["formal_parameter_freeze_sha256"]:
        raise ValueError("formal parameter freeze hash mismatch")
    beta_values = config["parameter_grid"]["beta"]
    materialized_budgets = {
        case: {str(beta): beta * b_ref for beta in beta_values}
        for case, b_ref in config["budget_reference_by_case"].items()
    }
    plan = {
        "experiment_id": config["experiment_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "protocol_status": config["protocol_status"],
        "case_ids": config["case_ids"],
        "budget_rule": config["budget_rule"],
        "budget_reference_by_case": config["budget_reference_by_case"],
        "materialized_budgets_by_beta": materialized_budgets,
        "solver_profile_id": config["solver_profile_id"],
        "config_hash": canonical_hash(config),
        "writes_performed": False,
    }
    if args.checkpoint:
        checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
        validate_resume_identity(
            checkpoint,
            identity_for(config_path, checkpoint["case_id"]),
        )
    if args.execute:
        require_formal_authorization(config)
        raise NotImplementedError("formal solver dispatch requires a separately authorized PR")
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
