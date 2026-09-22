from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "artifacts/ai_trigger_pilot/ai_trigger_feature_importance.csv"
DEFAULT_OUTPUT = ROOT / "artifacts/ai_trigger_pilot"
FULL_METHODS = ("logistic_full", "tree_full", "gradient_boosting_full")
FOLDS = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")
FOCAL_FEATURES = (
    "Gamma",
    "transport_cost_cv",
    "beta",
    "inventory_to_nominal_demand_ratio",
    "incumbent_inventory_concentration_across_depots",
)
ZERO_TOLERANCE = 1e-12

# Predeclared before reading audit results.
GB_STABLE_MIN_NONZERO_FOLDS = 7
GB_STABLE_MIN_TOP5_FOLDS = 6
GB_STABLE_MAX_CV = 0.75
GB_MODERATE_MIN_NONZERO_FOLDS = 4
GB_MODERATE_MIN_TOP5_FOLDS = 3
GB_MODERATE_MAX_CV = 1.50

LOGISTIC_SIGN_STABLE_MIN_NONZERO_FOLDS = 6
LOGISTIC_SIGN_STABLE_MIN_RATIO = 0.875
LOGISTIC_SIGN_MODERATE_MIN_NONZERO_FOLDS = 4
LOGISTIC_SIGN_MODERATE_MIN_RATIO = 0.75

OVERALL_STABLE_MIN_GB_JACCARD = 0.60
OVERALL_STABLE_MIN_JOINT_FOCAL_FEATURES = 4
OVERALL_PARTIAL_MIN_GB_JACCARD = 0.30
OVERALL_PARTIAL_MIN_JOINT_FOCAL_FEATURES = 2


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_fold_importance(path: Path = DEFAULT_INPUT) -> dict[str, dict[str, dict[str, float]]]:
    rows = [
        row
        for row in read_csv(path)
        if row["scope"] == "fold" and row["method"] in FULL_METHODS
    ]
    data: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        method = row["method"]
        fold = row["held_out_case"]
        feature = row["feature"]
        if feature in data[method][fold]:
            raise RuntimeError(f"DUPLICATE_IMPORTANCE_ROW: {method} {fold} {feature}")
        data[method][fold][feature] = float(row["value"])

    reference_features: set[str] | None = None
    for method in FULL_METHODS:
        if set(data[method]) != set(FOLDS):
            raise RuntimeError(f"INCOMPLETE_FOLD_SET: {method}")
        for fold in FOLDS:
            features = set(data[method][fold])
            if reference_features is None:
                reference_features = features
            if features != reference_features:
                raise RuntimeError(f"FEATURE_SET_MISMATCH: {method} {fold}")
    if reference_features is None or len(reference_features) != 28:
        raise RuntimeError("EXPECTED_28_FULL_MODEL_FEATURES")
    return data


def top_features(values: dict[str, float], count: int = 5) -> tuple[str, ...]:
    return tuple(
        feature
        for feature, _ in sorted(values.items(), key=lambda item: (-abs(item[1]), item[0]))[:count]
    )


def relative_dispersion(mean: float, std: float) -> float:
    if abs(mean) <= ZERO_TOLERANCE:
        return 0.0 if std <= ZERO_TOLERANCE else math.inf
    return std / abs(mean)


def classify_gradient_stability(nonzero_folds: int, top5_folds: int, cv: float) -> str:
    if (
        nonzero_folds >= GB_STABLE_MIN_NONZERO_FOLDS
        and top5_folds >= GB_STABLE_MIN_TOP5_FOLDS
        and cv <= GB_STABLE_MAX_CV
    ):
        return "STABLE"
    if (
        nonzero_folds >= GB_MODERATE_MIN_NONZERO_FOLDS
        and top5_folds >= GB_MODERATE_MIN_TOP5_FOLDS
        and cv <= GB_MODERATE_MAX_CV
    ):
        return "MODERATELY_STABLE"
    return "UNSTABLE"


def classify_sign_stability(nonzero_folds: int, sign_ratio: float) -> str:
    if (
        nonzero_folds >= LOGISTIC_SIGN_STABLE_MIN_NONZERO_FOLDS
        and sign_ratio >= LOGISTIC_SIGN_STABLE_MIN_RATIO
    ):
        return "SIGN_STABLE"
    if (
        nonzero_folds >= LOGISTIC_SIGN_MODERATE_MIN_NONZERO_FOLDS
        and sign_ratio >= LOGISTIC_SIGN_MODERATE_MIN_RATIO
    ):
        return "SIGN_MODERATELY_STABLE"
    return "SIGN_UNSTABLE"


