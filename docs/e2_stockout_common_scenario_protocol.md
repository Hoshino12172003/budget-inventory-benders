# E2 fixed-policy common-scenario stockout protocol

## Scope and authorization

This is a new supplemental protocol, `E2_STOCKOUT_COMMON_SCENARIO_V1`. It does
not replace or overwrite the historical E2 protocol. Its manifest is
`experiments/configs/e2_stockout_common_scenario_manifest.json`.

The manifest freezes `formal_run_authorized=false`. The current authorization is
limited to a three-scenario, one-case, Existing-policy pilot. A full 8-case run
must be a separate, explicit authorization change after human policy review.

## Frozen inputs

For every Renault case the manifest freezes:

- the instance path and SHA-256;
- the coordinate hash of each candidate first-stage policy;
- 12 regions, 8 products, and 96 uncertain region-product components;
- `Gamma=2`;
- the canonical region-major scenario order;
- all 4,657 scenarios with zero, one, or two binary demand shocks;
- the SHA-256 of the canonical scenario list;
- the formal LP solver tolerances and one-thread execution;
- the existing `1e-7` economic-band reporting tie-break.

The instance SHA-256 jointly freezes base demand, demand deviation, service
levels, service penalties, transport costs, shortage penalties, inventory data,
and all other instance parameters. The evaluator does not accept alternative
parameter arrays.

## Fixed first stage

The evaluator loads and validates a policy coordinate payload
`{y,x,a_plus,a_minus}`. It hashes the payload before and after evaluation and
fails if the hashes differ. Only `x` enters the recourse constraints; `y` and the
adjustment matrices remain part of the immutable policy identity.

The evaluator module does not import or call first-stage solution functions. A
static AST audit rejects calls named `solve_prb_benders`,
`solve_exact_reconfiguration`, `build_exact_reconfiguration_model`, or
`optimize_first_stage`.

## Second-stage model

For fixed inventory and scenario `omega`, the evaluator solves only:

- shipment `q_irj(omega)`;
- shortage `u_rj(omega)`;
- soft-service excess `e_j(omega)`.

It retains the original demand, inventory, and soft-service constraints and the
original economic objective:

```text
transportation_cost = sum_i,r,j c_irj q_irj
shortage_penalty_cost = sum_r,j pi_rj u_rj
service_penalty_cost = sum_j phi_j e_j
recourse_cost = transportation_cost
              + shortage_penalty_cost
              + service_penalty_cost
```

All three cost components are read directly from solved expressions. No shortage
quantity or shortage cost is inferred from a total-objective difference.

After the economic optimum is found, every product-local block is constrained
to its optimum plus `1e-7`, and the evaluator minimizes the original sum of
squared shortages. It records both the post-tie-break direct component sum and
the economic optimum, plus their numerical delta.

## Exact product-block equivalence

The product-local implementation is exact for this frozen model:

1. For fixed `x`, every recourse variable and constraint carries exactly one
   product index. There is no cross-product shipping capacity or service
   constraint.
2. Transportation, shortage, and service penalties are additive over products.
3. A full scenario with global shock budget two maps uniquely to product-local
   shock sets whose cardinalities sum to at most two.
4. Therefore the optimum for a full scenario is the sum of its eight
   product-local optima.
5. The reporting objective is also a sum of squared product-local shortages,
   and the economic-band constraints are imposed per local block. Its minimizer
   is consequently obtained by independently applying the same tie-break to
   each block.

For one case-policy task only

```text
8 * (C(12,0) + C(12,1) + C(12,2)) = 632
```

unique blocks are needed. Tests compare the block evaluator against the existing
full-scenario evaluator on every requested metric for a small instance.

If a future model introduces a cross-product recourse constraint, the proof no
longer holds and the static protocol must fail or move to direct full-scenario
evaluation.

## Scenario output

`experiments/schemas/e2_stockout_scenario_result.schema.json` requires:

- scenario and shock identity;
- policy and instance hashes;
- solver status;
- total shipment and shortage;
- shortage and service excess by product;
- total service excess;
- direct transport, shortage-penalty, and service-penalty costs;
- direct component sum and economic optimum cost;
- tie-break cost delta.

Unsolved, infeasible, timed-out, missing, non-finite, corrupt, or identity-mismatched
records are errors. They are never converted to zero.

## Predeclared publication metrics

For the no-shock common scenario `S0000`, report total shortage, total service
excess, shortage penalty, service penalty, transport cost, the direct
post-tie-break component sum, and the economic-optimum recourse cost.

Over the complete frozen set, separately report:

- maximum total shortage;
- maximum total service excess;
- maximum shortage-penalty cost;
- maximum `economic_optimum_recourse_cost`.

Each metric retains its maximizing scenario. Ties within `1e-9` retain the full
tied scenario-ID list and select the first canonical scenario as the
representative. Maximum shortage and maximum economic cost are never treated as
the same functional unless their recorded scenario IDs actually agree.

For baseline value `M_B > 1e-9`, improvement is

```text
100 * (M_B - M_policy) / M_B
```

Otherwise the output is JSON `null`, interpreted as `NA`, not zero. Scenario
averages are not labeled as expectations because no probability distribution is
defined.

## Checkpoint and resource protocol

Every case-policy task is serial and uses `Threads=1`. A checkpoint records and
validates the instance, policy, scenario manifest, evaluator code, and config
hashes. A sidecar SHA-256 protects checkpoint content. A missing or mismatched
hash refuses resume. Diagnostic files are not checkpoint inputs.

For a future full run, process one case-policy task at a time, write its 632
block results and scenario aggregates, dispose the model, and only then continue.
Do not load multiple complete scenario datasets concurrently.

The conservative future workload is 24 case-policy tasks, 15,168 unique local
blocks, and 111,768 logical policy-scenario rows. No part of that workload is
authorized by the present manifest.

## Pilot declaration

The only predeclared pilot is:

- case `210202`;
- policy `EXISTING_CANONICAL_210202`;
- scenarios `S0000`, `S0001`, and `S0097`;
- classification `PILOT_NON_PUBLISHABLE`.

Pilot data must not enter paper result tables.
