"""Create E8 paper tables only from complete, identity-verified formal results."""
from __future__ import annotations

import csv
import importlib.util
import json
import statistics
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from robust_inventory_reconfiguration.e8_fulfillment_flexibility import (
    MODES,
    paired_reporting_rows,
)


def _load_runner():
    path = ROOT / "experiments/run_e8_fulfillment_flexibility_local.py"
    spec = importlib.util.spec_from_file_location("e8_runner_for_summary", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the frozen E8 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_case(case_id: str, runner: Any) -> tuple[list[dict[str, Any]], dict[str, float]]:
    config, _ = runner.validate_static_protocol()
    protocol = runner.case_protocol(case_id, config)
    summaries: dict[str, dict[str, Any]] = {}
    rows_by_mode: dict[str, list[dict[str, Any]]] = {}
    for mode in MODES:
        identity = runner.condition_identity(
            case_id, mode, config, protocol, pilot=False
        )
        target = runner.result_dir(case_id, mode, pilot=False)
        if not runner.verified_result(target, identity):
            raise RuntimeError(f"BLOCK_E8_INCOMPLETE_FORMAL_CASE:{case_id}:{mode}")
        summaries[mode] = runner.read_json(target / "summary.json")
        rows_by_mode[mode] = runner._read_scenario_rows(
            target / "scenario_results.jsonl.gz"
        )
    rows = paired_reporting_rows(
        rows_by_mode,
        summaries,
        float(config["immutable_protocol"]["mode_order_tolerance"]),
    )
    robust_costs = {
        mode: float(summaries[mode]["worst_economic_cost"]["value"])
        for mode in MODES
    }
    return [{"case": case_id, **row} for row in rows], robust_costs


def write_outputs(rows: list[dict[str, Any]], output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "fixed_inventory_fulfillment_comparison.json"
    json_path.write_text(
        json.dumps(rows, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    csv_path = output_root / "fixed_inventory_fulfillment_comparison.csv"
    columns = [
        "case",
        "evaluation_basis",
        "mode",
        "scenario_id",
        "recourse_cost",
        "transportation_cost",
        "shortage_penalty_cost",
        "service_violation_penalty_cost",
        "total_shortage",
        "demand_weighted_fill_rate",
        "worst_region_fill_rate",
        "worst_region_id",
        "service_violation_quantity",
        "actual_multi_source_region_product_count",
        "actual_multi_source_shipment_quantity",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)



def build_sensitivity_summary(
    case_costs: dict[str, dict[str, float]],
    paired_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Descriptive all-eight and seven-case sensitivity (no solver calls)."""
    cases = sorted(case_costs)
    if len(cases) != 8 or "210330" not in case_costs:
        raise RuntimeError("BLOCK_E8_SENSITIVITY_REQUIRES_ALL_EIGHT_CASES")
    bases = ("nominal_demand", "full_mode_worst_economic_cost")
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in paired_rows:
        key = (row["case"], row["evaluation_basis"], row["mode"])
        if key in indexed:
            raise RuntimeError("BLOCK_E8_DUPLICATE_PAIRED_ROW")
        indexed[key] = row
    expected = {
        (case, basis, mode)
        for case in cases for basis in bases for mode in MODES
    }
    if set(indexed) != expected:
        raise RuntimeError("BLOCK_E8_SENSITIVITY_INCOMPLETE_PAIRED_ROWS")
    for case in cases:
        costs = case_costs[case]
        if set(costs) != set(MODES):
            raise RuntimeError("BLOCK_E8_SENSITIVITY_MISSING_MODE_COST")
        if not all(costs[mode] >= 0.0 for mode in MODES):
            raise RuntimeError("BLOCK_E8_SENSITIVITY_NEGATIVE_COST")
        if costs["full"] > costs["k2"] + 1e-4 or costs["k2"] > costs["k1"] + 1e-4:
            raise RuntimeError("BLOCK_E8_SENSITIVITY_COST_ORDER")

    def cohort(subset: list[str]) -> dict[str, Any]:
        k1_full = [case_costs[c]["k1"] - case_costs[c]["full"] for c in subset]
        k2_full = [case_costs[c]["k2"] - case_costs[c]["full"] for c in subset]
        relative = [
            100.0 * (case_costs[c]["k1"] - case_costs[c]["full"]) / case_costs[c]["k1"]
            for c in subset if case_costs[c]["k1"] > 0.0
        ]
        if len(relative) != len(subset):
            raise RuntimeError("BLOCK_E8_SENSITIVITY_NONPOSITIVE_BASELINE")
        paired = {}
        for basis in bases:
            shortage = [
                float(indexed[(c, basis, "full")]["total_shortage"])
                - float(indexed[(c, basis, "k1")]["total_shortage"])
                for c in subset
            ]
            fill = [
                float(indexed[(c, basis, "full")]["demand_weighted_fill_rate"])
                - float(indexed[(c, basis, "k1")]["demand_weighted_fill_rate"])
                for c in subset
            ]
            paired[basis] = {
                "mean_full_minus_k1_total_shortage": statistics.mean(shortage),
                "mean_full_minus_k1_demand_weighted_fill_rate": statistics.mean(fill),
            }
        return {
            "case_count": len(subset),
            "cases": subset,
            "mean_k1_minus_full_robust_cost": statistics.mean(k1_full),
            "median_k1_minus_full_robust_cost": statistics.median(k1_full),
            "mean_k2_minus_full_robust_cost": statistics.mean(k2_full),
            "mean_k1_to_full_cost_reduction_percent": statistics.mean(relative),
            "k1_to_full_positive_saving_count_above_1e-4": sum(x > 1e-4 for x in k1_full),
            "k2_to_full_positive_saving_count_above_1e-4": sum(x > 1e-4 for x in k2_full),
            "paired_service_comparisons": paired,
        }

    return {
        "schema": "e8_robust_cost_and_service_sensitivity_v1",
        "scope": "descriptive fixed-inventory comparisons; no statistical significance asserted",
        "historical_certification_qualification": {
            "case": "210330",
            "e1_label": "CERTIFIED_PRB_EXACT",
            "e1_global_coupling_pass": False,
        },
        "cohorts": {
            "all_8_cases": cohort(cases),
            "exclude_210330_7_cases": cohort([c for c in cases if c != "210330"]),
        },
    }

def main() -> None:
    runner = _load_runner()
    rows: list[dict[str, Any]] = []
    case_costs: dict[str, dict[str, float]] = {}
    for case_id in runner.CASE_IDS:
        case_rows, robust_costs = collect_case(case_id, runner)
        rows.extend(case_rows)
        case_costs[case_id] = robust_costs
    if len(rows) != len(runner.CASE_IDS) * len(MODES) * 2:
        raise RuntimeError("BLOCK_E8_PAPER_TABLE_COMPLETENESS")
    output_root = Path(__file__).resolve().parent
    sensitivity = build_sensitivity_summary(case_costs, rows)
    write_outputs(rows, output_root)
    (output_root / "fixed_inventory_sensitivity_8_vs_7.json").write_text(
        json.dumps(sensitivity, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
