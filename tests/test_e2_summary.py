from __future__ import annotations

import pytest

from scripts.summarize_e2_results import baseline_consistent, is_material


def result(**overrides):
    value = {
        "objective_eval": 100.0,
        "RI": 0.0,
        "RS": 0.0,
        "changed_pair_count": 0,
        "active_depots": 2,
        "opened_depots": [],
        "closed_depots": [],
    }
    value.update(overrides)
    return value


def test_material_rule_is_predeclared_at_one_e_minus_six() -> None:
    assert not is_material(result(RI=1e-6))
    assert is_material(result(RI=1.000001e-6))
    assert is_material(result(changed_pair_count=1))


def test_baseline_consistency_uses_stored_material_indicators() -> None:
    existing = result()
    assert baseline_consistent(existing, result(objective_eval=100.00009))
    assert not baseline_consistent(existing, result(objective_eval=100.00011))
    assert not baseline_consistent(existing, result(opened_depots=["D1"]))
