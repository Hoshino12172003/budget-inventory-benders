# AI risk-trigger pilot feature dictionary

All model inputs are available before optimization. Population standard deviations use `ddof=0`. HHI means the sum of squared shares. Cost means and CVs use every entry in the corresponding frozen formal-instance array.

| Feature | Definition | Frozen source |
|---|---|---|
| `Gamma` | Demand-risk budget for the decision state. | Frozen E2/E3/E4/E5/E7 protocol |
| `beta` | Financial budget multiplier B/B_ref for the decision state. | Frozen E2/E3/E4/E5/E7 protocol |
| `lambda_R` | Symmetric inventory-reconfiguration friction multiplier. | Frozen E2/E3/E4/E5/E7 protocol |
| `total_nominal_demand` | sum_(r,j) dbar[r,j] | formal instance base_demand |
| `total_deviation` | sum_(r,j) dhat[r,j] | formal instance demand_deviation |
| `deviation_to_nominal_ratio` | total_deviation / total_nominal_demand | formal instance |
| `nominal_demand_mean` | Population mean over the R by J nominal-demand matrix. | formal instance base_demand |
| `nominal_demand_std` | Population standard deviation over the R by J nominal-demand matrix. | formal instance base_demand |
| `nominal_demand_cv` | nominal_demand_std / nominal_demand_mean | formal instance base_demand |
| `maximum_nominal_demand_to_mean_ratio` | max(dbar) / mean(dbar) | formal instance base_demand |
| `demand_density` | count(dbar[r,j] > 0) / (R*J) | formal instance base_demand |
| `regional_demand_concentration` | HHI of regional shares: sum_r (sum_j dbar[r,j] / total)^2 | formal instance base_demand |
| `product_demand_concentration` | HHI of product shares: sum_j (sum_r dbar[r,j] / total)^2 | formal instance base_demand |
| `total_incumbent_inventory` | sum_(i,j) x0[i,j] in inventory units | frozen x0 artifact |
| `inventory_to_nominal_demand_ratio` | total_incumbent_inventory / total_nominal_demand | frozen x0 plus formal instance |
| `incumbent_inventory_concentration_across_depots` | HHI of depot shares of x0. | frozen x0 artifact |
| `incumbent_inventory_concentration_across_products` | HHI of product shares of x0. | frozen x0 artifact |
| `total_capacity` | sum_i C[i] in the model's volume units. | formal instance capacity |
| `incumbent_capacity_utilization` | sum_(i,j) volume[j]*x0[i,j] / sum_i C[i] | frozen x0 and formal instance product_volume/capacity |
| `capacity_slack_ratio` | 1 - incumbent_capacity_utilization | frozen x0 and formal instance |
| `mean_transport_cost` | Population mean over the full transport-cost tensor. | formal instance transport_cost |
| `transport_cost_cv` | Population standard deviation / mean of transport_cost. | formal instance transport_cost |
| `mean_inventory_cost` | Population mean over inventory_cost. | formal instance inventory_cost |
| `inventory_cost_cv` | Population standard deviation / mean of inventory_cost. | formal instance inventory_cost |
| `mean_shortage_penalty` | Population mean over shortage_penalty. | formal instance shortage_penalty |
| `shortage_penalty_cv` | Population standard deviation / mean of shortage_penalty. | formal instance shortage_penalty |
| `mean_service_penalty` | Population mean over service_penalty. | formal instance service_penalty |
| `fixed_cost_cv` | Population standard deviation / mean of fixed planning-period depot cost. | formal instance fixed_depot_cost |

## Label

`material_reconfiguration` uses the frozen rule `RI > 1e-6`. E5 and E7 provide the stored field directly. E2 provides its frozen classification field. E3 and E4 labels are reconstructed from their stored RI using the same threshold. RI is used only to construct the outcome label and never appears among model inputs.

## Metadata excluded from models

`state_key`, `case`, `source_experiments`, and `label_source` support provenance and grouped validation only. They are never passed to a classifier.
