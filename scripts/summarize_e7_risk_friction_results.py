from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "experiments/results/e7_risk_friction_interaction_v1"
ARTIFACTS = ROOT / "artifacts"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
GAMMAS = (0, 2, 4)
LAMBDAS = (0.0025, 0.05, 0.2)


def first_material_gamma(rows: list[dict], lambda_r: float) -> str:
    indexed = {row["Gamma"]: row for row in rows if row["lambda_R"] == lambda_r}
    return next(
        (str(gamma) for gamma in GAMMAS if indexed[gamma]["material_reconfiguration"]),
        "none_through_4",
    )


def interaction_contrast_for_case(case: str, rows: list[dict]) -> dict:
    indexed = {(row["Gamma"], row["lambda_R"]): row for row in rows if row["case"] == case}
    out = {"case": case}
    for token, value in (("L0025", 0.0025), ("L0500", 0.05), ("L2000", 0.2)):
        g0, g4 = indexed[(0, value)], indexed[(4, value)]
        for name, field in (("RI", "RI"), ("objective", "objective"), ("recourse", "robust_recourse_cost"), ("RS", "RS"), ("changed_pairs", "changed_pair_count")):
            out[f"delta_Gamma_{name}_{token}"] = g4[field] - g0[field]
        out[f"first_material_gamma_{token}"] = first_material_gamma(
            [row for row in rows if row["case"] == case], value
        )
    for name in ("RI", "objective", "recourse", "RS"):
        out[f"DID_{name}_low_vs_high_friction"] = (
            out[f"delta_Gamma_{name}_L0025"] - out[f"delta_Gamma_{name}_L2000"]
        )
    return out


def margin_summary(rows: list[dict]) -> dict:
    material = [row for row in rows if row["material_reconfiguration"]]
    return {
        "observation_count": len(rows),
        "material_count": len(material),
        "material_share": len(material) / len(rows) if rows else 0.0,
        "mean_RI_conditional_on_material": (
            statistics.mean(row["RI"] for row in material) if material else None
        ),
        "mean_adjustment_conditional_on_material": (
            statistics.mean(row["canonical_total_adjustment"] for row in material)
            if material else None
        ),
    }


def load_complete_results() -> list[dict]:
    results = [json.loads(path.read_text(encoding="utf-8")) for path in RESULT_ROOT.glob("*/result.json")]
    expected = {(case, gamma, value) for case in CASES for gamma in GAMMAS for value in LAMBDAS}
    actual = {(row["case"], row["Gamma"], row["lambda_R"]) for row in results}
    if len(results) != 72 or actual != expected:
        raise RuntimeError("E7 reporting requires the complete certified 72-result grid")
    if any(row["status"] != "OPTIMAL" or not row["exact_certification_pass"] for row in results):
        raise RuntimeError("E7 reporting requires exact certification")
    return results


def write_csv(name: str, rows: list[dict]) -> None:
    with (ARTIFACTS / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = load_complete_results()
    references = {case: next(row for row in rows if row["case"] == case and row["Gamma"] == 2 and row["lambda_R"] == 0.05) for case in CASES}
    for row in rows:
        row["normalized_objective"] = row["objective"] / references[row["case"]]["objective"]
        row["normalized_robust_recourse"] = row["robust_recourse_cost"] / references[row["case"]]["robust_recourse_cost"]
    aggregate = []
    for gamma in GAMMAS:
        for value in LAMBDAS:
            cell = [row for row in rows if row["Gamma"] == gamma and row["lambda_R"] == value]
            aggregate.append({
                "Gamma": gamma, "lambda_R": value, "case_count": len(cell),
                "mean_normalized_objective": statistics.mean(row["normalized_objective"] for row in cell),
                "mean_normalized_robust_recourse": statistics.mean(row["normalized_robust_recourse"] for row in cell),
                "mean_RI": statistics.mean(row["RI"] for row in cell),
                "mean_RS": statistics.mean(row["RS"] for row in cell),
                "mean_changed_pair_count": statistics.mean(row["changed_pair_count"] for row in cell),
                "mean_top_adjustment_share": statistics.mean(row["top_adjustment_share"] for row in cell),
                "material_case_count": sum(row["material_reconfiguration"] for row in cell),
                "mean_budget_utilization": statistics.mean(row["budget_utilization"] for row in cell),
            })
    contrasts = [interaction_contrast_for_case(case, rows) for case in CASES]
    composition = [{key: row[key] for key in ("run_id", "case", "Gamma", "lambda_R", "canonical_total_adjustment", "RI", "changed_pair_count", "top_adjustment_share", "active_depot_ids", "positive_inventory_depot_ids")} for row in rows]
    timing = [{"run_id": row["run_id"], "reused": row["reused"], **row["timing"]} for row in rows]
    write_csv("e7_table_risk_friction_case_level.csv", rows)
    write_csv("e7_table_risk_friction_aggregate.csv", aggregate)
    write_csv("e7_table_interaction_contrasts.csv", contrasts)
    write_csv("e7_table_adjustment_composition.csv", composition)
    write_csv("e7_runtime_breakdown.csv", timing)


if __name__ == "__main__":
    main()
