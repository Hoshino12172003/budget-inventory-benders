# PRB oracle acceleration audit

## Scope and invariants

This is a development-only implementation audit. It does not change the
mathematical model, uncertainty set, PRB master, product cut definition,
termination tolerances, or exact certification contract. Original PRB remains
available through `solve_prb_benders`; the new entry point is
`solve_accelerated_prb_benders`.

No E2--E7 result was rerun or overwritten.

## Original call flow and bottleneck

At each PRB iteration, Original PRB:

1. solves the PRB master;
2. loops serially over products;
3. updates the supply RHS in one `ProductRiskSubproblem` per product;
4. solves the product LP containing every exact shock-pattern block for local
   risk budgets `0..Gamma`;
5. enumerates global Gamma allocations and adds every violated product cut;
6. repeats the same serial product loop for final exact certification.

The dominant routine is `ProductRiskSubproblem.solve`, together with building
its replicated scenario blocks. On frozen XL-low, Original PRB used 33.396 s
in the product oracle and 65.094 s core time despite only six PRB iterations.

## Accelerated implementation

- **Product parallelism:** eight persistent worker processes own disjoint
  products. Each product model uses an independent Gurobi environment and
  `Threads=1`, preventing nested thread oversubscription.
- **Exact cache:** the key is `(product id, exact normalized Python-float x_j
  tuple)`. There is no rounding or proximity match. A changed coordinate is a
  cache miss.
- **Warm start:** every worker retains its product LP. Gurobi LP basis reuse is
  enabled with `LPWarmStart=2`; failure falls back to the unchanged exact solve
  path by raising rather than accepting an approximate value.
- **Gamma composition:** Accelerated PRB uses an exact dynamic program over the
  same integer allocation set instead of materializing `(Gamma+1)^J` tuples.
- **Selective separation:** not implemented. No state is heuristically skipped.
  Before termination, all product-risk states are re-solved with cache disabled.

The first compact-LP prototype and the four-worker block prototype are retained
locally as development evidence. The final eight-worker block implementation is
the reported candidate.

## Correctness

All three instances pass independent first-stage feasibility, exact final
recourse certification, and global Gamma-coupling checks. Accelerated PRB has
the same iteration and cut counts as Original PRB. The saved first-stage
solutions are identical within `1e-5`; the largest observed coordinate
difference is `5.68e-14` on XL-low.

| Instance | Objective difference | Recourse difference | Same y | Max x difference | Certification |
|---|---:|---:|:---:|---:|:---:|
| 210202 | 0 | 1.16e-10 | yes | 0 | PASS |
| L | 0 | 0 | yes | 0 | PASS |
| XL-low | 1.86e-9 | 1.86e-9 | yes | 5.68e-14 | PASS |

## Development performance

| Instance | Original core | Accelerated core | Core reduction | Original oracle | Accelerated oracle | Oracle reduction |
|---|---:|---:|---:|---:|---:|---:|
| 210202 | 1.233 s | 1.781 s | -44.4% | 0.500 s | 0.100 s | 80.1% |
| L | 22.587 s | 4.192 s | 81.4% | 11.597 s | 1.487 s | 87.2% |
| XL-low | 65.094 s | 9.506 s | 85.4% | 33.396 s | 3.648 s | 89.1% |

The small 210202 instance exposes process-start and parallel model-build
overhead, so Accelerated PRB is slower in total there even though its oracle
phase is faster. On XL-low, peak monitored process-tree memory was 4.99 GiB.
The remaining XL-low cost is primarily product-model construction (4.26 s),
separation (3.65 s), and certification (0.95 s).

Exact cache reuse avoided 54, 150, and 165 product-risk state solves on 210202,
L, and XL-low respectively. Warm starts were used 14, 22, and 29 times.

## Interpretation and next action

The development target of reducing XL-low below 10 seconds was met without an
exactness loss. This is `ACCELERATION_SUCCESS` for the requested oracle-side
development round. It is not evidence that Accelerated PRB is faster than Pure
Benders: Accelerated PRB remains 4.26x, 5.53x, and 5.42x slower on 210202, L,
and XL-low. The implementation should therefore receive additional small-case
overhead work and broader development validation before replacing any
paper-final performance implementation. An eight-case expansion is not yet
recommended, and no management experiment needs to be rerun because all
mathematical outputs and frozen contracts are unchanged.
