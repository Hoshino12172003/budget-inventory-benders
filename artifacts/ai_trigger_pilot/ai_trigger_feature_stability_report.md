# AI risk-trigger feature stability audit

Source importance SHA-256: `d9a5291f009dacc6f0c8073f003a437dd669bf002b61bccb7ef76dee63d707de`. This audit reads the frozen fold-level importance records from commit `92c79a836f5d233f783f0ccd00f2f88c87bbc282`. It does not refit a classifier or run an optimization model.

## Predeclared rules

Gradient Boosting uses raw training-fold permutation importance. `CV = population std / abs(mean)`; a zero mean with nonzero dispersion has infinite CV.

- `STABLE`: nonzero in at least 7/8 folds, top-5 in at least 6/8 folds, and CV at most 0.75.
- `MODERATELY_STABLE`: nonzero in at least 4/8 folds, top-5 in at least 3/8 folds, and CV at most 1.50.
- `UNSTABLE`: otherwise.
- Logistic `SIGN_STABLE`: at least 6 nonzero folds and dominant sign in at least 7/8 nonzero folds.
- Logistic `SIGN_MODERATELY_STABLE`: at least 4 nonzero folds and dominant sign in at least 6/8 nonzero folds.
- Logistic `SIGN_UNSTABLE`: otherwise.
- Overall `STABLE_STRUCTURAL_SIGNAL`: Gradient Boosting mean pairwise top-5 Jaccard at least 0.60 and at least 4/5 focal features jointly non-unstable under Gradient Boosting and Logistic sign checks.
- Overall `PARTIALLY_STABLE_SIGNAL`: Jaccard at least 0.30 and at least 2/5 focal features jointly non-unstable.
- Otherwise: `UNSTABLE_SIGNAL`.

## Top-5 overlap

| Full model | Mean pairwise Jaccard |
|---|---:|
| `logistic_full` | 0.409 |
| `tree_full` | 0.435 |
| `gradient_boosting_full` | 0.550 |

Gradient Boosting leave-one-case sensitivity:

| Held-out case | Top-5 features | Mean overlap with other folds | Minimum overlap |
|---|---|---:|---:|
| 210129 | `Gamma`, `beta`, `maximum_nominal_demand_to_mean_ratio`, `nominal_demand_cv`, `transport_cost_cv` | 0.403 | 0.250 |
| 210202 | `Gamma`, `beta`, `incumbent_inventory_concentration_across_depots`, `inventory_to_nominal_demand_ratio`, `mean_transport_cost` | 0.412 | 0.250 |
| 210310 | `Gamma`, `beta`, `capacity_slack_ratio`, `demand_density`, `transport_cost_cv` | 0.539 | 0.250 |
| 210323 | `Gamma`, `beta`, `incumbent_inventory_concentration_across_depots`, `mean_transport_cost`, `transport_cost_cv` | 0.531 | 0.429 |
| 210330 | `Gamma`, `beta`, `capacity_slack_ratio`, `inventory_to_nominal_demand_ratio`, `transport_cost_cv` | 0.612 | 0.429 |
| 210428 | `Gamma`, `beta`, `capacity_slack_ratio`, `inventory_to_nominal_demand_ratio`, `transport_cost_cv` | 0.612 | 0.429 |
| 210611 | `Gamma`, `beta`, `capacity_slack_ratio`, `incumbent_inventory_concentration_across_depots`, `transport_cost_cv` | 0.646 | 0.429 |
| 210628 | `Gamma`, `beta`, `capacity_slack_ratio`, `incumbent_inventory_concentration_across_depots`, `transport_cost_cv` | 0.646 | 0.429 |

## Focal feature audit

| Feature | GB mean | GB CV | GB top-5 folds | GB class | Logistic + / - / 0 | Sign ratio | Sign class |
|---|---:|---:|---:|---|---:|---:|---|
| `Gamma` | 0.2044 | 0.100 | 8/8 | STABLE | 8 / 0 / 0 | 1.000 | SIGN_STABLE |
| `transport_cost_cv` | 0.1148 | 0.856 | 7/8 | MODERATELY_STABLE | 4 / 4 / 0 | 0.500 | SIGN_UNSTABLE |
| `beta` | 0.1039 | 0.152 | 8/8 | STABLE | 0 / 8 / 0 | 1.000 | SIGN_STABLE |
| `inventory_to_nominal_demand_ratio` | 0.0486 | 2.125 | 3/8 | UNSTABLE | 6 / 2 / 0 | 0.750 | SIGN_MODERATELY_STABLE |
| `incumbent_inventory_concentration_across_depots` | 0.0465 | 1.982 | 4/8 | UNSTABLE | 8 / 0 / 0 | 1.000 | SIGN_STABLE |

## Interpretation

Gradient Boosting mean pairwise top-5 overlap is 0.550. Only 2/5 focal features are jointly non-unstable across the Gradient Boosting magnitude and Logistic sign checks. The fold-specific top feature set therefore changes materially when some individual Renault cases are removed.

These diagnostics describe predictive stability in a small eight-case sample. Feature importance and coefficient direction are not causal effects.

## Final classification

PARTIALLY_STABLE_SIGNAL
