from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.utils.class_weight import compute_sample_weight


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "artifacts" / "ai_trigger_pilot"
CASES = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")
MATERIALITY_TOLERANCE = 1e-6
RANDOM_STATE = 20260920

CONTROL_FEATURES = ["Gamma", "beta", "lambda_R"]
STRUCTURAL_FEATURES = [
    "total_nominal_demand",
    "total_deviation",
    "deviation_to_nominal_ratio",
    "nominal_demand_mean",
    "nominal_demand_std",
    "nominal_demand_cv",
    "maximum_nominal_demand_to_mean_ratio",
    "demand_density",
    "regional_demand_concentration",
    "product_demand_concentration",
    "total_incumbent_inventory",
    "inventory_to_nominal_demand_ratio",
    "incumbent_inventory_concentration_across_depots",
    "incumbent_inventory_concentration_across_products",
    "total_capacity",
    "incumbent_capacity_utilization",
    "capacity_slack_ratio",
    "mean_transport_cost",
    "transport_cost_cv",
    "mean_inventory_cost",
    "inventory_cost_cv",
    "mean_shortage_penalty",
    "shortage_penalty_cv",
    "mean_service_penalty",
    "fixed_cost_cv",
]
FULL_FEATURES = CONTROL_FEATURES + STRUCTURAL_FEATURES
PROHIBITED_INPUTS = {
    "objective",
    "RI",
    "total_adjustment",
    "changed_pair_count",
    "runtime",
    "iterations",
    "cuts_added",
    "shortage_result",
    "fill_rate_result",
    "case",
    "run_id",
    "state_key",
}

