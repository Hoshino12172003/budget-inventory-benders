from __future__ import annotations

from experiments.ai_trigger_pilot.audit_feature_stability import (
    FOLDS,
    FULL_METHODS,
    build_overlap_rows,
    build_sign_rows,
    build_stability_rows,
    classify_gradient_stability,
    classify_overall,
    classify_sign_stability,
    jaccard,
    load_fold_importance,
)


def test_predeclared_gradient_stability_boundaries() -> None:
    assert classify_gradient_stability(7, 6, 0.75) == "STABLE"
    assert classify_gradient_stability(4, 3, 1.50) == "MODERATELY_STABLE"
    assert classify_gradient_stability(8, 2, 0.10) == "UNSTABLE"
    assert classify_gradient_stability(8, 8, 1.51) == "UNSTABLE"


def test_predeclared_logistic_sign_boundaries() -> None:
    assert classify_sign_stability(8, 0.875) == "SIGN_STABLE"
    assert classify_sign_stability(8, 0.75) == "SIGN_MODERATELY_STABLE"
    assert classify_sign_stability(8, 0.625) == "SIGN_UNSTABLE"


def test_jaccard() -> None:
    assert jaccard({"a", "b", "c"}, {"b", "c", "d"}) == 0.5
    assert jaccard(set(), set()) == 1.0


def test_frozen_importance_input_is_complete() -> None:
    data = load_fold_importance()
    assert set(data) == set(FULL_METHODS)
    for method in FULL_METHODS:
        assert set(data[method]) == set(FOLDS)
        assert all(len(data[method][fold]) == 28 for fold in FOLDS)


def test_outputs_cover_all_features_and_folds() -> None:
    data = load_fold_importance()
    stability, _ = build_stability_rows(data)
    signs = build_sign_rows(data)
    overlap, method_means = build_overlap_rows(data)
    assert len(stability) == 3 * 28
    assert len(signs) == 28
    assert len(overlap) == 3 * (28 + 8 + 1)
    assert set(method_means) == set(FULL_METHODS)
    assert all(0.0 <= value <= 1.0 for value in method_means.values())


def test_overall_classification_has_only_frozen_outcomes() -> None:
    data = load_fold_importance()
    stability, _ = build_stability_rows(data)
    signs = build_sign_rows(data)
    _, method_means = build_overlap_rows(data)
    classification, _ = classify_overall(
        stability,
        signs,
        method_means["gradient_boosting_full"],
    )
    assert classification in {
        "STABLE_STRUCTURAL_SIGNAL",
        "PARTIALLY_STABLE_SIGNAL",
        "UNSTABLE_SIGNAL",
    }
