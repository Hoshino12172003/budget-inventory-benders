# E2 fixed-policy common-scenario stockout protocol

## Scope and authorization

This is a new supplemental protocol, `E2_STOCKOUT_COMMON_SCENARIO_V1`. It does
not replace or overwrite the historical E2 protocol. Its manifest is
`experiments/configs/e2_stockout_common_scenario_manifest.json`.

The manifest freezes `formal_run_authorized=false`. In addition to the original
three-scenario Pilot, a separate non-publishable authorization permits exactly
one complete resource and recovery preflight for case `210202` under the
Existing Baseline. A full 16-task run requires a later explicit authorization.

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

## Policy comparison definition

The supplemental analysis contains two independent first-stage configurations:

1. **Baseline:** `EXISTING_CANONICAL_<case>`, the canonical `x0/y0` policy.
2. **Robust candidate:** `ROBUST_EQUIVALENT_SCAL_BASE_<case>`, accepted by the
   user as a later exactly certified policy while retaining its SCAL_BASE
   lineage.

`NOMINAL_CANONICAL_REDECLARED_<case>` has exactly the same coordinate hash as
Baseline in all eight cases. It remains visible as a policy-validation label,
but it is not counted or plotted as a third independent configuration. The
original E2 Nominal coordinates remain unrecovered. Likewise, the Robust
candidates are not relabeled as original E1/E2 coordinates.
The scientific decision and all eight identity hashes are recorded in
`docs/e2_stockout_scientific_policy_confirmation.md`.

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

### Scenario-coverage gate

Formal worst-value reporting uses `summarize_complete_policy_metrics`. The
function accepts the authenticated common-scenario manifest and case ID, derives
`S0000` through `S4656` internally, verifies the manifest payload and frozen ID
order hash, and then checks exact set equality. The caller cannot substitute an
arbitrary expected set. Duplicates, missing IDs, unknown IDs, non-optimal rows,
missing metrics, and count mismatches are rejected. Merely receiving 4,657 rows
is not sufficient.

Pilot and diagnostic subsets use `summarize_partial_policy_metrics`. Their
output is marked `PARTIAL_SCENARIO_DIAGNOSTIC` and may contain only:

- an independent `S0000` nominal-scenario summary when `S0000` is present; and
- `worst_over_observed_subset`, which has no complete uncertainty-set meaning.

Partial output never contains `worst_over_frozen_set`. There is no silent
fallback from the complete interface to the partial interface.

## Checkpoint and resource protocol

Every case-policy task is serial and uses `Threads=1`. A checkpoint records and
validates the instance, policy, scenario manifest, evaluator code, and config
hashes. A sidecar SHA-256 protects checkpoint content. A missing or mismatched
hash refuses resume. Diagnostic files are not checkpoint inputs.

For a future full run, process one case-policy task at a time, write its 632
block results and scenario aggregates, dispose the model, and only then continue.
Do not load multiple complete scenario datasets concurrently.

The frozen comparison contains 16 case-policy tasks: eight Existing Baselines
and eight later SCAL_BASE Robust candidates. Nominal is a validation label and
is never scheduled. The workload is 10,112 unique local blocks and 74,512
logical policy-scenario rows. No part of that workload is authorized by the
present formal manifest.

### Authorized non-publishable full-case preflight

`experiments/configs/e2_stockout_resource_preflight_authorization.json`
authorizes only `210202` and `EXISTING_CANONICAL_210202`. It freezes all 4,657
scenario IDs, the 632-block order, `Threads=1`, code/protocol/schema hashes, and
an intentional interruption after block 16. `preflight-interrupt` writes a
digest-protected incomplete checkpoint; `preflight-resume` validates the exact
completed prefix and every identity before solving block 17 onward.

Each block uses the unchanged economic recourse objective and unchanged
reporting tie-break. The product-local separation proof above makes independent
block solution strictly equivalent to the combined separable model. The final
checkpoint is marked `PREFLIGHT_NON_PUBLISHABLE`, must cover exactly 632 blocks
and 4,657 scenario rows, and must pass the same row, cost, tie-break, scenario,
policy, and instance validation as a formal task. It records per-segment elapsed
time and peak RSS, both Gurobi statuses for every block, output size, digests,
and explicit interrupted-checkpoint recovery evidence. It is never a paper
result and cannot be resumed as a formal checkpoint.

## Formal runner and authorization chain

The independent formal entry point is the `formal-run` command in
`experiments/run_e2_stockout_common_scenario.py`. Before creating an output
directory or invoking the evaluator it validates:

- the supplemental authorization payload hash and an explicit `[false, true]`
  authorization transition;
- four separate human approvals and the exact list of 16 task IDs;
- formal authorization in both identity and scenario manifests;
- per-policy formal authorization for Existing and SCAL_BASE only;
- the runner, evaluator dependencies, protocol, schemas, policy manifest,
  scenario manifest, instance, policy, scenario order, and scenario-ID hashes.

The committed supplemental authorization remains false. `formal-run` and
`resume-formal` therefore fail before solving. The historical E2 authorization
is not accepted by this runner.

Completed formal tasks use the separate
`e2_stockout_formal_checkpoint.schema.json` contract. Resume revalidates the
sidecar digest, all identities, every scenario/shock/policy/instance identity,
solver status, required metrics, product totals, cost decomposition, tie-break
band, exact 4,657-row coverage, and recomputed worst metrics. Pilot checkpoints
cannot be resumed as formal checkpoints.

## Pilot declaration

The only predeclared pilot is:

- case `210202`;
- policy `EXISTING_CANONICAL_210202`;
- scenarios `S0000`, `S0001`, and `S0097`;
- classification `PILOT_NON_PUBLISHABLE`.

Pilot data must not enter paper result tables.
