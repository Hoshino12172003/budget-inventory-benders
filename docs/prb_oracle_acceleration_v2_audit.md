# Accelerated PRB V2 runtime and correctness audit

This development-only audit changes no model, tolerance, uncertainty, cut, or certification contract.

## V1 bottleneck

On profiled XL-low, the 9.762 s core time consisted primarily of 3.354 s product-model construction, 0.982 s worker startup, 3.756 s main separation, 0.924 s repeated final certification, and 0.606 s master construction. IPC, serialization, cut management, LB/UB accounting, and Gamma DP were individually below 0.04 s.

## V2 changes

- exact recursive allocation generation replaces Cartesian filtering while preserving tuple order;
- final certification reuses only bitwise-identical cached product states;
- worker selection uses product-risk block count, not case identity (2 workers at <=1000 blocks, otherwise up to 8);
- workers retain static data and persistent Gurobi models; only x_j is sent per iteration;
- unused shipment primal matrices are no longer serialized; cost values and duals are batch-read;
- no heuristic selective separation is used.

## Fair repeated runtime benchmark

| Case | Pure median | Original PRB median | V1 median | V2 median | V2/Pure | V2/V1 |
|---|---:|---:|---:|---:|---:|---:|
| 210202 | 0.407s | 1.478s | 1.774s | 1.038s | 2.55x | 0.585 |
| L | 0.817s | 25.435s | 4.317s | 3.230s | 3.96x | 0.748 |
| XL_low | 1.610s | 65.737s | 9.634s | 6.583s | 4.09x | 0.683 |

Each cell uses two same-machine exact observations and reports median, with min, max, mean, and sample standard deviation in the CSV artifact. No fastest-run selection is used.

## Correctness and interpretation

Both V2 repetitions pass objective, recourse, first-stage identity/equivalence, exact certification, and global Gamma-coupling checks on all three instances. Certification duplicate state solves fall from 24/36/42 to zero for 210202/L/XL-low. V2 remains more than 1.5x slower than Pure on every tested instance, so the frozen conclusion is `MAJOR_GAIN_BUT_PURE_STILL_FASTER`. No eight-case expansion is authorized.

E2--E7 reruns: 0. Paper text changed: no.
