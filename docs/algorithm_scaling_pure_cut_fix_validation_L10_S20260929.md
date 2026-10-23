# Pure Benders previous-cut guard fix validation

The semantic fix changes only the separation residual from certified primal
recourse minus theta to dual cut RHS minus theta. Certified upper bounds continue
to use the certified primal value.

Targeted tests passed before the formal-condition validation. Only
`ASC_L10_S20260929_PURE_BENDERS` was then executed, using an isolated validation
output root. It completed `OPTIMAL` with exact certification.

| Metric | Result |
|---|---:|
| Objective | 2,557,651.111913833 |
| Lower bound | 2,557,651.111913597 |
| Upper bound | 2,557,651.111913833 |
| Absolute gap | 2.3562461137771606e-07 |
| Relative gap | 9.212539203652506e-14 |
| Iterations | 11 |
| Cuts | 10 |
| Final dual-cut violation | 4.656612873077393e-10 |
| Peak process-tree RSS | 0.08208465576171875 GiB |

The final dual-cut violation is below the formal `1e-7` cut-check tolerance. All
previous cuts are explicit constraints in the optimal master; its `1e-8`
`FeasibilityTol` is stricter than the cut-check tolerance.

The original formal result root retained its 24 successful run directories and
the original failed attempt. No existing artifact was overwritten, the L10 batch
was not continued, and no XL10 or XXL10 condition was run.
