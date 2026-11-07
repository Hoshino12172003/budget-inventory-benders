# E8 ex-post fulfillment flexibility: pre-execution audit

## Status

The E8 implementation is statically prepared, but both pilot and formal authorization remain `false`. No E8 Gurobi optimization has been run and no E8 result directory exists.

## Frozen scientific comparison

- Experiment: `E8_EX_POST_FULFILLMENT_FLEXIBILITY_V1`.
- Cases: the eight frozen `RENAULT_EMPIRICAL_8CASE_V1` instances.
- Fixed policy: the certified E1 PRB `y*` and `x*`; E8 contains no first-stage optimization path.
- Common parameters: `Gamma=2`, `beta=1.0`, `lambda_R=0.05`, `SL=0.90`, and `kappa_phi=1.85`.
- Modes: `k1`, `k2`, and `Full`; eligible arcs are selected once before scenario evaluation by transport cost and then depot ID.
- Recourse objective: transportation, shortage penalty, and soft-service penalty. Reporting uses the existing cost-optimal-face squared-shortage tie-break with frozen tolerance `1e-7`.
- Scenarios: all 4,657 binary region-product shock sets with up to two active shocks, in one common canonical order.

The evaluator reports the worst economic cost, maximum total shortage, minimum worst-region fill rate, maximum service violation, and maximum shortage penalty separately. It does not infer one extreme from another.

## Product-block equivalence basis

The recourse model has product-specific inventory constraints, product-specific service constraints and additive costs. Demand shocks are binary region-product components with a global cardinality budget. E8 therefore solves all 79 local shock subsets of size 0, 1 or 2 for each product, then recomposes the exact global scenario list. No decision or constraint couples two products in the fixed-policy recourse model. The same cost-optimal-face reporting rule is applied within every local block.

This is a structural proof for the implementation, not a numerical claim. The future `Full` pilot must additionally match the archived E2 ROBUST recourse value within the predeclared `1e-4` tolerance; failure blocks result publication.

## Arc audit and interpretation boundary

All mode arc sets satisfy `k1 subset k2 subset Full`. Across all eight frozen policies, 72 of 96 region-product pairs have **zero** eligible stocked depots; only the remaining 24 pairs (two stocked products across 12 regions) can distinguish fulfillment modes. In six cases the 24 stocked pairs each have exactly two eligible depots and `k2 == Full`: 210129, 210202, 210323, 210330, 210428, and 210628. The two stocked products in 210310 have 3 and 4 eligible depots; those in 210611 have 4 and 5. Strictly more available arcs alone does not establish an economic or service improvement. Case-level arc counts are in `input_identity_audit.json`.

Case 210611 contains one disabled-depot inventory coordinate of `6.91924636296832e-09`. The protocol treats values at or below `1e-8` as numerical noise for arc eligibility and does not alter the archived coordinate.

## Historical E1 certification qualification

All eight archived E1 PRB results carry `OPTIMAL / CERTIFIED_PRB_EXACT`, but only seven have `global_coupling_pass=true`. Case 210330 has `global_coupling_pass=false` and is retained as a fixed-inventory diagnostic sample, not re-certified as strictly first-stage optimal. Final paper summaries must include all eight and a seven-case exclusion sensitivity. Full-versus-E2 recourse equality does not remedy the historical flag.

## Pilot design and formal coverage

Pilot candidates are 210202, 210628, and 210310, each in k1/k2/Full. The first two test k1-to-k2 while k2 and Full are identical; 210310 can test strictly additional Full arcs. All eight cases and 24 conditions remain in formal scope. Pilot results do not automatically count as formal results. Both authorizations remain false.

## Resource preflight

Execution is serial by case and mode, with eight sequential product models and `Threads=1`. A product has 79 local shock blocks. The largest static model estimate is 5,767 variables and 2,528 primary constraints. The process-tree cap is 6 GiB, the system memory floor is 4 GiB, and the pilot timeout is 900 seconds. A parent monitor records wall time and peak process-tree RSS and terminates on a frozen resource threshold.

The full experiment consists of 24 case-mode conditions. If authorized later, each condition uses 8 product models and two optimization phases per product. This pre-execution task made zero optimization calls.

## Environment qualification

The current machine matches the E8 target: Windows 11, Python 3.12.7, Gurobi/gurobipy 13.0.1, 31.50 GiB RAM, and the formal `gurobi-balanced-1e-8-v1` profile. Archived E1 records identify Gurobi 13.0.2, while historical Python and Gurobi Threads are not recorded. Consequently, strict historical environment identity cannot be claimed. E8's three modes are internally comparable because their environment and resources are explicitly common.

## Regression evidence

- E8 targeted tests: 9 passed.
- Scoped no-optimization regression: 31 passed, 1 failed.
- The failure is `tests/test_e2_protocol.py::test_e2_identity_and_reuse_contract`. Baseline commit `b4d20773d5f90892bed44f86b595f480335fd5b3` already contains runner blob SHA-256 `23db440e...`; the historical manifest expects `0ba3e006...`, the blob at commit `4b154729...`. The current Windows working-tree byte hash is `dd296522...` because line endings also differ. E8 did not modify either historical file.
- Classification: `HISTORICAL_FREEZE_MISMATCH`, not a newly introduced E8 regression. It prevents a claim of exact replay from the current E2 runner, but does not replace the independently hashed archived E1/E2 result inputs used by E8.

## Publication and execution gates

Formal or pilot execution requires a separate manual authorization, an authorized run ID, an authorized code commit that is an ancestor of HEAD, a clean tracked worktree, strict current-environment checks, and all frozen input/source hashes. Checkpoints bind the complete condition identity and product index. Existing or partial results are never overwritten.

The paper-table aggregator requires complete identity-verified formal results for all eight cases, checks all 4,657 scenario identities and `Full <= k2 <= k1`, emits nominal and Full-mode worst-economic-cost paired scenario rows, and creates an all-eight versus exclude-210330 seven-case descriptive sensitivity summary. It refuses partial output and does not claim statistical significance.

## Decision

`READY_FOR_MANUAL_PILOT_AUTHORIZATION_WITH_QUALIFICATIONS`: the code and resource gates are prepared for a separately authorized 210202/210628/210310 pilot, with the historical qualification disclosed. Authorization is not granted here. Full publication remains conditional on the numerical Full-versus-E2 equivalence check and on explicit disclosure of the historical environment limitations.
