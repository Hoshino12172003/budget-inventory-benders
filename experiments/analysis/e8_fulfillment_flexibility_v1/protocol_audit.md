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

All mode arc sets satisfy `k1 subset k2 subset Full`. Six cases have exactly two eligible inventory-positive depots per region-product and therefore `k2 == Full`: 210129, 210202, 210323, 210330, 210428, and 210628. Only 210310 and 210611 identify an incremental `Full` effect beyond `k2`. This fact must be disclosed rather than interpreted as a universal absence of value from additional sourcing flexibility.

Case 210611 contains one disabled-depot inventory coordinate of `6.91924636296832e-09`. The protocol treats values at or below `1e-8` as numerical noise for arc eligibility and does not alter the archived coordinate.

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

The paper-table aggregator requires all three formal mode results for a case, verifies all 4,657 scenario IDs and shock sets are identical, rederives every stored summary, checks `Full <= k2 <= k1`, and then emits only the nominal scenario and the Full-mode worst-economic-cost paired scenario. It refuses partial output and performs no interpolation.

## Decision

`READY_FOR_MANUAL_PILOT_AUTHORIZATION_WITH_QUALIFICATIONS`: the code and resource gates are safe for a separately authorized 210202/210628 pilot. Authorization is not granted here. Full publication remains conditional on the numerical Full-versus-E2 equivalence check and on explicit disclosure of the historical environment limitations.
