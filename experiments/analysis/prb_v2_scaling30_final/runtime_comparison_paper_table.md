# Basic PRB versus Accelerated PRB V2 runtime comparison

## Same-environment paired Scaling30 results

| Scale | Pairs | Basic mean core time (s) | V2 mean core time (s) | Geometric mean paired speedup | Mean-time reduction | V2 wins |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| L10 | 10 | 28.422 | 8.468 | 3.293x | 70.2% | 10/10 |
| XL10 | 10 | 65.375 | 18.583 | 3.510x | 71.6% | 10/10 |
| XXL10 | 10 | 210.669 | 55.353 | 3.817x | 73.7% | 10/10 |

The ratio of mean times and the geometric mean of paired speedups are separately reported in `performance_summary_by_size.csv`; neither is substituted for the other.

## Descriptive XXL10 context across experiment batches

| Method | Experiment batch | Exact-certified samples used for mean | Mean core time (s) | Interpretation |
| --- | --- | ---: | ---: | --- |
| Direct | historical XXL10 four-method batch | 3/10 | 901.694 | Descriptive only; seven runs were limited. |
| EF-BD | historical XXL10 four-method batch | 10/10 | 342.668 | Descriptive only; not paired with V2 in the new batch. |
| Aggregate-BD | historical XXL10 four-method batch | 10/10 | 227.065 | Descriptive only; not paired with V2 in the new batch. |
| Basic PRB | new same-environment Scaling30 batch | 10/10 | 210.669 | Valid paired baseline for V2. |
| Accelerated PRB V2 | new same-environment Scaling30 batch | 9 strict + 1 numerical/10 | 55.353 | Valid under disclosed mixed certification classes. |

The historical PRB-BD mean was 143.340 s, whereas the new Basic PRB mean is 210.669 s. The historical value is retained as source context rather than repeated as a second Basic column because the execution batches and runtime environments are not proven identical. No cross-batch speedup is claimed.

Pure Benders remains a separate historical research method. It is not EF-BD and is not silently removed; its evidence boundary is documented in `docs/pure_benders_historical_comparison_audit.md`.
