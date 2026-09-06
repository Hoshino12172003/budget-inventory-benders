from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from gurobipy import GRB

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.nominal_baseline import (
    baseline_feasibility,
    build_nominal_model,
    solve_nominal_baseline,
)


ROOT = Path(__file__).resolve().parents[1]
OLD_B_REF = {"210202": 84614.30513135396, "210628": 50558.18771213084}
OBJECTIVE_FACE_TOLERANCE = 1e-7
STRUCTURAL_RANGE_TOLERANCE = 1e-3


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _degeneracy_audit(case: str, instance, optimum: float) -> tuple[list[dict[str, object]], dict[str, object]]:
    model, y, x, first_stage, recourse = build_nominal_model(instance)
    primary = first_stage + recourse
    model.optimize()
    baseline_y = [int(round(y[i].X)) for i in range(instance.num_depots)]
    rows: list[dict[str, object]] = []
    minimum_y_flip_gap = float("inf")
    for i, depot_id in enumerate(instance.depot_ids):
        trial = model.copy()
        trial.Params.OutputFlag = 0
        trial.addConstr(trial.getVarByName(f"y[{i}]") == 1 - baseline_y[i])
        trial.optimize()
        gap = trial.ObjVal - optimum if trial.Status == GRB.OPTIMAL else float("inf")
        minimum_y_flip_gap = min(minimum_y_flip_gap, gap)
        rows.append(
            {
                "case": case,
                "variable": "y",
                "depot_id": depot_id,
                "product_id": "",
                "baseline_value": baseline_y[i],
                "minimum": baseline_y[i],
                "maximum": baseline_y[i],
                "range_width": 0.0,
                "forced_flip_objective_gap": gap,
            }
        )

    model.addConstr(primary <= optimum + OBJECTIVE_FACE_TOLERANCE, name="optimal_face")
    max_x_width = 0.0
    material_x_ranges = 0
    for i, depot_id in enumerate(instance.depot_ids):
        for j, product_id in enumerate(instance.product_ids):
            model.setObjective(x[i, j], GRB.MINIMIZE)
            model.optimize()
            minimum = x[i, j].X
            model.setObjective(x[i, j], GRB.MAXIMIZE)
            model.optimize()
            maximum = x[i, j].X
            width = maximum - minimum
            max_x_width = max(max_x_width, width)
            material_x_ranges += width > STRUCTURAL_RANGE_TOLERANCE
            rows.append(
                {
                    "case": case,
                    "variable": "x",
                    "depot_id": depot_id,
                    "product_id": product_id,
                    "baseline_value": "",
                    "minimum": minimum,
                    "maximum": maximum,
                    "range_width": width,
                    "forced_flip_objective_gap": "",
                }
            )
    stable = minimum_y_flip_gap > OBJECTIVE_FACE_TOLERANCE and material_x_ranges == 0
    return rows, {
        "objective_face_tolerance": OBJECTIVE_FACE_TOLERANCE,
        "structural_range_tolerance": STRUCTURAL_RANGE_TOLERANCE,
        "minimum_y_flip_objective_gap": minimum_y_flip_gap,
        "maximum_x_range_width": max_x_width,
        "material_x_range_count": material_x_ranges,
        "baseline_structurally_stable": stable,
        "tie_break_required": not stable,
    }


