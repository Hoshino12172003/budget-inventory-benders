# E2 stockout common-scenario pilot report

## Status

The pilot passed. It is explicitly classified `PILOT_NON_PUBLISHABLE` and is
not an E2 paper result.

## Frozen pilot identity

- Case: `210202`
- Policy: `EXISTING_CANONICAL_210202`
- Policy lineage: original canonical Existing policy
- Scenarios: `S0000`, `S0001`, `S0097`
- Solver: Gurobi 13.0.1
- Threads: 1
- Formal-run authorization: false

The pilot result and restart checkpoint are stored under
`experiments/results/e2_stockout_common_scenario_pilot_v1/`.

## Checks performed

- The input instance and policy hashes matched both manifests.
- The scenario-order hash matched the frozen 4,657-scenario enumeration.
- The first-stage coordinate hash was identical before and after evaluation.
- All three scenarios solved with `OPTIMAL` status.
- Transportation, shortage-penalty, and service-penalty costs came directly
  from solved expressions.
- Their sum matched the reported post-tie-break recourse cost.
- The economic-band delta remained within the per-block tie-break tolerance and
  LP numerical tolerance.
- A second `resume-pilot` invocation accepted the intact checkpoint without
  resolving the model.
- Tests verify that a corrupt checkpoint or any identity mismatch is rejected.

## Resource observation

- Wall-clock runtime: approximately 0.10 seconds
- Peak process RSS: 29,437,952 bytes, approximately 28.1 MiB
- Scenarios materialized: 3
- Unique product-local blocks: 11
- Checkpoint size: approximately 8 KiB

This small pilot does not estimate full-run wall time linearly, but it confirms
that the serial block representation is far below the 32 GB memory limit. The
formal resource plan remains one case-policy task at a time.

## Test evidence

Targeted tests cover:

- strict equivalence to the existing full-scenario evaluator;
- immutable first-stage coordinates;
- deterministic repeated evaluation;
- direct cost-component reconciliation;
- common scenario manifest identity;
- `NA` rather than zero for invalid improvement denominators;
- distinct worst-shortage, worst-service-excess, worst-shortage-cost, and
  worst-economic-cost selectors;
- checkpoint corruption and identity mismatch rejection;
- absence of first-stage optimization call paths.

Relevant existing scenario, recourse, service, first-stage artifact, E2 protocol,
and E2 summary regression tests are also required before handoff.

## Manual confirmations required before formal authorization

1. Approve canonical `x0/y0` as a newly declared Nominal policy, acknowledging
   that it is the same first-stage configuration as Existing and not recovered
   E2 coordinates; or provide the original Nominal artifact.
2. Approve the later SCAL_BASE certified Robust solutions with their preserved
   lineage; or provide the original E1/E2 artifacts.
3. Decide whether the paper presents two unique configurations while retaining
   Nominal as a validation label.
4. Review the publication metrics and denominator/tie tolerances.
5. Create a separate authorization change setting only reviewed policies to
   `formal_authorized=true` and the formal manifest gate to true.

## Decision

**B. Only after human confirmation of the Nominal definition and Robust recovery
source may formal evaluation proceed.**