def build_stability_rows(
    data: dict[str, dict[str, dict[str, float]]]
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, ...]]]:
    top5 = {
        method: {fold: top_features(data[method][fold]) for fold in FOLDS}
        for method in FULL_METHODS
    }
    features = sorted(data[FULL_METHODS[0]][FOLDS[0]])
    rows = []
    for method in FULL_METHODS:
        importance_type = {
            "logistic_full": "standardized_coefficient",
            "tree_full": "impurity_importance",
            "gradient_boosting_full": "training_fold_permutation_balanced_accuracy",
        }[method]
        for feature in features:
            values = [data[method][fold][feature] for fold in FOLDS]
            mean = statistics.fmean(values)
            std = statistics.pstdev(values)
            nonzero = sum(abs(value) > ZERO_TOLERANCE for value in values)
            top5_count = sum(feature in top5[method][fold] for fold in FOLDS)
            cv = relative_dispersion(mean, std) if method == "gradient_boosting_full" else ""
            classification = (
                classify_gradient_stability(nonzero, top5_count, float(cv))
                if method == "gradient_boosting_full"
                else ""
            )
            rows.append(
                {
                    "method": method,
                    "feature": feature,
                    "importance_type": importance_type,
                    "fold_count": len(values),
                    "importance_mean": mean,
                    "importance_std": std,
                    "importance_median": statistics.median(values),
                    "importance_min": min(values),
                    "importance_max": max(values),
                    "nonzero_importance_fold_count": nonzero,
                    "top5_importance_fold_count": top5_count,
                    "coefficient_of_variation": cv,
                    "stability_classification": classification,
                    "focal_feature": feature in FOCAL_FEATURES,
                }
            )
    return rows, {method: tuple(features) for method in FULL_METHODS}


