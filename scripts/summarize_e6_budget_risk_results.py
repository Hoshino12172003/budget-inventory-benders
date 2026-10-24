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

from experiments.run_e6_budget_risk_local import (
    BETA_BY_TOKEN,
    CASES,
    GAMMA_BY_TOKEN,
    RESULT_ROOT,
    enumerate_conditions,
    load_manifest,
)


ARTIFACTS = ROOT / "artifacts"
CASE_TABLE = ARTIFACTS / "e6_table_budget_risk_interaction_case_level.csv"
AGGREGATE_TABLE = ARTIFACTS / "e6_table_budget_risk_interaction_aggregate.csv"
CONTRAST_TABLE = ARTIFACTS / "e6_table_interaction_contrasts.csv"
AGGREGATE_METRICS = (
    "objective", "normalized_objective", "fixed_cost", "inventory_cost",
    "reconfiguration_cost", "robust_recourse_cost", "normalized_robust_recourse",
    "RI", "RS", "canonical_total_adjustment", "budget_utilization", "budget_slack",
    "shortage_cost", "transportation_cost", "service_penalty", "total_shortage",
    "minimum_fill_rate", "average_fill_rate",
)


def load_complete_results(result_root: Path = RESULT_ROOT) -> dict[str, dict]:
    expected = {condition.run_id for condition in enumerate_conditions()}
    results = {}
    for path in sorted(result_root.glob("*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        run_id = result["run_id"]
        if run_id in results:
            raise ValueError(f"duplicate E6 result: {run_id}")
        results[run_id] = result
    if set(results) != expected:
        raise ValueError(
            f"incomplete E6 results: missing={sorted(expected - set(results))}, "
            f"extra={sorted(set(results) - expected)}"
        )
    return results


def case_rows(results: dict[str, dict]) -> list[dict]:
    rows = []
    for case in CASES:
        reference = results[f"E6-{case}-B100-G2"]
        for condition in (item for item in enumerate_conditions() if item.case == case):
            result = results[condition.run_id]
            row = dict(result)
            row["normalized_objective"] = result["objective"] / reference["objective"]
            row["normalized_robust_recourse"] = (
                result["robust_recourse_cost"] / reference["robust_recourse_cost"]
            )
            rows.append(row)
    return rows


def aggregate_rows(rows: list[dict]) -> list[dict]:
    output = []
    for beta_token, beta in BETA_BY_TOKEN.items():
        for gamma_token, gamma in GAMMA_BY_TOKEN.items():
            cell = [
                row for row in rows
                if row["beta_token"] == beta_token and row["Gamma_token"] == gamma_token
            ]
            summary = {
                "beta_token": beta_token,
                "beta": float(beta),
                "Gamma_token": gamma_token,
                "Gamma": gamma,
                "case_count": len(cell),
                "material_case_count": sum(row["material_reconfiguration"] for row in cell),
                "budget_binding_case_count": sum(row["budget_binding"] for row in cell),
            }
            for metric in AGGREGATE_METRICS:
                values = [float(row[metric]) for row in cell]
                summary[f"mean_{metric}"] = statistics.mean(values)
                summary[f"median_{metric}"] = statistics.median(values)
                summary[f"min_{metric}"] = min(values)
                summary[f"max_{metric}"] = max(values)
            output.append(summary)
    return output


def first_material_gamma(rows: dict[int, dict], tolerance: float) -> str:
    for gamma in GAMMA_BY_TOKEN.values():
        if float(rows[gamma]["RI"]) > tolerance:
            return str(gamma)
    return "none_through_4"


def interaction_contrast_for_case(
    case: str, rows: list[dict], materiality_tolerance: float, binding_tolerance: float
) -> dict:
    indexed = {(float(row["beta"]), int(row["Gamma"])): row for row in rows if row["case"] == case}
    deltas = {}
    for beta in (0.8, 1.0, 1.2):
        g0, g4 = indexed[(beta, 0)], indexed[(beta, 4)]
        for metric in ("RI", "objective", "robust_recourse_cost", "RS"):
            deltas[f"delta_Gamma_{metric}_B{int(beta * 100):03d}"] = float(g4[metric]) - float(g0[metric])
    did_ri = deltas["delta_Gamma_RI_B080"] - deltas["delta_Gamma_RI_B120"]
    did_objective = (
        deltas["delta_Gamma_objective_B080"] - deltas["delta_Gamma_objective_B120"]
    )
    did_recourse = (
        deltas["delta_Gamma_robust_recourse_cost_B080"]
        - deltas["delta_Gamma_robust_recourse_cost_B120"]
    )
    thresholds = {
        f"first_material_gamma_B{int(beta * 100):03d}": first_material_gamma(
            {gamma: indexed[(beta, gamma)] for gamma in (0, 2, 4)}, materiality_tolerance
        )
        for beta in (0.8, 1.0, 1.2)
    }
    b120_g0 = indexed[(1.2, 0)]
    b120_g4 = indexed[(1.2, 4)]
    binding_transition = (
        float(b120_g0["budget_slack"]) > binding_tolerance
        and abs(float(b120_g4["budget_slack"])) <= binding_tolerance
    )
    labels = []
    if did_ri > materiality_tolerance:
        labels.append("SCARCITY_AMPLIFIES_RISK_RESPONSE")
    elif did_ri < -materiality_tolerance:
        labels.append("SCARCITY_DAMPENS_RISK_RESPONSE")
    else:
        labels.append("RISK_RESPONSE_BUDGET_INSENSITIVE")
    if binding_transition:
        labels.append("BUDGET_BINDING_TRANSITION")
    if len(set(thresholds.values())) > 1:
        labels.append("EXTENSIVE_MARGIN_THRESHOLD_SHIFT")
    elif all(indexed[(beta, 0)]["material_reconfiguration"] for beta in (0.8, 1.0, 1.2)):
        labels.append("INTENSIVE_MARGIN_ONLY")
    return {
        "case": case,
        **deltas,
        "DID_RI_tight_vs_relaxed": did_ri,
        "DID_objective_tight_vs_relaxed": did_objective,
        "DID_recourse_tight_vs_relaxed": did_recourse,
        **thresholds,
        "B120_risk_consumes_financial_slack": binding_transition,
        "mechanism_classification": "|".join(labels),
    }


def contrast_rows(rows: list[dict], manifest: dict) -> list[dict]:
    return [
        interaction_contrast_for_case(
            case,
            rows,
            manifest["materiality_tolerance"],
            manifest["budget_binding_tolerance"],
        )
        for case in CASES
    ]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    manifest = load_manifest()
    results = load_complete_results()
    rows = case_rows(results)
    write_csv(CASE_TABLE, rows)
    write_csv(AGGREGATE_TABLE, aggregate_rows(rows))
    write_csv(CONTRAST_TABLE, contrast_rows(rows, manifest))
    print("wrote E6 case, aggregate, and interaction-contrast tables")


if __name__ == "__main__":
    main()
