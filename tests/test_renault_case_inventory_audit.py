from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "table_renault_case_inventory.csv"


def load_audit_module():
    path = ROOT / "scripts" / "audit_renault_case_inventory.py"
    spec = importlib.util.spec_from_file_location("renault_case_inventory_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows() -> list[dict[str, str]]:
    with TABLE.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_direct_gamma2_size_matches_existing_e1_audit() -> None:
    assert load_audit_module().direct_size(15, 12, 8) == (122376, 18629)


def test_complete_case_inventory_and_classification() -> None:
    data = rows()
    assert len(data) == 71
    assert [row["case_id"] for row in data] == sorted({row["case_id"] for row in data})
    assert sum(row["compatibility_classification"] == "READY_WITH_EXISTING_PIPELINE" for row in data) == 2
    assert sum(row["compatibility_classification"] == "REQUIRES_NONSCIENTIFIC_PLUMBING_ONLY" for row in data) == 0
    assert sum(row["compatibility_classification"] == "REQUIRES_NEW_MODELING_ASSUMPTION" for row in data) == 69


def test_raw_integrity_and_formal_boundary() -> None:
    data = rows()
    assert all(row["raw_normalizer_consumable"] == "True" for row in data)
    assert all(row["x0_reconstructible"] == "True" for row in data)
    assert all(row["selected_8_products_present"] == "True" for row in data)
    assert all(int(row["nonzero_inventory_pairs"]) == 0 for row in data)
    assert {row["case_id"] for row in data if row["formal_pipeline_consumable"] == "True"} == {"210202", "210628"}
    assert all(
        row["post_processing_dimensions_status"] == "NOT_FROZEN"
        for row in data
        if row["formal_pipeline_consumable"] == "False"
    )


def test_recommendation_preserves_execution_gates() -> None:
    inventory = (ROOT / "docs" / "renault_case_inventory_audit.md").read_text(encoding="utf-8")
    recommendation = (ROOT / "docs" / "e1_real_data_redesign_recommendation.md").read_text(encoding="utf-8")
    assert "Optimization runs executed by this audit: 0" in inventory
    assert "Synthetic runs executed: 0" in inventory
    assert "E2-E7 authorization remains `false`" in inventory
    assert "Decision: Option C" in recommendation
    assert "creates no synthetic generator and authorizes no run" in recommendation
