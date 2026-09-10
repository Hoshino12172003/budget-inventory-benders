# E1 empirical case selection

`E1_EMPIRICAL_CASES_V1` fixes the following pre-solve order: `210202`, `210628`,
`210129`, `210310`, `210330`, `210323`, `210428`, and `210611`. Selection used
only raw customer count, depot count, demand-record density, and date coverage.
No optimization output was inspected or used to replace a case.

The cases span 485--760 customers, 11--19 empirical depots, 29--30 raw
products, 19--22 planning days, and demand-pair density 0.102269--0.129086.
The frozen eight products are:

- `BAC---1041`
- `BAC-O-4312`
- `BAC-O-4325`
- `BAC-O-6423`
- `BAC-O-6433`
- `CON-S-0130`
- `SLI---0770`
- `SLI---1200`

The intended final dimensions preserve each case's depot identities, with
`R=12` and `J=8`: 210202 `(15,12,8)`, 210628 `(15,12,8)`, 210129
`(15,12,8)`, 210310 `(16,12,8)`, 210330 `(11,12,8)`, 210323 `(13,12,8)`,
210428 `(18,12,8)`, and 210611 `(19,12,8)`. For the six new cases these remain
target dimensions, not constructed formal instances, because the geographic
identity gate blocks construction.

The earlier synthetic design remains historical `NOT_RUN` material. It is not
part of the proposed empirical main benchmark and was not executed here.

## Deferred robustness item

An alternative-incumbent robustness check may later use two or three
representative cases with a predeclared demand-proportional or perturbed
incumbent. It is outside this construction task and is not authorized.