def main() -> None:
    artifacts = ROOT / "artifacts"
    configs = ROOT / "configs"
    artifacts.mkdir(exist_ok=True)
    configs.mkdir(exist_ok=True)
    summary: dict[str, object] = {
        "baseline_definition": "nominal incumbent inventory configuration",
        "gamma": 0,
        "baseline_definition_noncircular": True,
        "productwise_benders_compatible": True,
        "lambda_r_calibrated": False,
        "robust_gamma_positive_experiment_run": False,
        "step_1_3_parameters_modified": False,
        "cases": {},
    }
    provenance: dict[str, object] = {
        "generator": "scripts/generate_nominal_baselines.py",
        "model": "src/robust_inventory_reconfiguration/nominal_baseline.py",
        "rule": "Candidate A: unconstrained-budget Gamma=0 nominal optimum",
        "reconfiguration_variables_present": False,
        "reconfiguration_cost_present": False,
        "lambda_r_present": False,
        "cases": {},
    }
    all_degeneracy_rows: list[dict[str, object]] = []

    for case, old_budget in OLD_B_REF.items():
        instance_path = ROOT / "data" / "formal_instances" / f"{case}.json"
        instance = load_instance(instance_path)
        candidate_a = solve_nominal_baseline(instance)
        candidate_b = solve_nominal_baseline(instance, old_budget)
        degeneracy_rows, degeneracy = _degeneracy_audit(case, instance, candidate_a.objective)
        all_degeneracy_rows.extend(degeneracy_rows)

        csv_rows: list[dict[str, object]] = []
        per_product = [0.0] * instance.num_products
        per_depot = [0.0] * instance.num_depots
        positive_pairs = 0
        for i, depot_id in enumerate(instance.depot_ids):
            load = sum(
                instance.product_volume[j] * candidate_a.x[i][j]
                for j in range(instance.num_products)
            )
            for j, product_id in enumerate(instance.product_ids):
                value = candidate_a.x[i][j]
                upper_bound = instance.inventory_upper_bound[i][j]
                per_product[j] += value
                per_depot[i] += value
                positive_pairs += value > 1e-8
                csv_rows.append(
                    {
                        "case": case,
                        "depot_id": depot_id,
                        "product_id": product_id,
                        "x0": value,
                        "y0": candidate_a.y[i],
                        "depot_total_x0": "",
                        "product_total_x0": "",
                        "capacity_load": load,
                        "capacity": instance.capacity[i],
                        "capacity_utilization": load / instance.capacity[i],
                        "inventory_upper_bound": upper_bound,
                        "ub_utilization": value / upper_bound if upper_bound else (0.0 if value == 0 else "inf"),
                    }
                )
        for row in csv_rows:
            i = instance.depot_ids.index(str(row["depot_id"]))
            j = instance.product_ids.index(str(row["product_id"]))
            row["depot_total_x0"] = per_depot[i]
            row["product_total_x0"] = per_product[j]
        _write_csv(
            artifacts / f"nominal_baseline_{case}.csv",
            list(csv_rows[0]),
            csv_rows,
        )

        feasibility = baseline_feasibility(instance, candidate_a)
        case_summary = {
            "old_b_ref": old_budget,
            "candidate_a": {
                "objective": candidate_a.objective,
                "first_stage_spending": candidate_a.first_stage_spending,
                "nominal_recourse": candidate_a.recourse_cost,
            },
            "candidate_b": {
                "objective": candidate_b.objective,
                "first_stage_spending": candidate_b.first_stage_spending,
                "nominal_recourse": candidate_b.recourse_cost,
            },
            "candidate_objective_difference": candidate_b.objective - candidate_a.objective,
            "candidate_maximum_x_difference": max(
                abs(candidate_a.x[i][j] - candidate_b.x[i][j])
                for i in range(instance.num_depots)
                for j in range(instance.num_products)
            ),
            "candidate_y_identical": candidate_a.y == candidate_b.y,
            "total_inventory": sum(per_product),
            "active_depot_count": sum(candidate_a.y),
            "positive_x0_pair_count": positive_pairs,
            "zero_x0_pair_count": instance.num_depots * instance.num_products - positive_pairs,
            "positive_stock_depot_count": sum(value > 1e-8 for value in per_depot),
            "positive_stock_product_count": sum(value > 1e-8 for value in per_product),
            "per_product_inventory": dict(zip(instance.product_ids, per_product)),
            "per_depot_inventory": dict(zip(instance.depot_ids, per_depot)),
            "y0": dict(zip(instance.depot_ids, candidate_a.y)),
            "feasibility": feasibility,
            "degeneracy": degeneracy,
        }
        summary["cases"][case] = case_summary
        config = {
            "case": case,
            "gamma": 0,
            "financial_budget": None,
            "baseline_rule": "unconstrained-budget nominal optimum",
            "instance": f"data/formal_instances/{case}.json",
            "artifact": f"artifacts/nominal_baseline_{case}.csv",
        }
        (configs / f"nominal_baseline_{case}.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )
        provenance["cases"][case] = {
            "instance_path": f"data/formal_instances/{case}.json",
            "instance_sha256": _sha256(instance_path),
            "legacy_instance_sha256": instance.provenance["legacy_instance_sha256"],
            "old_b_ref": old_budget,
            "old_b_ref_reproduced_first_stage_spending": candidate_a.first_stage_spending,
        }

    _write_csv(
        artifacts / "nominal_baseline_degeneracy_audit.csv",
        [
            "case",
            "variable",
            "depot_id",
            "product_id",
            "baseline_value",
            "minimum",
            "maximum",
            "range_width",
            "forced_flip_objective_gap",
        ],
        all_degeneracy_rows,
    )
    (artifacts / "nominal_baseline_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "nominal_baseline_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
