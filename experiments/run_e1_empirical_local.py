from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "experiments" / "configs" / "formal" / "e1_empirical_case_freeze.json"
NEW_CASES = ("210129", "210310", "210330", "210323", "210428", "210611")
METHODS = ("direct", "prb")


def validate_execution_gate(case_id: str, method: str, output_root: Path, resume: bool) -> None:
    if case_id not in NEW_CASES:
        raise RuntimeError(f"case is not a frozen new E1 empirical case: {case_id}")
    if method not in METHODS:
        raise RuntimeError(f"unsupported E1 method: {method}")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze["status"] != "E1_EMPIRICAL_DATASET_READY":
        raise RuntimeError("BLOCK_E1_EMPIRICAL_REGION_MAPPING")

    authorization = ROOT / "experiments" / "configs" / "e1_empirical_execution_authorization.json"
    if not authorization.exists():
        raise RuntimeError("E1 empirical execution authorization is missing")
    manifest = json.loads(authorization.read_text(encoding="utf-8"))
    run_id = f"E1-{case_id}-{method.upper()}"
    if manifest.get("authorized_run_ids") != [run_id]:
        raise RuntimeError("authorization must name exactly this one run")
    if manifest.get("e2_e7_authorization") is not False:
        raise RuntimeError("E2-E7 authorization changed")

    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("E1 empirical execution requires a clean committed worktree")
    target = output_root / run_id
    if target.exists() and not resume:
        raise RuntimeError(f"refusing to overwrite existing attempt: {target}")
    if resume and not target.exists():
        raise RuntimeError(f"cannot resume a missing attempt: {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one authorized empirical E1 solve.")
    parser.add_argument("--case", required=True, choices=NEW_CASES)
    parser.add_argument("--method", required=True, choices=METHODS)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "experiments" / "results" / "e1_empirical",
    )
    args = parser.parse_args()
    validate_execution_gate(args.case, args.method, args.output_root, args.resume)
    raise RuntimeError(
        "E1 empirical solve dispatch is intentionally unavailable until the dataset freeze is READY"
    )


if __name__ == "__main__":
    main()