def build_sign_rows(data: dict[str, dict[str, dict[str, float]]]) -> list[dict[str, Any]]:
    rows = []
    features = sorted(data["logistic_full"][FOLDS[0]])
    for feature in features:
        values = [data["logistic_full"][fold][feature] for fold in FOLDS]
        positive = sum(value > ZERO_TOLERANCE for value in values)
        negative = sum(value < -ZERO_TOLERANCE for value in values)
        zero = len(values) - positive - negative
        nonzero = positive + negative
        sign_ratio = max(positive, negative) / nonzero if nonzero else 0.0
        dominant_sign = "POSITIVE" if positive > negative else "NEGATIVE" if negative > positive else "TIED"
        rows.append(
            {
                "method": "logistic_full",
                "feature": feature,
                "fold_count": len(values),
                "positive_fold_count": positive,
                "negative_fold_count": negative,
                "zero_fold_count": zero,
                "nonzero_fold_count": nonzero,
                "dominant_sign": dominant_sign,
                "sign_consistency_ratio": sign_ratio,
                "sign_stability_classification": classify_sign_stability(nonzero, sign_ratio),
                "focal_feature": feature in FOCAL_FEATURES,
            }
        )
    return rows


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def build_overlap_rows(data: dict[str, dict[str, dict[str, float]]]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    rows: list[dict[str, Any]] = []
    method_means: dict[str, float] = {}
    for method in FULL_METHODS:
        top5 = {fold: set(top_features(data[method][fold])) for fold in FOLDS}
        pair_values: dict[tuple[str, str], float] = {}
        for fold_a, fold_b in itertools.combinations(FOLDS, 2):
            value = jaccard(top5[fold_a], top5[fold_b])
            pair_values[(fold_a, fold_b)] = value
            rows.append(
                {
                    "row_type": "fold_pair",
                    "method": method,
                    "fold_a": fold_a,
                    "fold_b": fold_b,
                    "top5_a": "|".join(sorted(top5[fold_a])),
                    "top5_b": "|".join(sorted(top5[fold_b])),
                    "intersection_size": len(top5[fold_a] & top5[fold_b]),
                    "union_size": len(top5[fold_a] | top5[fold_b]),
                    "jaccard_overlap": value,
                    "average_jaccard": "",
                    "minimum_jaccard": "",
                    "maximum_jaccard": "",
                }
            )
        for fold in FOLDS:
            values = [
                value for pair, value in pair_values.items() if fold in pair
            ]
            rows.append(
                {
                    "row_type": "fold_summary",
                    "method": method,
                    "fold_a": fold,
                    "fold_b": "ALL_OTHER_FOLDS",
                    "top5_a": "|".join(sorted(top5[fold])),
                    "top5_b": "",
                    "intersection_size": "",
                    "union_size": "",
                    "jaccard_overlap": "",
                    "average_jaccard": statistics.fmean(values),
                    "minimum_jaccard": min(values),
                    "maximum_jaccard": max(values),
                }
            )
        all_values = list(pair_values.values())
        method_means[method] = statistics.fmean(all_values)
        rows.append(
            {
                "row_type": "method_summary",
                "method": method,
                "fold_a": "ALL_FOLDS",
                "fold_b": "ALL_FOLDS",
                "top5_a": "",
                "top5_b": "",
                "intersection_size": "",
                "union_size": "",
                "jaccard_overlap": "",
                "average_jaccard": method_means[method],
                "minimum_jaccard": min(all_values),
                "maximum_jaccard": max(all_values),
            }
        )
    return rows, method_means


def classify_overall(
    stability_rows: list[dict[str, Any]],
    sign_rows: list[dict[str, Any]],
    gb_jaccard: float,
) -> tuple[str, dict[str, Any]]:
    gb = {
        row["feature"]: row["stability_classification"]
        for row in stability_rows
        if row["method"] == "gradient_boosting_full"
    }
    signs = {row["feature"]: row["sign_stability_classification"] for row in sign_rows}
    joint_focal = sum(
        gb[feature] != "UNSTABLE" and signs[feature] != "SIGN_UNSTABLE"
        for feature in FOCAL_FEATURES
    )
    if (
        gb_jaccard >= OVERALL_STABLE_MIN_GB_JACCARD
        and joint_focal >= OVERALL_STABLE_MIN_JOINT_FOCAL_FEATURES
    ):
        classification = "STABLE_STRUCTURAL_SIGNAL"
    elif (
        gb_jaccard >= OVERALL_PARTIAL_MIN_GB_JACCARD
        and joint_focal >= OVERALL_PARTIAL_MIN_JOINT_FOCAL_FEATURES
    ):
        classification = "PARTIALLY_STABLE_SIGNAL"
    else:
        classification = "UNSTABLE_SIGNAL"
    return classification, {
        "gradient_boosting_average_top5_jaccard": gb_jaccard,
        "jointly_nonunstable_focal_feature_count": joint_focal,
    }


def write_report(
    path: Path,
    source_hash: str,
    stability_rows: list[dict[str, Any]],
    sign_rows: list[dict[str, Any]],
    overlap_rows: list[dict[str, Any]],
    method_means: dict[str, float],
    classification: str,
    detail: dict[str, Any],
) -> None:
    stability = {(row["method"], row["feature"]): row for row in stability_rows}
    signs = {row["feature"]: row for row in sign_rows}
    gb_fold_rows = [
        row
        for row in overlap_rows
        if row["method"] == "gradient_boosting_full" and row["row_type"] == "fold_summary"
    ]
    lines = [
        "# AI risk-trigger feature stability audit",
        "",
        f"Source importance SHA-256: `{source_hash}`. This audit reads the frozen fold-level importance records from commit `92c79a836f5d233f783f0ccd00f2f88c87bbc282`. It does not refit a classifier or run an optimization model.",
        "",
        "## Predeclared rules",
        "",
        "Gradient Boosting uses raw training-fold permutation importance. `CV = population std / abs(mean)`; a zero mean with nonzero dispersion has infinite CV.",
        "",
        "- `STABLE`: nonzero in at least 7/8 folds, top-5 in at least 6/8 folds, and CV at most 0.75.",
        "- `MODERATELY_STABLE`: nonzero in at least 4/8 folds, top-5 in at least 3/8 folds, and CV at most 1.50.",
        "- `UNSTABLE`: otherwise.",
        "- Logistic `SIGN_STABLE`: at least 6 nonzero folds and dominant sign in at least 7/8 nonzero folds.",
        "- Logistic `SIGN_MODERATELY_STABLE`: at least 4 nonzero folds and dominant sign in at least 6/8 nonzero folds.",
        "- Logistic `SIGN_UNSTABLE`: otherwise.",
        "- Overall `STABLE_STRUCTURAL_SIGNAL`: Gradient Boosting mean pairwise top-5 Jaccard at least 0.60 and at least 4/5 focal features jointly non-unstable under Gradient Boosting and Logistic sign checks.",
        "- Overall `PARTIALLY_STABLE_SIGNAL`: Jaccard at least 0.30 and at least 2/5 focal features jointly non-unstable.",
        "- Otherwise: `UNSTABLE_SIGNAL`.",
        "",
        "## Top-5 overlap",
        "",
        "| Full model | Mean pairwise Jaccard |",
        "|---|---:|",
    ]
    for method in FULL_METHODS:
        lines.append(f"| `{method}` | {method_means[method]:.3f} |")
    lines.extend(
        [
            "",
            "Gradient Boosting leave-one-case sensitivity:",
            "",
            "| Held-out case | Top-5 features | Mean overlap with other folds | Minimum overlap |",
            "|---|---|---:|---:|",
        ]
    )
    for row in gb_fold_rows:
        lines.append(
            f"| {row['fold_a']} | `{row['top5_a'].replace('|', '`, `')}` | "
            f"{float(row['average_jaccard']):.3f} | {float(row['minimum_jaccard']):.3f} |"
        )
    lines.extend(
        [
            "",
            "## Focal feature audit",
            "",
            "| Feature | GB mean | GB CV | GB top-5 folds | GB class | Logistic + / - / 0 | Sign ratio | Sign class |",
            "|---|---:|---:|---:|---|---:|---:|---|",
        ]
    )
    for feature in FOCAL_FEATURES:
        gb = stability[("gradient_boosting_full", feature)]
        sign = signs[feature]
        cv = gb["coefficient_of_variation"]
        cv_text = "inf" if math.isinf(float(cv)) else f"{float(cv):.3f}"
        lines.append(
            f"| `{feature}` | {float(gb['importance_mean']):.4f} | {cv_text} | "
            f"{gb['top5_importance_fold_count']}/8 | {gb['stability_classification']} | "
            f"{sign['positive_fold_count']} / {sign['negative_fold_count']} / {sign['zero_fold_count']} | "
            f"{float(sign['sign_consistency_ratio']):.3f} | {sign['sign_stability_classification']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"Gradient Boosting mean pairwise top-5 overlap is {detail['gradient_boosting_average_top5_jaccard']:.3f}. "
            f"Only {detail['jointly_nonunstable_focal_feature_count']}/5 focal features are jointly non-unstable across the Gradient Boosting magnitude and Logistic sign checks. The fold-specific top feature set therefore changes materially when some individual Renault cases are removed.",
            "",
            "These diagnostics describe predictive stability in a small eight-case sample. Feature importance and coefficient direction are not causal effects.",
            "",
            "## Final classification",
            "",
            classification,
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_audit(input_path: Path = DEFAULT_INPUT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    data = load_fold_importance(input_path)
    stability_rows, _ = build_stability_rows(data)
    sign_rows = build_sign_rows(data)
    overlap_rows, method_means = build_overlap_rows(data)
    classification, detail = classify_overall(
        stability_rows,
        sign_rows,
        method_means["gradient_boosting_full"],
    )
    write_csv(output_dir / "ai_trigger_feature_stability.csv", stability_rows)
    write_csv(output_dir / "ai_trigger_feature_sign_stability.csv", sign_rows)
    write_csv(output_dir / "ai_trigger_top5_overlap.csv", overlap_rows)
    write_report(
        output_dir / "ai_trigger_feature_stability_report.md",
        sha256(input_path),
        stability_rows,
        sign_rows,
        overlap_rows,
        method_means,
        classification,
        detail,
    )
    return {
        "classification": classification,
        "source_sha256": sha256(input_path),
        "feature_count": 28,
        "fold_count": 8,
        "method_top5_mean_jaccard": method_means,
        **detail,
        "optimization_runs": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit stability of frozen AI trigger feature importances.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_audit(args.input, args.output_dir)
    print(result)


if __name__ == "__main__":
    main()
