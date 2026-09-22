# PRB original bottleneck validation

## Decision

- Question A, global oracle bottleneck with increasing product dimension: `EVIDENCE_INSUFFICIENT`.
- Question B, product-level master/cuts versus aggregate master: `SUPPORTED`.
- Overall: `PRB_MASTER_BENEFIT_ONLY`.

The negative/insufficient oracle conclusion is not a claim that a global oracle can never become difficult. It states that the exact-certified range observed here does not show that mechanism, while the larger predeclared points fail before a valid relative timing comparison can be made.

## Existing exact evidence

All eight Renault cases and both frozen E1c L/XL-low probes are objective-consistent and exact-certified. Across the eight empirical cases, Aggregate-Structured takes 3.27--5.20 times the Pure total time, and its structured-oracle time is 3.82--10.39 times the Pure global-oracle time. At L those ratios are 35.74 and 69.36; at XL-low they are 50.55 and 127.39. Thus the product-decomposed oracle is more expensive, not less expensive, over every previously certified comparison.

PRB is faster than Aggregate-Structured in all ten comparisons. PRB/Aggregate total-time ratios range from 0.73 to 0.91. Aggregate needs 7--10 iterations, while PRB needs 4--6. PRB adds more individual product-budget cuts, so the benefit is fewer structured refinement rounds and a stronger information layout, not a smaller cut count or a lower measured master optimize time in every row.

Lower-bound trajectories and per-round gaps were not persisted for the eight empirical or L/XL-low artifacts. Those fields are `NOT_RECORDED`; the audit does not reconstruct them.

## Predeclared J-only development validation

The frozen design uses I=25, R=24, Gamma=2, seed 20260911 and J in {12,24,48,96}. Each product has

\[
1+R+\binom{R}{2}=1+24+276=301
\]

local patterns. Product-risk blocks therefore grow linearly as 3,612, 7,224, 14,448 and 28,896. Pure global uncertainty binaries grow as 288, 576, 1,152 and 2,304.

| J | Pure | Aggregate-Structured | PRB | Exactness use |
|---:|---|---|---|---|
| 12 | OPTIMAL, certified, 0.785389 s | OPTIMAL, certified, 25.516722 s | OPTIMAL, certified, 23.143570 s | PASS; max objective difference 4.66e-10 |
| 24 | zero-gap objective in 2.457489 s, certification false | TIME_LIMIT at 900.354 s | TIME_LIMIT at 900.186 s | NOT ELIGIBLE |
| 48 | master status SUBOPTIMAL after 11.082 s | TIME_LIMIT at 900.948 s | TIME_LIMIT at 900.112 s | NOT ELIGIBLE |
| 96 | no method run; canonical Gamma=0 x0 preparation numerical failure | no method run | no method run | NOT ELIGIBLE |

At J=12 the structured/Pure oracle-time ratio is 64.86 and the Aggregate/Pure total-time ratio is 32.49. PRB is 9.30% faster than Aggregate, using six rather than seven iterations. The J=24 and J=48 timeouts show a real structured-block workload escalation, but the absent exact three-method comparison means they cannot establish an oracle speed ratio. J=96 remains a predeclared blocked point rather than a post-result grid deletion.

## Interpretation of the two difficulties

### A. Global worst-case oracle

The previously certified empirical/L/XL-low evidence and the new certified J=12 point all show the global adversarial MILP to be substantially cheaper than the product-pattern oracle. The larger J points contain timeout/noncertification/preparation failures, which the preregistered rule classifies as insufficient evidence rather than a speed win. Accordingly, `GLOBAL_ORACLE_BOTTLENECK_SUPPORTED` is not established.

### B. Aggregate master refinement

Aggregate-Structured and PRB share the product-risk oracle family. PRB is faster at every one of the ten prior exact comparisons and at the new exact J=12 point, with fewer iterations. The L-to-XL-low advantage does not disappear: PRB/Aggregate total time moves from 0.83 to 0.73. The evidence therefore supports a product-level master/refinement benefit in the tested regime.

The benefit should be described narrowly. Master `optimize()` time itself is small for both methods. Most total time is oracle construction/evaluation and unallocated structured orchestration. The supported mechanism is fewer full structured refinement rounds and more informative product-budget cuts, not that the PRB master is intrinsically cheaper per solve.

## Resource and correctness audit

No formal optimization was run. Nine development method conditions were invoked: three at each of J=12,24,48. Only the three J=12 conditions are exact-certified and eligible for speed conclusions. J=96 had zero method invocations. Nine preparation attempts were recorded because the large canonical baseline required retained numerical-recovery attempts; none is a paper-final observation. No memory stop occurred. Peak process-tree memory was 1.815 GiB at J=12, 3.282 GiB for the J=24 Structured timeout, and 6.497 GiB for the J=48 Structured timeout, below the 14 GiB hard stop.

All artifacts are development-only and excluded from formal reporting. Solver/model/cut/timeout/resource settings were not tuned after observing method outcomes.

