# Formal acceptance batch 1 results

`FORMAL_ACCEPTANCE_PASS`

The only execution attempt was `attempt_001`, authorized by commit
`1b06be7cc3a6108871d0dc40c6d0da2165b470b7`. Exactly A1-A5 ran for Renault
case `210202`; there were no failures or retries.

| Run | Mode | Objective | Runtime (s) | RI | Robust recourse |
| --- | --- | ---: | ---: | ---: | ---: |
| A1 | Direct exact, Gamma 2 | 116875.3457619544 | 8.680999994277954 | 0.020913487972572833 | 32261.040630600473 |
| A2 | PRB-Benders, Gamma 2 | 116875.34576195436 | 2.2748046000488102 | 0.020913487972578842 | 32261.040630600415 |
| A3 | Existing system, Gamma 0 | 108999.13573275977 | 0.006000041961669922 | 0 | 24384.830601405847 |
| A4 | Nominal reconfiguration, Gamma 0 | 108999.13573275965 | 0.019999980926513672 | 3.1575746674186425e-15 | 24384.83060140576 |
| A5 | Robust reconfiguration, Gamma 2 | 116875.3457619544 | 8.567999839782715 | 0.020913487972572833 | 32261.040630600473 |

A1/A2 objective, first-stage, and recourse differences are
`4.3655745685100555e-11`, `0`, and `5.820766091346741e-11`. Maximum coordinate
`x` difference is `9.652012522565201e-11`. A2 converged in 11 master solves with
114 unique product cuts and passed exact final certification.

A3 has exact `x=x0`, maximum `x` difference zero, and RI zero. A4 has `Gamma=0`
with reconfiguration allowed. A5 has `Gamma=2`, active robust recourse, and exact
certification.

For A3/A4/A5, robust minimum fill rates are 0.7946773732400614,
0.7946773732428405, and 0.713874373711431. Average fill rates in the selected
worst-service scenarios are 0.9828897811033365, 0.9828897811035548, and
0.9761561978092859. The canonical worst region is `12` in all three runs; A5's
worst-service shock set is `(1, BAC-O-6433)` and `(12, BAC---1041)`.

All formal-schema, provenance, file-hash, authorization, solver-profile, and A2
checkpoint/restart identity audits pass. Full E1-E7 authorization remains false.
