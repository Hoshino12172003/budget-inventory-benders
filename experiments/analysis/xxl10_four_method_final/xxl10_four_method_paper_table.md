# XXL10 four-method computational comparison

| method | scheduled_n | executed_n | exact_certified_n | exact_certification_rate | time_or_monitor_limited_n | mean_core_time_certified_seconds |
| --- | --- | --- | --- | --- | --- | --- |
| Direct | 10 | 10 | 3 | 0.3 | 7 | 901.694 |
| EF-BD | 10 | 10 | 10 | 1 | 0 | 342.668 |
| Aggregate-BD | 10 | 10 | 10 | 1 | 0 | 227.065 |
| PRB-BD | 10 | 10 | 10 | 1 | 0 | 143.34 |

Notes:

- Direct has 3/10 exact-certified results. Its seven limited runs remain in the fixed denominator but are excluded from ordinary exact-pair speedups.
- `DIRECT_XXL10_S20260922` remains in the historical batch report as `STOPPED_INTEGRITY_FAILURE`; the independent read-only audit classifies the preserved evidence as `TIME_LIMIT_NO_INCUMBENT`.
- `DIRECT_XXL10_S20260927` ended at the outer monitor hard limit with Worker return code 15. No solver objective, bound, gap, or final solver status is inferred.
- EF-BD, Aggregate-BD, and PRB-BD have 10/10 exact-certified results. Timing comparisons against Direct use only the three jointly exact-certified seeds.
- Scaling V2 historical solver version remains not fully verifiable; Direct and EF-BD were recorded with Python 3.12.7 and Gurobi 13.0.1.

## Paired comparisons

| baseline | comparator | paired_n | geometric_mean_baseline_over_comparator | comparator_wins | baseline_wins | ties | wilcoxon_statistic | wilcoxon_two_sided_p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direct | EF-BD | 3 | 2.56225 | 3 | 0 | 0 | 0 | 0.25 |
| Direct | Aggregate-BD | 3 | 3.90867 | 3 | 0 | 0 | 0 | 0.25 |
| Direct | PRB-BD | 3 | 6.29901 | 3 | 0 | 0 | 0 | 0.25 |
| EF-BD | Aggregate-BD | 10 | 1.50327 | 10 | 0 | 0 | 0 | 0.00195312 |
| EF-BD | PRB-BD | 10 | 2.37532 | 10 | 0 | 0 | 0 | 0.00195312 |
| Aggregate-BD | PRB-BD | 10 | 1.58011 | 10 | 0 | 0 | 0 | 0.00195312 |
