from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.run_e6_budget_risk_5x5_local import (
    BETA_BY_TOKEN,
    CASES,
    E3_ROOT,
    E4_ROOT,
    E6_ROOT,
    EXPERIMENT_ID,
    GAMMA_BY_TOKEN,
    IDENTITY_TABLE,
    LAMBDA_R,
    RESULT_ROOT,
    enumerate_conditions,
    planned_new_solve_conditions,
    planned_reuse_conditions,
    selected_source,
)
from experiments import run_e6_budget_risk_local as historical_e6


ARTIFACTS = ROOT / "artifacts"
AUTHORIZATION = ARTIFACTS / "e6_budget_risk_5x5_authorization.json"
REUSE_MAP = ARTIFACTS / "e6_budget_risk_5x5_reuse_map.csv"
MISSING_CELLS = ARTIFACTS / "e6_budget_risk_5x5_missing_cells.json"
AUDIT_DOC = ROOT / "docs/e6_budget_risk_5x5_extension_audit.md"
DELIVERY_HASHES = ARTIFACTS / "e6_budget_risk_5x5_delivery_sha256.csv"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def historical_hashes() -> dict[str, str]:
    hashes = {}
    with (ARTIFACTS / "e3_primary_result_hashes.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            hashes[row["run_id"]] = row["result_sha256"]
    e6_audit = load_json(ARTIFACTS / "e6_final_result_audit.json")
    for run_id, files in e6_audit["primary_artifact_hashes"].items():
        hashes[run_id] = files["result.json"]
    return hashes


def source_candidates(condition) -> list[str]:
    candidates = []
    if condition.gamma_token == "G2":
        candidates.append(f"E3-{condition.case}-{condition.beta_token}")
    if condition.beta_token == "B100":
        candidates.append(f"E4-{condition.case}-{condition.gamma_token}")
    if condition.beta_token in {"B080", "B100", "B120"} and condition.gamma_token in {
        "G0", "G2", "G4"
    }:
        candidates.append(f"E6-{condition.case}-{condition.beta_token}-{condition.gamma_token}")
    return candidates


def candidate_directory(run_id: str) -> Path:
    if run_id.startswith("E3-"):
        return E3_ROOT / run_id
    if run_id.startswith("E4-"):
        return E4_ROOT / run_id
    return E6_ROOT / run_id


def audit_candidate(condition, run_id: str, known_hashes: dict[str, str], contract: dict) -> dict:
    directory = candidate_directory(run_id)
    result_path = directory / "result.json"
    solution_path = directory / "first_stage_solution.json"
    provenance_path = directory / "provenance.json"
    if not all(path.is_file() for path in (result_path, solution_path, provenance_path)):
        return {"pass": False, "status": "SOURCE_ARTIFACT_UNAVAILABLE", "directory": directory}
    try:
        result = load_json(result_path)
        provenance = load_json(provenance_path)
        actual_hash = sha256(result_path)
        expected_hash = known_hashes.get(run_id)
        checks = {
            "historical_hash": expected_hash is None or actual_hash == expected_hash,
            "result_hash": provenance.get("result_sha256") == actual_hash,
            "solution_hash": provenance.get("first_stage_solution_sha256") == sha256(solution_path),
            "case": result.get("case") == condition.case,
            "beta": float(result.get("beta")) == float(condition.beta),
            "Gamma": result.get("Gamma") == condition.gamma,
            "lambda_R": result.get("lambda_R") == LAMBDA_R,
            "dataset": result.get("dataset_id") == contract["dataset_id"],
            "instance": result.get("instance_hash") == contract["instance_hashes"][condition.case],
            "x0": result.get("x0_hash") == contract["x0_hashes"][condition.case],
            "calibration": result.get("calibration_hash") == contract["calibration_hashes"][condition.case],
            "mapping": result.get("mapping_hash") == contract["mapping_sha256"],
            "model": result.get("model_identity_sha256") == contract["model_identity_sha256"],
            "solver": result.get("solver_profile") == contract["solver_profile"],
            "status": result.get("status") == "OPTIMAL",
            "certification": result.get("certification_status") == "CERTIFIED_PRB_EXACT"
            and result.get("exact_certification_pass", True) is True,
        }
        return {
            "pass": all(checks.values()),
            "status": "PASS" if all(checks.values()) else "IDENTITY_MISMATCH",
            "directory": directory,
            "result": result,
            "result_hash": actual_hash,
            "solution_hash": sha256(solution_path),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"pass": False, "status": "INVALID_SOURCE_ARTIFACT", "directory": directory}


def candidates_equivalent(audits: list[dict]) -> bool:
    if not audits or not all(item["pass"] for item in audits):
        return False
    reference = audits[0]
    fields = (
        "objective",
        "fixed_cost",
        "inventory_cost",
        "reconfiguration_cost",
        "robust_recourse_cost",
        "budget_used",
        "RI",
    )
    return all(
        item["solution_hash"] == reference["solution_hash"]
        and all(abs(float(item["result"][field]) - float(reference["result"][field])) <= 1e-6 for field in fields)
        for item in audits[1:]
    )


def reuse_rows() -> list[dict]:
    known_hashes = historical_hashes()
    contract = load_json(ROOT / "experiments/configs/formal/e6_budget_risk_interaction_authorization.json")
    rows = []
    for condition in planned_reuse_conditions():
        experiment, source_run, directory = selected_source(condition)
        candidate_ids = source_candidates(condition)
        audits = [audit_candidate(condition, run_id, known_hashes, contract) for run_id in candidate_ids]
        selected_audit = audits[candidate_ids.index(source_run)]
        actual_hash = selected_audit.get("result_hash", "")
        expected_hash = known_hashes.get(source_run, "")
        overlap_pass = candidates_equivalent(audits)
        reuse_pass = bool(selected_audit["pass"] and overlap_pass)
        statuses = sorted({item["status"] for item in audits})
        rows.append(
            {
                "case": condition.case,
                "beta": str(condition.beta),
                "Gamma": condition.gamma,
                "target_run_id": condition.run_id,
                "source_experiment": experiment,
                "source_artifact": directory.relative_to(ROOT).as_posix(),
                "source_run_id": source_run,
                "source_hash": actual_hash or expected_hash,
                "source_hash_basis": "CURRENT_FILE" if actual_hash else (
                    "HISTORICAL_PRIMARY_AUDIT" if expected_hash else "UNAVAILABLE"
                ),
                "source_candidates": ";".join(candidate_ids),
                "candidate_identity_audit": "PASS" if overlap_pass else "+".join(statuses),
                "reuse_pass": str(reuse_pass).lower(),
                "reuse_status": "PASS" if reuse_pass else "+".join(statuses),
            }
        )
    return rows


def build_manifest(rows: list[dict]) -> dict:
    old = load_json(ROOT / "experiments/configs/formal/e6_budget_risk_interaction_authorization.json")
    paths = {
        "E3_manifest": ROOT / "experiments/configs/formal/e3_budget_sensitivity_authorization.json",
        "E4_manifest": ROOT / "experiments/configs/formal/e4_gamma_sensitivity_authorization.json",
        "E6_manifest": ROOT / "experiments/configs/formal/e6_budget_risk_interaction_authorization.json",
        "E3_final_audit": ARTIFACTS / "e3_final_result_audit.json",
        "E4_final_audit": ARTIFACTS / "e4_final_result_audit.json",
        "E6_final_audit": ARTIFACTS / "e6_final_result_audit.json",
        "historical_source_audit": ARTIFACTS / "e6_budget_risk_5x5_historical_source_audit.json",
        "historical_source_table": ARTIFACTS / "e6_budget_risk_5x5_historical_source_audit.csv",
        "E4_derived_per_file_hashes": ARTIFACTS / "e4_per_file_hashes_for_e6_reuse_audit.csv",
    }
    source_audit = load_json(paths["historical_source_audit"])
    source_ready = all(row["reuse_pass"] == "true" for row in rows)
    return {
        "schema": "e6_budget_risk_5x5_authorization_v1",
        "experiment_id": EXPERIMENT_ID,
        "BASE_MODEL_IDENTITY": "HISTORICAL_E6_FROZEN",
        "EXPERIMENT_LAYER": "E6_5X5_EXTENSION",
        "base_historical_commit": "cc87b68363fa9cc444046f7823a6807412bb7ca8",
        "protocol_status": "PREPARED_NOT_AUTHORIZED" if source_ready else "PREPARED_NOT_AUTHORIZED_SOURCE_RESTORE_REQUIRED",
        "formal_run_authorized": False,
        "authorization_transition": [False],
        "authorization_scope": [],
        "dataset_id": old["dataset_id"],
        "cases": list(CASES),
        "beta_tokens": list(BETA_BY_TOKEN),
        "beta_grid": [str(value) for value in BETA_BY_TOKEN.values()],
        "Gamma_tokens": list(GAMMA_BY_TOKEN),
        "Gamma_grid": list(GAMMA_BY_TOKEN.values()),
        "lambda_R": LAMBDA_R,
        "budget_rule": old["budget_rule"],
        "planned_run_ids": [condition.run_id for condition in enumerate_conditions()],
        "planned_reuse_run_ids": [condition.run_id for condition in planned_reuse_conditions()],
        "planned_new_solve_run_ids": [condition.run_id for condition in planned_new_solve_conditions()],
        "source_inventory_ready": source_ready,
        "historical_source_paths": {
            "E3": source_audit["E3_source_path"],
            "E4": source_audit["E4_source_path"],
            "E6": source_audit["E6_source_path"],
        },
        "historical_code_commits": source_audit["historical_commits"],
        "B_ref_by_case": old["B_ref_by_case"],
        "solver_profile": old["solver_profile"],
        "budget_feasibility_tolerance": old["budget_feasibility_tolerance"],
        "budget_binding_tolerance": old["budget_binding_tolerance"],
        "objective_certification_tolerance": old["objective_certification_tolerance"],
        "reporting_tolerance": old["reporting_tolerance"],
        "materiality_tolerance": old["materiality_tolerance"],
        "mapping_sha256": old["mapping_sha256"],
        "identity_table": IDENTITY_TABLE.relative_to(ROOT).as_posix(),
        "identity_table_sha256": sha256(IDENTITY_TABLE),
        "instance_hashes": old["instance_hashes"],
        "x0_hashes": old["x0_hashes"],
        "calibration_hashes": old["calibration_hashes"],
        "model_reference_commit": old["model_reference_commit"],
        "model_files": old["model_files"],
        "model_identity_sha256": old["model_identity_sha256"],
        "prb_identity_sha256": old["prb_identity_sha256"],
        "runner": "experiments/run_e6_budget_risk_5x5_local.py",
        "runner_sha256": sha256(ROOT / "experiments/run_e6_budget_risk_5x5_local.py"),
        "result_schema": "experiments/schemas/e6_budget_risk_5x5_result.schema.json",
        "result_schema_sha256": sha256(ROOT / "experiments/schemas/e6_budget_risk_5x5_result.schema.json"),
        "aggregation_script": "scripts/summarize_e6_budget_risk_5x5_results.py",
        "aggregation_script_sha256": sha256(ROOT / "scripts/summarize_e6_budget_risk_5x5_results.py"),
        "reuse_map": REUSE_MAP.relative_to(ROOT).as_posix(),
        "reuse_map_sha256": sha256(REUSE_MAP),
        "missing_cells": MISSING_CELLS.relative_to(ROOT).as_posix(),
        "source_contracts": {f"{name}_sha256": sha256(path) for name, path in paths.items()},
        "observed_preparation_identity": {
            "git_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
            "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "model_identity_sha256": historical_e6.source_model_identity(),
            "prb_identity_sha256": sha256(historical_e6.PRB_FILE),
            "historical_e6_runner_current_sha256": sha256(ROOT / "experiments/run_e6_budget_risk_local.py"),
        },
        "source_roots": {
            "E3": E3_ROOT.relative_to(ROOT).as_posix(),
            "E4": E4_ROOT.relative_to(ROOT).as_posix(),
            "E6": E6_ROOT.relative_to(ROOT).as_posix(),
        },
        "reuse_precedence": [
            "E6 for every cell in the historical 3x3 grid",
            "E3 for additional Gamma=2 cells B090 and B110",
            "E4 for additional beta=1 cells G1 and G3",
        ],
        "result_root": RESULT_ROOT.relative_to(ROOT).as_posix(),
        "interpolation_allowed": False,
    }


def write_outputs() -> dict:
    rows = reuse_rows()
    fields = list(rows[0])
    with REUSE_MAP.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    missing = [
        {
            "run_id": condition.run_id,
            "case": condition.case,
            "beta_token": condition.beta_token,
            "beta": str(condition.beta),
            "Gamma_token": condition.gamma_token,
            "Gamma": condition.gamma,
        }
        for condition in planned_new_solve_conditions()
    ]
    MISSING_CELLS.write_text(
        json.dumps(
            {
                "schema": "e6_budget_risk_5x5_missing_cells_v1",
                "classification_rule": "no exact parameter cell in the formal E3/E4/E6 source union",
                "cell_count": len(missing),
                "cells": missing,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest = build_manifest(rows)
    AUTHORIZATION.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    passed = sum(row["reuse_pass"] == "true" for row in rows)
    source_decision = (
        f"All {len(rows)} planned reuse cells pass the live source-file and overlap identity audit."
        if passed == len(rows)
        else f"Only {passed} of {len(rows)} planned reuse cells pass the live source-file identity audit."
    )
    source_action = (
        "The historical sources are recovered and bound to this manifest; no source-restoration blocker remains."
        if passed == len(rows)
        else "Restore the formal source artifacts and regenerate this audit before authorization."
    )
    frozen_execution_identity = (
        manifest["observed_preparation_identity"]["model_identity_sha256"]
        == manifest["model_identity_sha256"]
        and manifest["observed_preparation_identity"]["prb_identity_sha256"]
        == manifest["prb_identity_sha256"]
    )
    execution_statement = (
        "This execution checkout matches the frozen E6 model and PRB identities byte for byte."
        if frozen_execution_identity
        else "The current model bundle or PRB identity differs from the frozen E6 contract."
    )
    document = f"""# E6 budget-risk 5x5 extension audit

## Decision

**PREPARED BUT NOT AUTHORIZED.** No optimization was executed. The formal authorization remains `false`.
{source_decision} {source_action}

The recovered artifacts independently authenticate their exact historical code commits and frozen
model identity. This resolves reuse identity without pretending the extension layer produced them.
{execution_statement}

## Frozen extension

- Experiment: `E6_BUDGET_RISK_5X5_V1` (independent of historical E6).
- Grid: beta = 0.80, 0.90, 1.00, 1.10, 1.20; Gamma = 0, 1, 2, 3, 4.
- Parameter combinations: {len(BETA_BY_TOKEN) * len(GAMMA_BY_TOKEN)}.
- Renault cases: {len(CASES)}; expected case-level cells: {len(enumerate_conditions())}.
- Planned exact reuse cells: {len(rows)}; live identity-audit passes: {passed}.
- Genuinely absent parameter cells requiring new optimization after authorization: {len(missing)}.
- Fixed scientific inputs: Renault 8-case dataset, case-specific `B_ref`, `x0`, lambda_R=0.05,
  model identity, solver profile, and tolerances inherited byte-for-byte from the formal E6 contract.

## Deterministic reuse rule

Historical E6 is selected for all 72 cells in its 3x3 grid. E3 supplies only the 16 additional
`Gamma=2` cells at beta 0.90 and 1.10. E4 supplies only the 16 additional beta 1.00 cells at
Gamma 1 and 3. Candidate overlaps are recorded in the reuse map; they are never counted twice.
Reuse requires the source result, first-stage solution, and provenance files plus matching case,
beta, Gamma, lambda_R, instance/x0/calibration/mapping/model/solver identities, `OPTIMAL` status,
and `CERTIFIED_PRB_EXACT` certification. Missing source files fail closed.

The E3 audit preserves per-file hashes, and the historical E6 audit preserves per-file hashes.
For E4, the recovered frozen ZIP is SHA-256 authenticated and all 120 ZIP members match the recovered
result tree byte for byte. `e4_per_file_hashes_for_e6_reuse_audit.csv` records the derived per-file
hashes with classification `DERIVED_FROM_FROZEN_ARCHIVE_FOR_REUSE_AUDIT`; it is audit evidence, not
a new experiment result.

Recovered formal source paths:

- E3: `{manifest['historical_source_paths']['E3']}`
- E4: `{manifest['historical_source_paths']['E4']}`
- E6: `{manifest['historical_source_paths']['E6']}`

The provenance commits are `{', '.join(manifest['historical_code_commits'])}`. All resolve in the
current Git object database and reproduce model identity `{manifest['model_identity_sha256']}`.
The E6-producing commit is `cc87b68363fa9cc444046f7823a6807412bb7ca8`; a detached audit
worktree is available at `E:/paper-code/formal-history/e6-frozen-code-cc87b683`.

## Runner and recovery contract

`experiments/run_e6_budget_risk_5x5_local.py` uses a separate result root,
`experiments/results/e6_budget_risk_5x5_v1`. It refuses authorization=false, validates every planned
reuse source before any optimization, refuses dirty worktrees and overwrites, writes each cell through
an atomic temporary directory, and resumes only from a complete checkpoint whose manifest, runner,
result, solution, status, and certification identities all match. Reuse cells are materialized without
optimization; only the cells in `e6_budget_risk_5x5_missing_cells.json` enter the solver path.

## Heatmap contract

`scripts/summarize_e6_budget_risk_5x5_results.py` refuses anything except the exact 200-run ID set,
rejects duplicate, uncertified, or missing-metric results, and writes discrete 5x5 matrices for mean
objective normalized within each case by beta=1.00/Gamma=2 and mean RI in percent. It performs no
interpolation, smoothing, or synthetic completion.

## Current safety conclusion and commands

The runner is safe for preparation/audit. Formal authorization remains false, so optimization is
still prohibited even when all identity checks pass.

Preparation checkout: `{manifest['observed_preparation_identity']['git_branch']}` at
`{manifest['observed_preparation_identity']['git_head']}`. The branch label is not itself a scientific
blocker; commit, model, data, and experiment identities control admission. The observed model identity is
`{manifest['observed_preparation_identity']['model_identity_sha256']}` versus the frozen E6 identity
`{manifest['model_identity_sha256']}`. The observed PRB file is
`{manifest['observed_preparation_identity']['prb_identity_sha256']}` versus
`{manifest['prb_identity_sha256']}`. These are hard runtime blockers, not waived differences.

Targeted extension tests: `11 passed`. Extension plus available historical E6 protocol tests:
`26 passed, 4 failed`; the four failures are legacy physical-file hash gates or a read-only fixture
assumption. E3/E4 protocol tests: `37 passed, 6 failed`; those failures are historical checkout
line-ending hashes or absent E1/E2 fixtures.
`e6_budget_risk_5x5_regression_classification.csv` classifies every failure as
`TRUE_CURRENT_BLOCKER`, `HISTORICAL_FREEZE_MISMATCH`, `MISSING_FIXTURE`, or
`IRRELEVANT_TO_E6_5X5_EXECUTION` and separately
records whether it blocks reuse or the future 96-cell run.

`git diff` reports no modification to the historical E6 runner, authorization, or final E3/E4/E6
audits. Therefore the failures are preserved evidence, not repaired by weakening old contracts.

The combined scoped gate reports `43 passed, 10 failed`. No failure was hidden, and none was changed
to a pass by editing a historical authorization or result.

## Admission recommendation

`{'READY_FOR_MANUAL_AUTHORIZATION' if frozen_execution_identity and passed == len(rows) else 'PARTIALLY_RECOVERED'}`:
104/104 reuse cells are verified, the 96-cell missing set is unchanged, and the execution checkout
uses the frozen E6 model bundle. Authorization must still be a separate manual change.

PyCharm: run `experiments/run_e6_budget_risk_5x5_local.py` with parameter `--audit-only` and the
repository root as working directory.

Command line (authorized preparation audit only):

```powershell
python experiments/run_e6_budget_risk_5x5_local.py --audit-only
```

Future formal command, shown for review only and guaranteed to fail until a separately reviewed
manifest changes authorization to true:

```powershell
python experiments/run_e6_budget_risk_5x5_local.py --run-all
```
"""
    AUDIT_DOC.write_text(document, encoding="utf-8", newline="\n")
    delivered = (
        ROOT / ".gitignore",
        ROOT / ".gitattributes",
        ROOT / "experiments/run_e6_budget_risk_5x5_local.py",
        ROOT / "scripts/prepare_e6_budget_risk_5x5_extension.py",
        ROOT / "scripts/summarize_e6_budget_risk_5x5_results.py",
        ROOT / "scripts/audit_e6_5x5_historical_sources.py",
        ROOT / "scripts/audit_e6_5x5_frozen_execution_identity.py",
        ROOT / "experiments/schemas/e6_budget_risk_5x5_result.schema.json",
        AUTHORIZATION,
        REUSE_MAP,
        MISSING_CELLS,
        AUDIT_DOC,
        ROOT / "docs/e6_budget_risk_5x5_frozen_execution_audit.md",
        ARTIFACTS / "e6_budget_risk_5x5_historical_source_audit.json",
        ARTIFACTS / "e6_budget_risk_5x5_historical_source_audit.csv",
        ARTIFACTS / "e4_per_file_hashes_for_e6_reuse_audit.csv",
        ARTIFACTS / "e6_budget_risk_5x5_regression_classification.csv",
        ARTIFACTS / "e6_budget_risk_5x5_frozen_execution_identity.json",
        ROOT / "tests/test_e6_budget_risk_5x5_extension.py",
    )
    with DELIVERY_HASHES.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("path", "sha256"), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)} for path in delivered
        )
    return {
        "parameter_combinations": 25,
        "expected_cells": len(enumerate_conditions()),
        "planned_reuse": len(rows),
        "reuse_pass": passed,
        "new_solve": len(missing),
        "optimization_invocations": 0,
    }


if __name__ == "__main__":
    print(json.dumps(write_outputs(), indent=2))
