from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.run_e6_budget_risk_5x5_local import (
    BETA_BY_TOKEN,
    CASES,
    GAMMA_BY_TOKEN,
    RESULT_ROOT,
    enumerate_conditions,
)


OBJECTIVE_MATRIX = ROOT / "artifacts/e6_budget_risk_5x5_mean_normalized_objective.csv"
RI_MATRIX = ROOT / "artifacts/e6_budget_risk_5x5_mean_ri_percent.csv"


def load_complete_results(result_root: Path = RESULT_ROOT) -> dict[str, dict]:
    expected = {condition.run_id for condition in enumerate_conditions()}
    results: dict[str, dict] = {}
    for path in sorted(result_root.glob("*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        run_id = result.get("run_id")
        if run_id in results:
            raise ValueError(f"duplicate E6-5X5 result: {run_id}")
        results[run_id] = result
    if set(results) != expected:
        raise ValueError(
            f"incomplete E6-5X5 results: missing={len(expected - set(results))}, "
            f"extra={len(set(results) - expected)}"
        )
    for run_id, result in results.items():
        if result.get("status") != "OPTIMAL" or result.get("certification_status") != "CERTIFIED_PRB_EXACT":
            raise ValueError(f"uncertified E6-5X5 result: {run_id}")
        for metric in ("objective", "RI"):
            if result.get(metric) is None:
                raise ValueError(f"missing {metric}: {run_id}")
    return results


def matrices(results: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    normalized: dict[tuple[str, str, str], float] = {}
    for case in CASES:
        reference_id = f"E6-5X5-{case}-B100-G2"
        reference = float(results[reference_id]["objective"])
        if reference <= 0.0:
            raise ValueError(f"nonpositive normalization reference: {reference_id}")
        for condition in (item for item in enumerate_conditions() if item.case == case):
            normalized[(case, condition.beta_token, condition.gamma_token)] = (
                float(results[condition.run_id]["objective"]) / reference
            )
    objective_rows = []
    ri_rows = []
    for beta_token, beta in BETA_BY_TOKEN.items():
        objective_row = {"beta_token": beta_token, "beta": float(beta)}
        ri_row = {"beta_token": beta_token, "beta": float(beta)}
        for gamma_token in GAMMA_BY_TOKEN:
            objective_row[gamma_token] = statistics.mean(
                normalized[(case, beta_token, gamma_token)] for case in CASES
            )
            ri_row[gamma_token] = 100.0 * statistics.mean(
                float(results[f"E6-5X5-{case}-{beta_token}-{gamma_token}"]["RI"])
                for case in CASES
            )
        objective_rows.append(objective_row)
        ri_rows.append(ri_row)
    return objective_rows, ri_rows


def write_matrix(path: Path, rows: list[dict]) -> None:
    fields = ["beta_token", "beta", *GAMMA_BY_TOKEN]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    objective_rows, ri_rows = matrices(load_complete_results())
    write_matrix(OBJECTIVE_MATRIX, objective_rows)
    write_matrix(RI_MATRIX, ri_rows)
    print(json.dumps({"objective_matrix": str(OBJECTIVE_MATRIX), "RI_matrix": str(RI_MATRIX)}, indent=2))


if __name__ == "__main__":
    main()
