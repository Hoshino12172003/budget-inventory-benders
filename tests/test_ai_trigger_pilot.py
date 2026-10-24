from __future__ import annotations

import math

import pytest

from experiments.ai_trigger_pilot.run_ai_trigger_pilot import (
    CASES,
    CONTROL_FEATURES,
    FULL_FEATURES,
    PROHIBITED_INPUTS,
    add_state,
    build_dataset,
    evaluate_loco,
    load_unique_states,
    static_features,
    tune_gamma_threshold,
)


def test_unique_state_deduplication_and_label_consistency() -> None:
    rows, audit = load_unique_states()
    assert audit["source_row_count"] == 200
    assert audit["unique_state_count"] == 136
    assert audit["duplicates_removed"] == 64
    assert audit["duplicate_label_conflicts"] == 0
    assert {row["case"] for row in rows} == set(CASES)


def test_duplicate_label_conflict_fails_closed() -> None:
    states = {}
    common = {"case": "210202", "beta": 1.0, "gamma": 2, "lambda_r": 0.05}
    add_state(states, **common, label=True, source="E3", label_source="E3:RI>1e-6")
    with pytest.raises(RuntimeError, match="INCONSISTENT_DUPLICATE_LABEL"):
        add_state(states, **common, label=False, source="E4", label_source="E4:RI>1e-6")


def test_all_cases_have_finite_pre_solve_features() -> None:
    for case in CASES:
        features = static_features(case)
        assert set(features) == set(FULL_FEATURES) - set(CONTROL_FEATURES)
        assert all(math.isfinite(value) for value in features.values())
        assert 0.0 <= features["incumbent_capacity_utilization"] <= 1.0


def test_model_feature_whitelist_excludes_identifiers_and_outcomes() -> None:
    assert not (set(FULL_FEATURES) & PROHIBITED_INPUTS)
    assert "case" not in FULL_FEATURES
    assert "run_id" not in FULL_FEATURES
    assert "material_reconfiguration" not in FULL_FEATURES


def test_dataset_is_balanced_enough_for_loco() -> None:
    rows, audit = build_dataset()
    assert len(rows) == 136
    assert audit["positive_labels"] == 65
    assert audit["negative_labels"] == 71
    for case in CASES:
        labels = {row["material_reconfiguration"] for row in rows if row["case"] == case}
        assert labels == {False, True}


def test_gamma_threshold_is_selected_from_training_values_only() -> None:
    import numpy as np

    gamma = np.asarray([0.0, 1.0, 2.0, 4.0])
    labels = np.asarray([0, 0, 1, 1])
    assert tune_gamma_threshold(gamma, labels) == 2.0


def test_loco_outputs_every_case_and_method() -> None:
    rows, _ = build_dataset()
    cv_rows, confusion_rows, importance_rows, tree_rules = evaluate_loco(rows)
    assert len(cv_rows) == 8 * 8
    assert {row["held_out_case"] for row in cv_rows} == set(CASES)
    assert len(confusion_rows) == 8 * 8 + 8
    assert sum(row["scope"] == "held_out_case" for row in confusion_rows) == 8 * 8
    assert sum(row["scope"] == "pooled_loco" for row in confusion_rows) == 8
    assert importance_rows
    assert "held out 210202" in tree_rules
