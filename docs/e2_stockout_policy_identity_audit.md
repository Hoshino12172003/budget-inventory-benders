# E2 stockout policy identity audit

## Decision

The policy freeze is **partial** and the formal-run decision is **B**: formal
evaluation may proceed only after a human confirms the canonical Nominal policy
definition and the proposed Robust recovery lineage. No policy is authorized for
formal stockout evaluation by this audit.

The machine-readable source of truth is
`artifacts/e2_stockout_policy_identity_manifest.json`. Its payload hash covers
all policy entries and authorization flags.

## Recovery search

The repository and its containing `paper-code2` directory were searched for the
24 ignored E2 run directories, original E2 Nominal coordinates, original E1 PRB
solution artifacts, and plausible E1/E2 archives. None were found. The original
locations remain absent:

- `experiments/results/e2_existing_nominal_robust_v1/`
- `experiments/results/e1_empirical_8case_v1/`

Both paths are intentionally ignored by `.gitignore`, so the current Git history
cannot restore them. The retained E2 evidence is aggregate-only:
`artifacts/e2_policy_contrast_summary.csv` and the interpretation audit.

## Existing policy

For every case, Existing is recovered from the original canonical incumbent
artifact:

`artifacts/renault_empirical_8case_v1/x0/<case>.json`

The artifact contains the complete `x0` matrix, `y0`, instance hash, canonical
rule, solver profile, and canonical objective. For the evaluation identity,
`a_plus=a_minus=0` by the Existing policy definition. The manifest hashes the
canonical `{y,x,a_plus,a_minus}` payload; it does not infer any missing value.

All eight x0 artifacts match their frozen instance identities. Their companion
`stability/<case>.json` records `canonical_incumbent_status=PASS` and
`status=PASS`. Existing is the only policy authorized for the pilot.

## Nominal policy

No original E2 Nominal coordinate artifact was recovered. The E2 aggregate audit
shows no material Nominal reconfiguration and objective agreement with Existing,
but aggregate agreement cannot reconstruct solver coordinates.

The manifest therefore records a candidate policy named
`NOMINAL_CANONICAL_REDECLARED_<case>` with lineage:

`REDECLARED_CANONICAL_POLICY_NOT_RECOVERED_E2_COORDINATES`

This candidate uses the formally defined canonical Gamma=0 incumbent `x0/y0`.
Its coordinate hash is exactly equal to the corresponding Existing coordinate
hash. It is the same first-stage configuration, not a distinct configuration.
Both policy labels remain visible so that no policy is silently deleted.

Human decision required:

1. Approve canonical `x0/y0` as the prospective Nominal policy definition and
   present the scientific comparison as two distinct configurations
   (canonical baseline versus Robust), while retaining the Nominal label as a
   validation identity; or
2. supply the original E2 Nominal coordinates and provenance.

The audit recommends option 1 because `x0` is formally defined as the canonical
Gamma=0 nominal optimum. This is a new policy declaration, not recovery of the
lost E2 solver incumbent. Under that declaration, Nominal is a validation label
for the Baseline coordinates and is not counted as a separate configuration.

## Robust policy

No original E1/E2 Robust solution artifact was recovered. Each
`SERVICE_CALIBRATION_ROBUSTNESS_V2/SCAL_BASE_<case>` directory does contain:

- a complete `first_stage_solution.json` with `y/x/a_plus/a_minus`;
- a result with `solver_status=OPTIMAL` and
  `optimality_certification=CERTIFIED_PRB_EXACT`;
- provenance hashes for the result, first-stage solution, and scenario archive.

The candidate lineage is explicitly frozen as:

`SUBSEQUENT_NUMERICALLY_EQUIVALENT_SOLUTION_NOT_ORIGINAL_E1_E2`

The candidates match the frozen instance hashes and the retained E2 Robust
objective, RI, and RS aggregates within `1e-6`. This supports numerical
equivalence but does not change their lineage into original E1/E2 artifacts.

For every candidate the manifest additionally verifies the SHA-256 link from
`provenance.json` to both `result.json` and `first_stage_solution.json`, checks
the instance hash, and requires `solver_status=OPTIMAL` plus
`optimality_certification=CERTIFIED_PRB_EXACT`. These facts certify the later
SCAL_BASE solution. They do not certify recovery of the historical E2 file.

Human decision required: approve these later, certified solutions as the fixed
Robust policies for a new supplemental evaluation, or provide the original E1/E2
solution artifacts.

## Certification interpretation

- E2 authorization and an E2 `OPTIMAL` aggregate are not treated as a coordinate
  certificate.
- Missing Nominal certification fields are not filled with `OPTIMAL` or zero.
- SCAL_BASE certificates are attributed only to the later SCAL_BASE runs.
- `formal_authorized=false` for all 24 policy identities.
- Existing pilot authorization is not formal-run authorization.

## Cases and source classes

The audit covers `210129`, `210202`, `210310`, `210323`, `210330`, `210428`,
`210611`, and `210628`. Exact source paths, source-run IDs, instance hashes,
file hashes, coordinate hashes, solver status, certification, E2 aggregate
consistency, and configuration groups are recorded per entry in the identity
manifest.

## Stop condition

The full common-scenario evaluation must not start while the manifest remains
`PARTIAL_REQUIRES_HUMAN_CONFIRMATION` or while any selected policy has
`formal_authorized=false`.
