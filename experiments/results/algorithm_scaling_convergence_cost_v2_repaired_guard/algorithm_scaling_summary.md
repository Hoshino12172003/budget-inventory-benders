# Algorithm scaling and convergence-cost trade-off

Expected conditions: 90; exact-certified: 89; documented non-certified: 1; unattempted: 0.

Documented non-certified condition: `ASC_XXL10_S20260925_PURE_BENDERS`.

Formal classification: `PRB_FEWER_ITERATIONS_BUT_HIGHER_ORACLE_COST`.

| Size | Method | N | Iterations | Core time (s) | Oracle time (s) | Iterations to 99.9% LB | Iterations to 99.99% LB |
|---|---|---:|---:|---:|---:|---:|---:|
| L10 | pure_benders | 10 | 18.500 | 1.491 | 0.423 | 5.300 | 8.100 |
| L10 | aggregate_benders_structured_oracle | 10 | 14.800 | 38.813 | 27.849 | 4.900 | 7.500 |
| L10 | prb_benders | 10 | 7.400 | 25.524 | 14.709 | 3.200 | 4.700 |
| XL10 | pure_benders | 10 | 14.900 | 2.261 | 0.697 | 5.100 | 8.000 |
| XL10 | aggregate_benders_structured_oracle | 10 | 14.300 | 108.116 | 78.157 | 5.000 | 7.900 |
| XL10 | prb_benders | 10 | 6.400 | 65.774 | 35.884 | 3.100 | 4.400 |
| XXL10 | pure_benders | 9 | 15.000 | 2.881 | 0.686 | 5.000 | 8.444 |
| XXL10 | aggregate_benders_structured_oracle | 10 | 13.200 | 227.065 | 161.519 | 4.600 | 8.500 |
| XXL10 | prb_benders | 10 | 6.300 | 143.340 | 79.668 | 3.000 | 4.600 |

PRB consistently reduces iterations and accelerates lower-bound refinement relative to Aggregate, while its structured oracle remains substantially more expensive than Pure's global oracle. Pure is therefore fastest in wall-clock time; the result does not claim that PRB is fastest overall. The main trade-off is stronger information transfer versus higher oracle cost.

XXL10 comparisons involving Pure use paired exact-certified seeds only; the Pure N=9 mean is not treated as a fully paired comparison against the N=10 Aggregate and PRB means.
