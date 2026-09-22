# E1 formal algorithm benchmark report

## Status

`BLOCK_E1_SYNTHETIC_REPRODUCIBILITY`

The Renault portion is complete and objective-consistent. The full E1 benchmark
is not complete because the repository's synthetic ladder is explicitly
`DESIGN_ONLY`: dimensions and a seed exist, but no formal generator version or
frozen rules for `x0`, costs, budget, uncertainty ranges, disk guard, and timeout
exist. No synthetic instance was invented and none of the eight synthetic runs
was executed.

Attempt 001 failed before any optimization because a historical reporting CSV
column was read as `lambda_R` instead of `lambda_r`. Its failure artifacts are
preserved. Attempt 002 performed exactly two new solves.

## Certified Renault results

| Instance | Method | Objective | Runtime (s) | Status | Origin |
| --- | --- | ---: | ---: | --- | --- |
| 210202 | Direct | 116875.3457619544 | 8.680999994277954 | CERTIFIED_EXACT | formal acceptance reuse |
| 210202 | PRB | 116875.34576195436 | 2.2748046000488102 | CERTIFIED_PRB_EXACT | formal acceptance reuse |
| 210628 | Direct | 81468.15564321939 | 10.815999984741211 | CERTIFIED_EXACT | E1 attempt 002 |
| 210628 | PRB | 81468.15564321943 | 3.2355355999898165 | CERTIFIED_PRB_EXACT | E1 attempt 002 |

The absolute objective difference is `4.3655745685100555e-11` for both pairs,
well below the frozen `1e-4` threshold. Runtime ratios Direct/PRB are
`3.8161519429368513` for 210202 and `3.342877755625762` for 210628. These two
Renault observations do not establish a general scale crossover.

Both Direct models use the factorized exact product-pattern formulation with
122,376 variables, 18,629 constraints, 376,923 nonzeros, 15 integer variables,
122,361 continuous variables, and 632 represented product-pattern blocks. The
210628 Direct solve used one node. The reused 210202 node count was not captured
in the acceptance schema.

PRB used 11 master solves and 114 unique product cuts for 210202. It used 14
master solves, 112 unique cuts, and 360 recorded product-subproblem evaluations
for 210628. The reused acceptance row did not record its product-subproblem
count. A separate global-coupling runtime was not measured for either row; an
immutable reporting correction records that the reused certification runtime
must not be relabeled as this metric.

Reliable process-level peak memory was not implemented and is reported as
`null`, in accordance with the frozen metric definition. No time, memory, or
other resource-limit event occurred in the four completed Renault observations.

## Interpretation limits

The completed evidence confirms Direct/PRB exactness and certification on both
formal Renault cases. It does not answer decomposition overhead at Small,
runtime growth across the synthetic ladder, a scale crossover, or Large-scale
memory advantage. Those questions remain blocked until a separately reviewed
formal synthetic generator and resource contract are frozen.

The A5 service-metric trade-off is outside E1 and is not reinterpreted here.
E2 must use a unified Gamma-based post-evaluation for Existing, Nominal, and
Robust decisions.

E2-E7 formal execution remains unauthorized.
