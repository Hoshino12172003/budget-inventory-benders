# A5 unified Gamma=2 evaluation audit

## Recovery identity

Recovery attempt 002 reran only A3, A4, and A5 for case 210202. Each recovered
objective exactly equals its immutable acceptance value within the frozen
`1e-4` tolerance. The original attempt 001 hash tree was identical before and
after recovery. Each new first-stage artifact contains 120 canonically indexed
and finite entries for each of `x`, `a_plus`, and `a_minus`, plus 15 depot
activation entries.

The recovered A3 and A4 decisions are numerically the incumbent configuration:
`max|x_A3-x0|=0`, `max|x_A4-x0|=1.1070255823142361e-11`, and
`max|x_A4-x_A3|=1.1070255823142361e-11`. This is recorded as
`NOMINAL_RECONFIGURATION_INACTIVE_AT_BASELINE`. A5 differs from `x0` by at most
`26.202808848136925` in one coordinate and has RI
`0.020913487972572833`.

## Unified evaluator

All three persisted decisions were loaded from disk and evaluated without a
new first-stage optimization. The same frozen exact evaluator, formal demand
deviations, recourse model, costs, and solver profile were used with `Gamma=2`.
The 12 regions and 8 products define 96 uncertain items and 4,657 binary-budget
extreme scenarios.

| Solution | Worst recourse | Worst total shortage | FR_min | Average fill in minimum-FR scenario | Total inventory | RI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A3 | 33184.482045254714 | 523.5024775260686 | 0.7177949087395694 | 0.9764829090616308 | 5776.468951048719 | 0 |
| A4 | 33184.48204525425 | 523.5024775263972 | 0.7177949087397539 | 0.9764829090616461 | 5776.468951048715 | 3.1575746674186425e-15 |
| A5 | 32261.04063060048 | 530.7456659951423 | 0.713874373711431 | 0.9761561978092859 | 5773.133253665497 | 0.020913487972572833 |

A3 and A4 share economic worst shocks `(1, SLI---0770)` and
`(8, BAC-O-4312)`. A5's economic worst shocks are `(8, BAC-O-4312)` and
`(12, BAC---1041)`. For all three decisions, the scenario-region pair producing
the minimum fill-rate diagnostic instead uses shocks `(1, BAC-O-6433)` and
`(12, BAC---1041)`, with worst region 12. Thus the economic-worst and
service-worst scenario identities are not interchangeable.

Transportation, shortage-cost, and soft-service-penalty breakdowns are reported
for each economic-worst scenario in
`table_a5_common_evaluation.csv`. A worst product is reported as `NA` because
the frozen fill-rate metric aggregates products at the region level and does
not define a canonical worst-product statistic.

## Common-scenario evidence

Under the shared A3/A4 economic-worst scenario, A5 recourse is
`32149.772164505033`, below the A3/A4 values near `33184.4820452545`. Under the
A5 economic-worst scenario, A5 recourse is `32261.04063060048`, below the A3/A4
values near `32810.5254787145`. In both comparisons A5 can have a lower regional
fill-rate even while it has lower economic recourse cost. The full nine-row
cross-evaluation is stored in
`table_a5_common_scenario_cross_evaluation.csv`.

## Conclusion

`A5_RESULT_VALID_METRIC_TRADEOFF`

The original visual anomaly partly reflected incomparable evaluation sets:
A3/A4 were originally reported at nominal `Gamma=0`, while A5 was reported at
`Gamma=2`. Under a common Gamma=2 evaluation, A5 lowers worst-case economic
recourse exposure by about `923.44` relative to A3/A4, as its robust objective
requires. It nevertheless has a slightly lower minimum regional fill rate and
a higher worst total shortage. This is not a model/evaluator inconsistency:
`FR_min` is a post-evaluation diagnostic, not the optimization objective.
Claims that robust reconfiguration necessarily improves minimum fill rate are
therefore unsupported by this model.

E1 and E2-E7 formal execution remain unauthorized.
