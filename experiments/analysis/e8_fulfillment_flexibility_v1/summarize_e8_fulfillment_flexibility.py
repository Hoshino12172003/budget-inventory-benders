"""Create E8 paper tables only from complete, identity-verified formal results."""
from __future__ import annotations

import csv
import importlib.util
import json
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


def collect_case(case_id: str, runner: Any) -> list[dict[str, Any]]:
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
    return [{"case": case_id, **row} for row in rows]


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


def main() -> None:
    runner = _load_runner()
    rows = [
        row
        for case_id in runner.CASE_IDS
        for row in collect_case(case_id, runner)
    ]
    if len(rows) != len(runner.CASE_IDS) * len(MODES) * 2:
        raise RuntimeError("BLOCK_E8_PAPER_TABLE_COMPLETENESS")
    write_outputs(rows, Path(__file__).resolve().parent)


if __name__ == "__main__":
    main()