FEATURE_DEFINITIONS = {
    "Gamma": ("Demand-risk budget for the decision state.", "Frozen E2/E3/E4/E5/E7 protocol"),
    "beta": ("Financial budget multiplier B/B_ref for the decision state.", "Frozen E2/E3/E4/E5/E7 protocol"),
    "lambda_R": ("Symmetric inventory-reconfiguration friction multiplier.", "Frozen E2/E3/E4/E5/E7 protocol"),
    "total_nominal_demand": ("sum_(r,j) dbar[r,j]", "formal instance base_demand"),
    "total_deviation": ("sum_(r,j) dhat[r,j]", "formal instance demand_deviation"),
    "deviation_to_nominal_ratio": ("total_deviation / total_nominal_demand", "formal instance"),
    "nominal_demand_mean": ("Population mean over the R by J nominal-demand matrix.", "formal instance base_demand"),
    "nominal_demand_std": ("Population standard deviation over the R by J nominal-demand matrix.", "formal instance base_demand"),
    "nominal_demand_cv": ("nominal_demand_std / nominal_demand_mean", "formal instance base_demand"),
    "maximum_nominal_demand_to_mean_ratio": ("max(dbar) / mean(dbar)", "formal instance base_demand"),
    "demand_density": ("count(dbar[r,j] > 0) / (R*J)", "formal instance base_demand"),
    "regional_demand_concentration": ("HHI of regional shares: sum_r (sum_j dbar[r,j] / total)^2", "formal instance base_demand"),
    "product_demand_concentration": ("HHI of product shares: sum_j (sum_r dbar[r,j] / total)^2", "formal instance base_demand"),
    "total_incumbent_inventory": ("sum_(i,j) x0[i,j] in inventory units", "frozen x0 artifact"),
    "inventory_to_nominal_demand_ratio": ("total_incumbent_inventory / total_nominal_demand", "frozen x0 plus formal instance"),
    "incumbent_inventory_concentration_across_depots": ("HHI of depot shares of x0.", "frozen x0 artifact"),
    "incumbent_inventory_concentration_across_products": ("HHI of product shares of x0.", "frozen x0 artifact"),
    "total_capacity": ("sum_i C[i] in the model's volume units.", "formal instance capacity"),
    "incumbent_capacity_utilization": ("sum_(i,j) volume[j]*x0[i,j] / sum_i C[i]", "frozen x0 and formal instance product_volume/capacity"),
    "capacity_slack_ratio": ("1 - incumbent_capacity_utilization", "frozen x0 and formal instance"),
    "mean_transport_cost": ("Population mean over the full transport-cost tensor.", "formal instance transport_cost"),
    "transport_cost_cv": ("Population standard deviation / mean of transport_cost.", "formal instance transport_cost"),
    "mean_inventory_cost": ("Population mean over inventory_cost.", "formal instance inventory_cost"),
    "inventory_cost_cv": ("Population standard deviation / mean of inventory_cost.", "formal instance inventory_cost"),
    "mean_shortage_penalty": ("Population mean over shortage_penalty.", "formal instance shortage_penalty"),
    "shortage_penalty_cv": ("Population standard deviation / mean of shortage_penalty.", "formal instance shortage_penalty"),
    "mean_service_penalty": ("Population mean over service_penalty.", "formal instance service_penalty"),
    "fixed_cost_cv": ("Population standard deviation / mean of fixed planning-period depot cost.", "formal instance fixed_depot_cost"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered not in {"true", "false"}:
        raise ValueError(f"INVALID_BOOLEAN: {value!r}")
    return lowered == "true"


def state_key(case: str, beta: float, gamma: int, lambda_r: float) -> str:
    return f"{case}|beta={beta:.12g}|Gamma={gamma}|lambda_R={lambda_r:.12g}"


def add_state(
    states: dict[str, dict[str, Any]],
    *,
    case: str,
    beta: float,
    gamma: int,
    lambda_r: float,
    label: bool,
    source: str,
    label_source: str,
) -> None:
    key = state_key(case, beta, gamma, lambda_r)
    if key in states and states[key]["material_reconfiguration"] != label:
        raise RuntimeError(
            f"INCONSISTENT_DUPLICATE_LABEL: {key}: "
            f"{states[key]['material_reconfiguration']} vs {label} from {source}"
        )
    if key not in states:
        states[key] = {
            "state_key": key,
            "case": case,
            "beta": float(beta),
            "Gamma": int(gamma),
            "lambda_R": float(lambda_r),
            "source_experiments": [],
            "label_source": [],
            "material_reconfiguration": bool(label),
        }
    if source not in states[key]["source_experiments"]:
        states[key]["source_experiments"].append(source)
    if label_source not in states[key]["label_source"]:
        states[key]["label_source"].append(label_source)


def validate_result_row(row: dict[str, str], source: str) -> None:
    if row.get("status") and row["status"] != "OPTIMAL":
        raise RuntimeError(f"NONOPTIMAL_SOURCE_ROW: {source} {row.get('run_id')}")
    if row.get("certification_status") and "CERTIFIED" not in row["certification_status"]:
        raise RuntimeError(f"UNCERTIFIED_SOURCE_ROW: {source} {row.get('run_id')}")
    if row.get("exact_certification_pass") and not boolean(row["exact_certification_pass"]):
        raise RuntimeError(f"UNCERTIFIED_SOURCE_ROW: {source} {row.get('run_id')}")


def load_unique_states(root: Path = ROOT) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    source_rows: Counter[str] = Counter()
    sources = {
        "E2": root / "artifacts/e2_case_classification_summary.csv",
        "E3": root / "artifacts/e3_table_budget_sensitivity_case_level.csv",
        "E4": root / "artifacts/e4_table_gamma_sensitivity_case_level.csv",
        "E5": root / "artifacts/e5_table_friction_sensitivity_case_level.csv",
        "E7": root / "artifacts/e7_table_risk_friction_case_level.csv",
    }
    for path in sources.values():
        if not path.exists():
            raise FileNotFoundError(path)

    for row in read_csv(sources["E3"]):
        validate_result_row(row, "E3")
        source_rows["E3"] += 1
        add_state(
            states,
            case=row["case"],
            beta=float(row["beta"]),
            gamma=2,
            lambda_r=0.05,
            label=float(row["RI"]) > MATERIALITY_TOLERANCE,
            source="E3",
            label_source="E3:RI>1e-6",
        )
    for row in read_csv(sources["E4"]):
        validate_result_row(row, "E4")
        source_rows["E4"] += 1
        add_state(
            states,
            case=row["case"],
            beta=1.0,
            gamma=int(row["Gamma"]),
            lambda_r=0.05,
            label=float(row["RI"]) > MATERIALITY_TOLERANCE,
            source="E4",
            label_source="E4:RI>1e-6",
        )
    for row in read_csv(sources["E5"]):
        validate_result_row(row, "E5")
        source_rows["E5"] += 1
        add_state(
            states,
            case=row["case"],
            beta=1.0,
            gamma=2,
            lambda_r=float(row["lambda_R"]),
            label=boolean(row["material_reconfiguration"]),
            source="E5",
            label_source="E5:material_reconfiguration",
        )
    for row in read_csv(sources["E7"]):
        validate_result_row(row, "E7")
        source_rows["E7"] += 1
        add_state(
            states,
            case=row["case"],
            beta=1.0,
            gamma=int(row["Gamma"]),
            lambda_r=float(row["lambda_R"]),
            label=boolean(row["material_reconfiguration"]),
            source="E7",
            label_source="E7:material_reconfiguration",
        )
    for row in read_csv(sources["E2"]):
        source_rows["E2"] += 1
        add_state(
            states,
            case=row["case"],
            beta=1.0,
            gamma=2,
            lambda_r=0.05,
            label=boolean(row["material_reconfiguration"]),
            source="E2",
            label_source="E2:material_reconfiguration",
        )

    ordered = [states[key] for key in sorted(states)]
    if set(row["case"] for row in ordered) != set(CASES):
        raise RuntimeError("CASE_COVERAGE_MISMATCH")
    case_counts = Counter(row["case"] for row in ordered)
    if any(case_counts[case] != 17 for case in CASES):
        raise RuntimeError(f"STATE_GRID_MISMATCH: {dict(case_counts)}")
    audit = {
        "source_rows": dict(source_rows),
        "source_row_count": sum(source_rows.values()),
        "unique_state_count": len(ordered),
        "duplicates_removed": sum(source_rows.values()) - len(ordered),
        "duplicate_label_conflicts": 0,
        "source_sha256": {name: sha256(path) for name, path in sources.items()},
    }
    return ordered, audit


def coefficient_of_variation(values: np.ndarray) -> float:
    mean = float(np.mean(values))
    return float(np.std(values, ddof=0) / mean) if mean != 0.0 else 0.0


def hhi(values: np.ndarray) -> float:
    total = float(np.sum(values))
    if total <= 0.0:
        raise RuntimeError("HHI_REQUIRES_POSITIVE_TOTAL")
    shares = values / total
    return float(np.sum(shares * shares))


def static_features(case: str, root: Path = ROOT) -> dict[str, float]:
    instance_path = root / "data/formal_instances_v2" / f"{case}.json"
    x0_path = root / "artifacts/renault_empirical_8case_v1/x0" / f"{case}.json"
    instance = read_json(instance_path)
    x0_document = read_json(x0_path)
    if instance["depot_ids"] != x0_document["depot_ids"]:
        raise RuntimeError(f"DEPOT_IDENTITY_MISMATCH: {case}")
    if instance["product_ids"] != x0_document["product_ids"]:
        raise RuntimeError(f"PRODUCT_IDENTITY_MISMATCH: {case}")

    demand = np.asarray(instance["base_demand"], dtype=float)
    deviation = np.asarray(instance["demand_deviation"], dtype=float)
    x0 = np.asarray(x0_document["x0"], dtype=float)
    volume = np.asarray(instance["product_volume"], dtype=float)
    capacity = np.asarray(instance["capacity"], dtype=float)
    if demand.shape != deviation.shape:
        raise RuntimeError(f"DEMAND_SHAPE_MISMATCH: {case}")
    if x0.shape != (len(instance["depot_ids"]), len(instance["product_ids"])):
        raise RuntimeError(f"X0_SHAPE_MISMATCH: {case}")

    total_demand = float(np.sum(demand))
    total_deviation = float(np.sum(deviation))
    demand_mean = float(np.mean(demand))
    total_inventory = float(np.sum(x0))
    total_capacity = float(np.sum(capacity))
    incumbent_load = float(np.sum(x0 * volume[np.newaxis, :]))
    transport = np.asarray(instance["transport_cost"], dtype=float).ravel()
    inventory_cost = np.asarray(instance["inventory_cost"], dtype=float).ravel()
    shortage = np.asarray(instance["shortage_penalty"], dtype=float).ravel()
    service = np.asarray(instance["service_penalty"], dtype=float).ravel()
    fixed = np.asarray(instance["fixed_depot_cost"], dtype=float).ravel()

    features = {
        "total_nominal_demand": total_demand,
        "total_deviation": total_deviation,
        "deviation_to_nominal_ratio": total_deviation / total_demand,
        "nominal_demand_mean": demand_mean,
        "nominal_demand_std": float(np.std(demand, ddof=0)),
        "nominal_demand_cv": coefficient_of_variation(demand),
        "maximum_nominal_demand_to_mean_ratio": float(np.max(demand) / demand_mean),
        "demand_density": float(np.count_nonzero(demand > 0.0) / demand.size),
        "regional_demand_concentration": hhi(np.sum(demand, axis=1)),
        "product_demand_concentration": hhi(np.sum(demand, axis=0)),
        "total_incumbent_inventory": total_inventory,
        "inventory_to_nominal_demand_ratio": total_inventory / total_demand,
        "incumbent_inventory_concentration_across_depots": hhi(np.sum(x0, axis=1)),
        "incumbent_inventory_concentration_across_products": hhi(np.sum(x0, axis=0)),
        "total_capacity": total_capacity,
        "incumbent_capacity_utilization": incumbent_load / total_capacity,
        "capacity_slack_ratio": (total_capacity - incumbent_load) / total_capacity,
        "mean_transport_cost": float(np.mean(transport)),
        "transport_cost_cv": coefficient_of_variation(transport),
        "mean_inventory_cost": float(np.mean(inventory_cost)),
        "inventory_cost_cv": coefficient_of_variation(inventory_cost),
        "mean_shortage_penalty": float(np.mean(shortage)),
        "shortage_penalty_cv": coefficient_of_variation(shortage),
        "mean_service_penalty": float(np.mean(service)),
        "fixed_cost_cv": coefficient_of_variation(fixed),
    }
    if set(features) != set(STRUCTURAL_FEATURES):
        raise RuntimeError("STATIC_FEATURE_SCHEMA_MISMATCH")
    if not all(math.isfinite(value) for value in features.values()):
        raise RuntimeError(f"NONFINITE_STATIC_FEATURE: {case}")
    return features


def build_dataset(root: Path = ROOT) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    states, audit = load_unique_states(root)
    by_case = {case: static_features(case, root) for case in CASES}
    rows = []
    for state in states:
        row = dict(state)
        row["source_experiments"] = "|".join(state["source_experiments"])
        row["label_source"] = "|".join(state["label_source"])
        row.update(by_case[state["case"]])
        rows.append(row)
    audit.update(
        {
            "case_count": len(by_case),
            "states_per_case": dict(Counter(row["case"] for row in rows)),
            "positive_labels": sum(row["material_reconfiguration"] for row in rows),
            "negative_labels": sum(not row["material_reconfiguration"] for row in rows),
        }
    )
    return rows, audit


def metric_row(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    positives = int(tp + fn)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "material_recall": float(recall_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "false_negative_count": int(fn),
        "false_negative_rate": float(fn / positives) if positives else 0.0,
        "true_negative": int(tn),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_positive": int(tp),
    }


def tune_gamma_threshold(train_gamma: np.ndarray, train_y: np.ndarray) -> float:
    unique = sorted(set(float(value) for value in train_gamma))
    candidates = unique + [unique[-1] + 1.0]
    scored = []
    for threshold in candidates:
        prediction = (train_gamma >= threshold).astype(int)
        metrics = metric_row(train_y, prediction)
        scored.append(
            (
                metrics["balanced_accuracy"],
                metrics["material_recall"],
                metrics["accuracy"],
                -threshold,
                threshold,
            )
        )
    return float(max(scored)[-1])


def make_model(method: str) -> Any:
    if method.startswith("logistic_"):
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=1.0,
                        class_weight="balanced",
                        max_iter=5000,
                        solver="liblinear",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        )
    if method.startswith("tree_"):
        return DecisionTreeClassifier(
            max_depth=3,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=RANDOM_STATE,
        )
    if method.startswith("gradient_boosting_"):
        return GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=2,
            min_samples_leaf=5,
            random_state=RANDOM_STATE,
        )
    raise ValueError(method)


def evaluate_loco(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    features_by_method = {
        "logistic_control": CONTROL_FEATURES,
        "logistic_full": FULL_FEATURES,
        "tree_control": CONTROL_FEATURES,
        "tree_full": FULL_FEATURES,
        "gradient_boosting_control": CONTROL_FEATURES,
        "gradient_boosting_full": FULL_FEATURES,
    }
    cv_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    tree_rule_blocks: list[str] = []
    pooled: dict[str, dict[str, list[int]]] = defaultdict(lambda: {"true": [], "pred": []})

    for held_out in CASES:
        train = [row for row in rows if row["case"] != held_out]
        test = [row for row in rows if row["case"] == held_out]
        train_y = np.asarray([int(row["material_reconfiguration"]) for row in train])
        test_y = np.asarray([int(row["material_reconfiguration"]) for row in test])

        majority = int(np.sum(train_y) > len(train_y) / 2)
        majority_pred = np.full(len(test), majority, dtype=int)
        predictions: dict[str, tuple[np.ndarray, str]] = {
            "majority": (majority_pred, f"training_majority={majority}"),
        }
        train_gamma = np.asarray([float(row["Gamma"]) for row in train])
        test_gamma = np.asarray([float(row["Gamma"]) for row in test])
        gamma_threshold = tune_gamma_threshold(train_gamma, train_y)
        predictions["gamma_threshold"] = (
            (test_gamma >= gamma_threshold).astype(int),
            f"Gamma>={gamma_threshold:.12g}",
        )

        for method, feature_names in features_by_method.items():
            train_x = np.asarray([[float(row[name]) for name in feature_names] for row in train])
            test_x = np.asarray([[float(row[name]) for name in feature_names] for row in test])
            model = make_model(method)
            fit_kwargs = {}
            if method.startswith("gradient_boosting_"):
                fit_kwargs["sample_weight"] = compute_sample_weight("balanced", train_y)
            model.fit(train_x, train_y, **fit_kwargs)
            predictions[method] = (model.predict(test_x).astype(int), "")

            if method.startswith("logistic_"):
                coefficients = model.named_steps["model"].coef_[0]
                for feature, value in zip(feature_names, coefficients, strict=True):
                    importance_rows.append(
                        {
                            "scope": "fold",
                            "held_out_case": held_out,
                            "method": method,
                            "feature": feature,
                            "importance_type": "standardized_coefficient",
                            "value": float(value),
                            "absolute_value": abs(float(value)),
                            "std": "",
                        }
                    )
            elif method.startswith("tree_"):
                for feature, value in zip(feature_names, model.feature_importances_, strict=True):
                    importance_rows.append(
                        {
                            "scope": "fold",
                            "held_out_case": held_out,
                            "method": method,
                            "feature": feature,
                            "importance_type": "impurity_importance",
                            "value": float(value),
                            "absolute_value": abs(float(value)),
                            "std": "",
                        }
                    )
                tree_rule_blocks.extend(
                    [
                        f"## {method}; held out {held_out}",
                        "",
                        export_text(model, feature_names=feature_names),
                        "",
                    ]
                )
            else:
                permutation = permutation_importance(
                    model,
                    train_x,
                    train_y,
                    scoring="balanced_accuracy",
                    n_repeats=20,
                    random_state=RANDOM_STATE,
                )
                for feature, value, std in zip(
                    feature_names,
                    permutation.importances_mean,
                    permutation.importances_std,
                    strict=True,
                ):
                    importance_rows.append(
                        {
                            "scope": "fold",
                            "held_out_case": held_out,
                            "method": method,
                            "feature": feature,
                            "importance_type": "training_fold_permutation_balanced_accuracy",
                            "value": float(value),
                            "absolute_value": abs(float(value)),
                            "std": float(std),
                        }
                    )

        for method, (prediction, tuned_parameter) in predictions.items():
            metrics = metric_row(test_y, prediction)
            cv_rows.append(
                {
                    "held_out_case": held_out,
                    "method": method,
                    "train_case_count": 7,
                    "train_n": len(train),
                    "test_n": len(test),
                    "tuned_parameter": tuned_parameter,
                    **metrics,
                }
            )
            pooled[method]["true"].extend(test_y.tolist())
            pooled[method]["pred"].extend(prediction.tolist())

    confusion_rows = [
        {
            "scope": "held_out_case",
            "held_out_case": row["held_out_case"],
            "method": row["method"],
            "n": row["test_n"],
            "accuracy": row["accuracy"],
            "balanced_accuracy": row["balanced_accuracy"],
            "material_recall": row["material_recall"],
            "false_negative_count": row["false_negative_count"],
            "false_negative_rate": row["false_negative_rate"],
            "true_negative": row["true_negative"],
            "false_positive": row["false_positive"],
            "false_negative": row["false_negative"],
            "true_positive": row["true_positive"],
        }
        for row in cv_rows
    ]
    for method in sorted(pooled):
        metrics = metric_row(np.asarray(pooled[method]["true"]), np.asarray(pooled[method]["pred"]))
        confusion_rows.append(
            {"scope": "pooled_loco", "held_out_case": "", "method": method, "n": len(rows), **metrics}
        )

    fold_importance = list(importance_rows)
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in fold_importance:
        grouped[(row["method"], row["feature"], row["importance_type"])].append(float(row["value"]))
    for (method, feature, importance_type), values in sorted(grouped.items()):
        importance_rows.append(
            {
                "scope": "mean_across_loco_folds",
                "held_out_case": "",
                "method": method,
                "feature": feature,
                "importance_type": importance_type,
                "value": statistics.fmean(values),
                "absolute_value": statistics.fmean(abs(value) for value in values),
                "std": statistics.pstdev(values),
            }
        )
    return cv_rows, confusion_rows, importance_rows, "\n".join(tree_rule_blocks)


def classify_signal(cv_rows: list[dict[str, Any]], confusion_rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    pooled = {row["method"]: row for row in confusion_rows if row["scope"] == "pooled_loco"}
    full_methods = ("logistic_full", "tree_full", "gradient_boosting_full")
    best_full = max(full_methods, key=lambda method: pooled[method]["balanced_accuracy"])
    matched_control = best_full.replace("_full", "_control")
    comparators = ("majority", "gamma_threshold", matched_control)
    margins = {
        method: pooled[best_full]["balanced_accuracy"] - pooled[method]["balanced_accuracy"]
        for method in comparators
    }
    fold_lookup = {(row["held_out_case"], row["method"]): row for row in cv_rows}
    nonworse_folds = sum(
        fold_lookup[(case, best_full)]["balanced_accuracy"]
        >= fold_lookup[(case, matched_control)]["balanced_accuracy"]
        for case in CASES
    )
    fnr_delta = pooled[best_full]["false_negative_rate"] - pooled[matched_control]["false_negative_rate"]
    if min(margins.values()) >= 0.05 and nonworse_folds >= 6 and fnr_delta <= 0.05:
        classification = "PROMISING"
    elif max(margins.values()) >= 0.02 and fnr_delta <= 0.10:
        classification = "WEAK_SIGNAL"
    else:
        classification = "NO_EVIDENCE"
    return classification, {
        "best_full_model": best_full,
        "matched_control_model": matched_control,
        "balanced_accuracy_margins": margins,
        "full_nonworse_than_control_fold_count": nonworse_folds,
        "false_negative_rate_delta_vs_control": fnr_delta,
        "rule": {
            "PROMISING": "best full BA >= each comparator by 0.05, nonworse in >=6/8 folds, FNR increase <=0.05",
            "WEAK_SIGNAL": "not PROMISING, but a BA margin >=0.02 and FNR increase <=0.10",
            "NO_EVIDENCE": "otherwise",
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = fieldnames or list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_feature_dictionary(path: Path) -> None:
    lines = [
        "# AI risk-trigger pilot feature dictionary",
        "",
        "All model inputs are available before optimization. Population standard deviations use `ddof=0`. HHI means the sum of squared shares. Cost means and CVs use every entry in the corresponding frozen formal-instance array.",
        "",
        "| Feature | Definition | Frozen source |",
        "|---|---|---|",
    ]
    for feature in FULL_FEATURES:
        definition, source = FEATURE_DEFINITIONS[feature]
        lines.append(f"| `{feature}` | {definition} | {source} |")
    lines.extend(
        [
            "",
            "## Label",
            "",
            "`material_reconfiguration` uses the frozen rule `RI > 1e-6`. E5 and E7 provide the stored field directly. E2 provides its frozen classification field. E3 and E4 labels are reconstructed from their stored RI using the same threshold. RI is used only to construct the outcome label and never appears among model inputs.",
            "",
            "## Metadata excluded from models",
            "",
            "`state_key`, `case`, `source_experiments`, and `label_source` support provenance and grouped validation only. They are never passed to a classifier.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(
    path: Path,
    dataset_audit: dict[str, Any],
    cv_rows: list[dict[str, Any]],
    confusion_rows: list[dict[str, Any]],
    importance_rows: list[dict[str, Any]],
    classification: str,
    classification_detail: dict[str, Any],
) -> None:
    pooled = {row["method"]: row for row in confusion_rows if row["scope"] == "pooled_loco"}
    lines = [
        "# AI risk-trigger feasibility pilot",
        "",
        "## Scope",
        "",
        "This exploratory diagnostic tests whether pre-solve controls and frozen case structure predict material inventory reconfiguration for a case that is absent from training. It does not replace, screen, or skip optimization.",
        "",
        "## Data and validation",
        "",
        f"- Source rows: {dataset_audit['source_row_count']}",
        f"- Unique decision states after exact key deduplication: {dataset_audit['unique_state_count']}",
        f"- Duplicate source rows removed: {dataset_audit['duplicates_removed']}",
        f"- Material / non-material labels: {dataset_audit['positive_labels']} / {dataset_audit['negative_labels']}",
        "- Validation: eight-fold leave-one-case-out; 7 cases train and one unseen case tests in every fold",
        "- Label: frozen `RI > 1e-6` materiality rule",
        "- Model inputs exclude all optimization outcomes, identifiers, runtimes, iterations, cuts, service outcomes, and shortage outcomes",
        "",
        "## Pooled out-of-case results",
        "",
        "| Method | Accuracy | Balanced accuracy | Material recall | False negatives | False-negative rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in sorted(pooled):
        row = pooled[method]
        lines.append(
            f"| {method} | {row['accuracy']:.3f} | {row['balanced_accuracy']:.3f} | "
            f"{row['material_recall']:.3f} | {row['false_negative_count']} | "
            f"{row['false_negative_rate']:.3f} |"
        )
    detail = classification_detail
    fold_lookup = {(row["held_out_case"], row["method"]): row for row in cv_rows}
    aggregate_importance = [
        row
        for row in importance_rows
        if row["scope"] == "mean_across_loco_folds" and row["method"] == detail["best_full_model"]
    ]
    top_features = sorted(aggregate_importance, key=lambda row: row["absolute_value"], reverse=True)[:5]
    lines.extend(
        [
            "",
            "## Held-out case results",
            "",
            "| Held-out case | Gamma threshold BA / FN | Matched control BA / FN | Best full BA / FN |",
            "|---|---:|---:|---:|",
        ]
    )
    for case in CASES:
        gamma = fold_lookup[(case, "gamma_threshold")]
        control = fold_lookup[(case, detail["matched_control_model"])]
        full = fold_lookup[(case, detail["best_full_model"])]
        lines.append(
            f"| {case} | {gamma['balanced_accuracy']:.3f} / {gamma['false_negative_count']} | "
            f"{control['balanced_accuracy']:.3f} / {control['false_negative_count']} | "
            f"{full['balanced_accuracy']:.3f} / {full['false_negative_count']} |"
        )
    lines.extend(
        [
            "",
            "## Structural-signal assessment",
            "",
            f"Best full model: `{detail['best_full_model']}`. Matched control-only model: `{detail['matched_control_model']}`.",
            "",
            f"The full model is non-worse than its matched control in {detail['full_nonworse_than_control_fold_count']}/8 held-out cases. Its pooled false-negative-rate difference versus the control is {detail['false_negative_rate_delta_vs_control']:.3f}.",
            "",
            "This is predictive association, not causal evidence. Feature coefficients and importances describe fitted predictive behavior under this small eight-case design.",
            "",
            "Gradient-boosting permutation importance is computed inside each seven-case training fold because case-level structural features are constant within a single held-out case. Top mean absolute importance values for the selected full model are reported below. They must not be interpreted causally.",
            "",
            "| Feature | Importance type | Mean value | Mean absolute value |",
            "|---|---|---:|---:|",
        ]
    )
    for row in top_features:
        lines.append(
            f"| `{row['feature']}` | {row['importance_type']} | {row['value']:.4f} | "
            f"{row['absolute_value']:.4f} |"
        )
    lines.extend(
        [
            "",
            f"## Final classification: {classification}",
            "",
            "The classification follows the predeclared balanced-accuracy, held-out-case stability, and false-negative safeguards recorded in the leakage audit. No target result was imposed.",
            "",
            "No optimization solver was imported or called. No E1-E7 result, formal instance, model source, or paper-final artifact was modified.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_pilot(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    rows, dataset_audit = build_dataset(ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_fields = [
        "state_key",
        "case",
        "beta",
        "Gamma",
        "lambda_R",
        "source_experiments",
        "label_source",
        *STRUCTURAL_FEATURES,
        "material_reconfiguration",
    ]
    write_csv(output_dir / "ai_trigger_pilot_dataset.csv", rows, dataset_fields)
    write_feature_dictionary(output_dir / "ai_trigger_feature_dictionary.md")

    cv_rows, confusion_rows, importance_rows, tree_rules = evaluate_loco(rows)
    write_csv(output_dir / "ai_trigger_cv_results.csv", cv_rows)
    write_csv(output_dir / "ai_trigger_confusion_summary.csv", confusion_rows)
    write_csv(output_dir / "ai_trigger_feature_importance.csv", importance_rows)
    (output_dir / "ai_trigger_tree_rules.txt").write_text(tree_rules.rstrip() + "\n", encoding="utf-8")

    classification, classification_detail = classify_signal(cv_rows, confusion_rows)
    fold_cases = []
    for held_out in CASES:
        train_cases = sorted(case for case in CASES if case != held_out)
        fold_cases.append(
            {
                "held_out_case": held_out,
                "train_cases": train_cases,
                "test_cases": [held_out],
                "case_overlap": [],
            }
        )
    leakage_audit = {
        "status": "PASS",
        "solver_imported_or_called": False,
        "optimization_runs": 0,
        "model_feature_columns": FULL_FEATURES,
        "control_only_feature_columns": CONTROL_FEATURES,
        "identifier_columns_used_as_features": [],
        "post_solve_columns_used_as_features": [],
        "prohibited_feature_intersection": sorted(set(FULL_FEATURES) & PROHIBITED_INPUTS),
        "label_only_post_solve_field": "RI/material_reconfiguration",
        "deduplication": dataset_audit,
        "loco_folds": fold_cases,
        "all_fold_case_overlaps_empty": True,
        "classification_detail": classification_detail,
    }
    (output_dir / "ai_trigger_data_leakage_audit.json").write_text(
        json.dumps(leakage_audit, indent=2, sort_keys=True), encoding="utf-8"
    )
    static_audit = {
        "status": "AI_TRIGGER_STATIC_AUDIT_PASS",
        "required_source_files_present": True,
        "all_eight_cases_have_static_features": True,
        "materiality_definition": "RI > 1e-6",
        "unique_state_count": dataset_audit["unique_state_count"],
        "duplicate_label_conflicts": dataset_audit["duplicate_label_conflicts"],
        "sklearn_version": __import__("sklearn").__version__,
        "instance_sha256": {
            case: sha256(ROOT / "data/formal_instances_v2" / f"{case}.json") for case in CASES
        },
        "x0_sha256": {
            case: sha256(ROOT / "artifacts/renault_empirical_8case_v1/x0" / f"{case}.json")
            for case in CASES
        },
        "optimization_runs": 0,
    }
    (output_dir / "ai_trigger_static_audit.json").write_text(
        json.dumps(static_audit, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_report(
        output_dir / "ai_trigger_pilot_report.md",
        dataset_audit,
        cv_rows,
        confusion_rows,
        importance_rows,
        classification,
        classification_detail,
    )
    return {
        "classification": classification,
        "dataset_audit": dataset_audit,
        "confusion_rows": confusion_rows,
        "classification_detail": classification_detail,
        "output_dir": str(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the solver-free AI risk-trigger feasibility pilot.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_pilot(args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
