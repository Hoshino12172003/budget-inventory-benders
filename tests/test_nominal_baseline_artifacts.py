from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nominal_baseline_artifacts_are_complete_and_nonzero() -> None:
    summary = json.loads((ROOT / "artifacts" / "nominal_baseline_summary.json").read_text())
    for case in ("210202", "210628"):
        path = ROOT / "artifacts" / f"nominal_baseline_{case}.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 120
        assert len({(row["depot_id"], row["product_id"]) for row in rows}) == 120
        assert sum(float(row["x0"]) for row in rows) > 0
        assert summary["cases"][case]["positive_stock_product_count"] == 8


def test_candidate_rules_are_numerically_equivalent() -> None:
    summary = json.loads((ROOT / "artifacts" / "nominal_baseline_summary.json").read_text())
    for case in ("210202", "210628"):
        result = summary["cases"][case]
        assert abs(result["candidate_objective_difference"]) <= 1e-7
        assert result["candidate_maximum_x_difference"] <= 1e-7
        assert result["candidate_y_identical"] is True


def test_generated_baselines_are_feasible_and_structurally_stable() -> None:
    summary = json.loads((ROOT / "artifacts" / "nominal_baseline_summary.json").read_text())
    for result in summary["cases"].values():
        assert result["feasibility"]["capacity_compatible"] is True
        assert result["feasibility"]["ub_compatible"] is True
        assert result["degeneracy"]["baseline_structurally_stable"] is True
        assert result["degeneracy"]["tie_break_required"] is False
