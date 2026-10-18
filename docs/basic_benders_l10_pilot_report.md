# Basic-BD L10 single-pilot audit

## Disposition

`PASS_EXACT_CERTIFIED_DEVELOPMENT_PILOT`

Only `BASIC_L10_S20260921`, attempt-001, was executed. No retry or other Basic-BD/Direct condition ran.

## Result

- Solver status: OPTIMAL; exact certification: True; cut validity: True.
- Objective/LB/UB: 2048661.144168571103 / 2048661.144168571103 / 2048661.144168571103; relative gap: 0.000e+00.
- Basic core time: 274.744711 s; independent-inclusive total: 305.044248 s.
- Iterations: 8; global cuts: 7; Oracle time: 274.535335 s.
- Independent certification objective residual: 0.000e+00; strong-duality residual: 0.000e+00.

## Resource and evidence

- Monitor elapsed: 305.783667 s; peak process-tree RSS: 0.045776 GiB; stop reason: none.
- 8 iteration rows and 10 complete global Oracle calls were persisted; each call checked 41,617 scenarios.
- Attempt and canonical archives are byte-identical; 20 file SHA-256 records pass.

## Frozen PRB comparison

- Objective difference: 8.685e-08; both methods are exact-certified.
- Core time: Basic 274.744711 s versus PRB 25.503613 s; Basic/PRB ratio 10.773x.
- Iterations: Basic 8 versus PRB 7.
- Basic global cuts and PRB product cuts have different granularity and are not treated as equal work units.
