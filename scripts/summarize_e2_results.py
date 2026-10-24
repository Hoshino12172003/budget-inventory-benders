from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "experiments/results/e2_existing_nominal_robust_v1"
CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
POLICIES = ("EXISTING", "NOMINAL", "ROBUST")
MATERIAL_TOLERANCE = 1e-6
BASELINE_OBJECTIVE_TOLERANCE = 1e-4


def load_results(result_root: Path = RESULT_ROOT) -> dict[str, dict[str, dict]]:
    by_case: dict[str, dict[str, dict]] = {}
    seen: set[str] = set()
    for path in sorted(result_root.glob("*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        run_id = result["run_id"]
        if run_id in seen:
            raise ValueError(f"duplicate E2 run ID: {run_id}")
        seen.add(run_id)
        by_case.setdefault(result["case"], {})[result["policy"]] = result

    expected = {f"E2-{case}-{policy}" for case in CASES for policy in POLICIES}
    if seen != expected:
        raise ValueError(f"E2 run identity mismatch: missing={sorted(expected - seen)}, extra={sorted(seen - expected)}")
    for case in CASES:
        for policy in POLICIES:
            result = by_case[case][policy]
            if result["status"] != "OPTIMAL" or result["case"] != case or result["policy"] != policy:
                raise ValueError(f"invalid E2 result: E2-{case}-{policy}")
    return by_case


def is_material(result: dict) -> bool:
    return (
        result["RI"] > MATERIAL_TOLERANCE
        or result["changed_pair_count"] > 0
        or bool(result["opened_depots"])
        or bool(result["closed_depots"])
    )


def baseline_consistent(existing: dict, nominal: dict) -> bool:
    return (
        abs(existing["objective_eval"] - nominal["objective_eval"]) <= BASELINE_OBJECTIVE_TOLERANCE
        and nominal["RI"] <= MATERIAL_TOLERANCE
        and nominal["RS"] <= MATERIAL_TOLERANCE
        and nominal["changed_pair_count"] == 0
        and nominal["active_depots"] == existing["active_depots"]
        and not nominal["opened_depots"]
        and not nominal["closed_depots"]
    )


def signed_change(robust: dict, existing: dict, key: str) -> float:
    return robust[key] - existing[key]


def contrast_rows(by_case: dict[str, dict[str, dict]]) -> list[dict]:
    rows = []
    for case in CASES:
        existing = by_case[case]["EXISTING"]
        nominal = by_case[case]["NOMINAL"]
        robust = by_case[case]["ROBUST"]
        improvement = existing["objective_eval"] - robust["objective_eval"]
        existing_transport = (
            existing["robust_recourse_cost"]
            - existing["worst_recourse_shortage_cost"]
            - existing["worst_recourse_service_penalty_cost"]
        )
        robust_transport = (
            robust["robust_recourse_cost"]
            - robust["worst_recourse_shortage_cost"]
            - robust["worst_recourse_service_penalty_cost"]
        )
        material = is_material(robust)
        rows.append({
            "case": case,
            "existing_objective": existing["objective_eval"],
            "nominal_objective": nominal["objective_eval"],
            "robust_objective": robust["objective_eval"],
            "existing_nominal_abs_objective_diff": abs(existing["objective_eval"] - nominal["objective_eval"]),
            "existing_nominal_relative_objective_diff": abs(existing["objective_eval"] - nominal["objective_eval"]) / abs(existing["objective_eval"]),
            "baseline_consistency": "BASELINE_CONSISTENCY_PASS" if baseline_consistent(existing, nominal) else "BASELINE_CONSISTENCY_FAIL",
            "robust_vs_existing_abs_improvement": improvement,
            "robust_vs_existing_pct_improvement": 100.0 * improvement / existing["objective_eval"],
            "robust_vs_nominal_abs_improvement": nominal["objective_eval"] - robust["objective_eval"],
            "fixed_cost_change": signed_change(robust, existing, "fixed_cost"),
            "inventory_cost_change": signed_change(robust, existing, "inventory_cost"),
            "reconfiguration_cost": robust["reconfiguration_cost"],
            "first_stage_spending_change": signed_change(robust, existing, "budget_used"),
            "robust_recourse_change": signed_change(robust, existing, "robust_recourse_cost"),
            "implied_transport_cost_change": robust_transport - existing_transport,
            "shortage_cost_change": signed_change(robust, existing, "worst_recourse_shortage_cost"),
            "service_penalty_change": signed_change(robust, existing, "worst_recourse_service_penalty_cost"),
            "total_shortage_change": signed_change(robust, existing, "worst_recourse_total_shortage"),
            "min_fill_rate_change": signed_change(robust, existing, "minimum_fill_rate"),
            "avg_fill_rate_change": signed_change(robust, existing, "average_fill_rate"),
            "existing_budget_used": existing["budget_used"],
            "robust_budget_used": robust["budget_used"],
            "robust_budget_utilization": robust["budget_utilization"],
            "RI": robust["RI"],
            "RS": robust["RS"],
            "total_a_plus": robust["total_a_plus"],
            "total_a_minus": robust["total_a_minus"],
            "changed_pair_count": robust["changed_pair_count"],
            "opened_depots": "|".join(robust["opened_depots"]),
            "closed_depots": "|".join(robust["closed_depots"]),
            "existing_active_depots": existing["active_depots"],
            "robust_active_depots": robust["active_depots"],
            "active_depot_change": robust["active_depots"] - existing["active_depots"],
            "classification": "MATERIAL_ROBUST_RECONFIGURATION" if material else "NO_MATERIAL_RECONFIGURATION",
        })
    return rows


def classification_rows(contrasts: list[dict]) -> list[dict]:
    rows = []
    for row in contrasts:
        material = row["classification"] == "MATERIAL_ROBUST_RECONFIGURATION"
        rows.append({
            "case": row["case"],
            "classification": row["classification"],
            "material_reconfiguration": str(material).lower(),
            "main_reason": (
                f"RI={row['RI']:.12g}, changed_pair_count={row['changed_pair_count']}"
                if material
                else f"RI<=1e-6 and changed_pair_count={row['changed_pair_count']}"
            ),
            "objective_improved": str(row["robust_vs_existing_abs_improvement"] > MATERIAL_TOLERANCE).lower(),
            "service_improved": str(row["avg_fill_rate_change"] > MATERIAL_TOLERANCE).lower(),
            "shortage_improved": str(row["total_shortage_change"] < -MATERIAL_TOLERANCE).lower(),
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    contrasts = contrast_rows(load_results())
    write_csv(ROOT / "artifacts/e2_policy_contrast_summary.csv", contrasts)
    write_csv(ROOT / "artifacts/e2_case_classification_summary.csv", classification_rows(contrasts))
    print("E2_SCIENTIFIC_INTERPRETATION_AUDIT_PASS: 24/24 OPTIMAL results summarized")


if __name__ == "__main__":
    main()
