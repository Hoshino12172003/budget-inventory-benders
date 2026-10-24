# E1 empirical computational performance summary (historical derivative)

Evidence level: `HISTORICAL_SUMMARY_ONLY`

The eight original E1a PRB `result.json` files are unavailable and none of
their expected SHA-256 identities was recovered. The numerical values below
are retained unchanged for historical traceability, but the PRB runtimes,
iterations, cuts, speedups, and original certification labels are not primary
verified evidence and must not be used as confirmatory paper results. Later
development runs are reported separately as `DEVELOPMENT_CROSSCHECK` evidence
(7/8 strict PASS); they are not replacements for E1a.

This document was originally generated from 16 result directories. Only the
derived table remains available for the eight PRB rows. The historical values
are not recomputed here and no optimization was run.

The absence at issue is not an optional solver log: the eight PRB
`result.json` source records themselves are missing. Therefore the prior
completeness gate is withdrawn.

## Main results

| Case | I | Direct obj. | PRB obj. | Abs. diff. | Direct time (s) | PRB time (s) | Speedup |
|---|---:|---:|---:|---:|---:|---:|---:|
| 210202 | 15 | 1058780.7942496864 | 1058780.7942496866 | 2.328e-10 | 3.341000 | 1.233368 | 2.709 |
| 210628 | 15 | 676700.8373030961 | 676700.8373031134 | 1.735e-08 | 2.908000 | 1.242657 | 2.340 |
| 210129 | 15 | 851260.2478325500 | 851260.2478325500 | 0.000e+00 | 2.914000 | 1.168639 | 2.493 |
| 210310 | 16 | 714814.5477075904 | 714814.5477077012 | 1.108e-07 | 3.030000 | 1.347380 | 2.249 |
| 210330 | 11 | 657659.5492540546 | 657659.5492546142 | 5.596e-07 | 1.670000 | 0.983133 | 1.699 |
| 210323 | 13 | 627147.2289325034 | 627147.2289325014 | 1.979e-09 | 2.331000 | 1.014445 | 2.298 |
| 210428 | 18 | 793717.3880816699 | 793717.3880816748 | 4.889e-09 | 3.413000 | 1.492963 | 2.286 |
| 210611 | 19 | 617415.6681422364 | 617415.6681421611 | 7.532e-08 | 3.304000 | 1.742742 | 1.896 |


## Historical runtime and speedup (not confirmatory)

| Runtime statistic (s) | Direct | PRB |
|---|---:|---:|
| Arithmetic mean | 2.863875 | 1.278166 |
| Median | 2.972000 | 1.238013 |
| Geometric mean | 2.798851 | 1.257744 |
| Minimum | 1.670000 | 0.983133 |
| Maximum | 3.413000 | 1.742742 |
| Sample standard deviation | 0.593326 | 0.250319 |

| Speedup statistic | Direct/PRB ratio |
|---|---:|
| Arithmetic mean | 2.246210 |
| Median | 2.291933 |
| Geometric mean | 2.225295 |
| Minimum | 1.698651 |
| Maximum | 2.708844 |
| PRB wins | 8/8 |

The historical derivative reports PRB as faster in all 8 cases. This is not an
independently reproducible performance conclusion. It reports Direct mean and
median runtimes of
`2.863875` s and
`2.972000` s. PRB has mean and median
runtimes of `1.278166` s and
`1.238013` s. The geometric-mean speedup
is `2.225295`, with a range of
`1.698651` to
`2.708844`.

The maximum, mean, and median absolute objective differences are
`5.5960845202207565e-07`,
`9.6275471150875092e-08`, and
`1.1117663234472275e-08`.

## Historical PRB diagnostics (not confirmatory)

Iterations have mean `4.625`, median
`5.000`, and range
`4`–`5`.
Cuts have mean `32.500` and range
`31`–`34`.
Mean master solves and product-subproblem evaluations are
`4.625` and
`135.000`.
All four fields appear in the derivative summary, but their original source
records cannot now be inspected.

The 210330 row retains `global_coupling_pass=false` and classification
`DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH`. Its objective consistency and exact
recourse recertification pass, its Gamma allocation is feasible, and its
objective was historically reported as unaffected. A later development run
reproduces the objective but fails the strict coupling certification gate; the
case must not be described as an independently verified E1a PASS.

## Network-size description

For depot count I, Pearson correlations with Direct runtime, PRB runtime, and
speedup are `0.8892`,
`0.9580`, and
`0.1420`. Corresponding Spearman
correlations are `0.8051`,
`0.9759`, and
`-0.1220`. These are descriptive
associations from eight observations. They do not establish a scalability law
or support a general large-scale scalability claim. No hypothesis test was
performed.

## Superseded Chinese summary

历史汇总表记录了八个 Renault 算例的 PRB-Benders 目标值和运行时间，但对应的八个原始 `result.json` 已无法恢复，因此这些运行时间、迭代次数、割数和加速比仅作为 `HISTORICAL_SUMMARY_ONLY` 保存，不能作为可独立复核的正式性能结论。后续开发批次在相同实例身份下复现了 8/8 个目标值，其中 7/8 通过严格认证，210330 未通过全局风险预算耦合检查；该批次属于 `DEVELOPMENT_CROSSCHECK`，不能替代原 E1a 正式运行。

No confirmatory Renault E1a runtime-advantage claim is retained. Independent
Scaling V2 and XXL10 results are assessed under their own source-complete
evidence chains.
