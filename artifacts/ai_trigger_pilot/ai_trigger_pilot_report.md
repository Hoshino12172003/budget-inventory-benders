# AI risk-trigger feasibility pilot

## Scope

This exploratory diagnostic tests whether pre-solve controls and frozen case structure predict material inventory reconfiguration for a case that is absent from training. It does not replace, screen, or skip optimization.

## Data and validation

- Source rows: 200
- Unique decision states after exact key deduplication: 136
- Duplicate source rows removed: 64
- Material / non-material labels: 65 / 71
- Validation: eight-fold leave-one-case-out; 7 cases train and one unseen case tests in every fold
- Label: frozen `RI > 1e-6` materiality rule
- Model inputs exclude all optimization outcomes, identifiers, runtimes, iterations, cuts, service outcomes, and shortage outcomes

## Pooled out-of-case results

| Method | Accuracy | Balanced accuracy | Material recall | False negatives | False-negative rate |
|---|---:|---:|---:|---:|---:|
| gamma_threshold | 0.684 | 0.696 | 0.969 | 2 | 0.031 |
| gradient_boosting_control | 0.566 | 0.573 | 0.723 | 18 | 0.277 |
| gradient_boosting_full | 0.721 | 0.721 | 0.723 | 18 | 0.277 |
| logistic_control | 0.654 | 0.657 | 0.723 | 18 | 0.277 |
| logistic_full | 0.426 | 0.432 | 0.554 | 29 | 0.446 |
| majority | 0.184 | 0.183 | 0.169 | 54 | 0.831 |
| tree_control | 0.566 | 0.573 | 0.723 | 18 | 0.277 |
| tree_full | 0.647 | 0.644 | 0.569 | 28 | 0.431 |

## Held-out case results

| Held-out case | Gamma threshold BA / FN | Matched control BA / FN | Best full BA / FN |
|---|---:|---:|---:|
| 210129 | 0.964 / 1 | 0.964 / 1 | 0.679 / 9 |
| 210202 | 0.964 / 1 | 0.964 / 1 | 0.964 / 1 |
| 210310 | 0.667 / 0 | 0.667 / 0 | 0.667 / 0 |
| 210323 | 1.000 / 0 | 0.692 / 8 | 0.692 / 8 |
| 210330 | 1.000 / 0 | 0.692 / 8 | 1.000 / 0 |
| 210428 | 0.633 / 0 | 0.633 / 0 | 0.600 / 0 |
| 210611 | 0.633 / 0 | 0.633 / 0 | 1.000 / 0 |
| 210628 | 0.633 / 0 | 0.633 / 0 | 1.000 / 0 |

## Structural-signal assessment

Best full model: `gradient_boosting_full`. Matched control-only model: `gradient_boosting_control`.

The full model is non-worse than its matched control in 6/8 held-out cases. Its pooled false-negative-rate difference versus the control is 0.000.

This is predictive association, not causal evidence. Feature coefficients and importances describe fitted predictive behavior under this small eight-case design.

Gradient-boosting permutation importance is computed inside each seven-case training fold because case-level structural features are constant within a single held-out case. Top mean absolute importance values for the selected full model are reported below. They must not be interpreted causally.

| Feature | Importance type | Mean value | Mean absolute value |
|---|---|---:|---:|
| `Gamma` | training_fold_permutation_balanced_accuracy | 0.2044 | 0.2044 |
| `transport_cost_cv` | training_fold_permutation_balanced_accuracy | 0.1148 | 0.1148 |
| `beta` | training_fold_permutation_balanced_accuracy | 0.1039 | 0.1039 |
| `inventory_to_nominal_demand_ratio` | training_fold_permutation_balanced_accuracy | 0.0486 | 0.0486 |
| `incumbent_inventory_concentration_across_depots` | training_fold_permutation_balanced_accuracy | 0.0465 | 0.0465 |

## Final classification: WEAK_SIGNAL

The classification follows the predeclared balanced-accuracy, held-out-case stability, and false-negative safeguards recorded in the leakage audit. No target result was imposed.

No optimization solver was imported or called. No E1-E7 result, formal instance, model source, or paper-final artifact was modified.
