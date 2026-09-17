# E1 empirical computational performance summary

All 16 paper-final result directories were read from `RENAULT_EMPIRICAL_8CASE_V1`.
The summary uses the persisted `runtime_seconds` field and does not rerun an
optimization. All eight paired objective differences pass the frozen `1e-4`
consistency tolerance, and no run is resource-limited.

Direct solver logs are present for 8/8 Direct runs. PRB solver logs are not
recorded because the PRB runner does not create a separate solver log; its
certification, iteration, cut, bound, and runtime diagnostics are persisted in
`result.json`. This missing optional log does not affect the completeness gate.

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


## Aggregate runtime and speedup

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

PRB is faster in all 8 cases. Direct has mean and median runtimes of
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

## PRB diagnostics

Iterations have mean `4.625`, median
`5.000`, and range
`4`–`5`.
Cuts have mean `32.500` and range
`31`–`34`.
Mean master solves and product-subproblem evaluations are
`4.625` and
`135.000`.
All four fields were recorded for 8/8 PRB runs.

The 210330 row retains `global_coupling_pass=false` and classification
`DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH`. Its objective consistency and exact
recourse recertification pass, its Gamma allocation is feasible, and its
objective is unaffected. It remains in the performance summary as an optimal
paper-final run.

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

## Paper-ready Chinese summary

在八个具有异质网络结构的 Renault 实证算例上，PRB-Benders 与 Direct 精确模型的目标值均在冻结的 `1e-4` 容差内一致，最大绝对差为 `5.596e-07`。PRB-Benders 在 8/8 个算例中缩短了计算时间：Direct 的平均和中位运行时间分别为 `2.864` 秒和 `2.972` 秒，PRB-Benders 分别为 `1.278` 秒和 `1.238` 秒。Direct/PRB 运行时间比的几何平均为 `2.225`，范围为 `1.699`–`2.709`。210330 的 global-coupling 标志源于不影响目标值、可行性或 Gamma 分配的数值诊断契约差异，因此不改变性能比较结论。现有证据支持 PRB-Benders 在这些异质实证算例上取得一致的计算收益，但不构成一般性的大规模可扩展性结论。

The evidence supports consistent computational gains across heterogeneous
empirical instances, not a general large-scale scalability claim.
