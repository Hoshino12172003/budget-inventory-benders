# Renault real-case paired PRB performance

Core time is the algorithm-reported `total_runtime`. V2 uses two process workers; Basic is serial. Each Gurobi model uses one thread.

| Case | Depots | Basic PRB (s) | Accelerated PRB V2 (s) | Basic/V2 | Basic iter. | V2 iter. | Basic cert. | V2 cert. |
|---:|---:|---:|---:|---:|---:|---:|:---|:---|
| 210202 | 15 | 2.143 | 1.839 | 1.165x | 4 | 4 | strict_original | strict_original |
| 210628 | 15 | 2.070 | 1.893 | 1.094x | 5 | 5 | strict_original | strict_original |
| 210129 | 15 | 1.896 | 1.815 | 1.045x | 4 | 4 | strict_original | strict_original |
| 210310 | 16 | 2.283 | 1.882 | 1.213x | 5 | 5 | strict_original | strict_original |
| 210330 | 11 | 1.549 | 1.668 | 0.929x | 5 | 5 | independently_numerically_validated | independently_numerically_validated |
| 210323 | 13 | 1.519 | 1.782 | 0.852x | 4 | 4 | strict_original | strict_original |
| 210428 | 18 | 2.551 | 1.976 | 1.291x | 5 | 5 | strict_original | strict_original |
| 210611 | 19 | 2.734 | 2.118 | 1.291x | 5 | 5 | strict_original | strict_original |

Arithmetic mean core times: Basic 2.093 s, V2 1.872 s. Paired geometric-mean speedup: 1.099x. V2 wins: 6/8.

The two 210330 runs are not strict-original successes. Both retain the original global-coupling failure and are separately labelled `independently_numerically_validated`; this is not an exact-arithmetic proof.
