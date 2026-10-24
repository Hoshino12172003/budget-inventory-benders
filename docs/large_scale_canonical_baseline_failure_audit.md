# Large-scale canonical nominal baseline failure audit

## Scope

This audit covers the 30 deterministic main instances in
`experiments/results/prb_large_scale_simulation_v1` before any repair is
applied. It concerns only the Gamma-zero nominal incumbent preparation. It
does not diagnose or modify Pure Benders, Aggregate Benders with the structured
oracle, or PRB-Benders.

The canonical rule is the existing two-level rule:

1. minimize the Gamma-zero nominal economic objective; and
2. on that primary optimal face, lexicographically minimize `y`, then `x`, in
   the frozen depot/product order.

The implementation used an absolute primary-face tolerance of `1e-7`. Each
selected variable value was then imposed by an exact equality before the next
continuous variable was optimized.

## Inventory of failed preparations

| Scale | Seed | Failure stage | Fixing position | Variable | Gurobi status | Current tolerance | Primary objective delta | Assessment |
|---|---:|---|---:|---|---:|---:|---:|---|
| L10 | 20260921 | sequential continuous fixing | 95 | `x[5,10]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |
| L10 | 20260922 | sequential continuous fixing | 186 | `x[13,5]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |
| L10 | 20260923 | sequential continuous fixing | 209 | `x[15,4]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |
| L10 | 20260925 | sequential continuous fixing | 47 | `x[1,10]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |
| L10 | 20260926 | sequential continuous fixing | 222 | `x[16,5]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |
| L10 | 20260929 | sequential continuous fixing | 252 | `x[18,11]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |
| L10 | 20260930 | sequential continuous fixing | 246 | `x[18,5]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |
| XL10 | 20260921 | sequential continuous fixing | 182 | `x[10,12]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |
| XL10 | 20260927 | final primary-face validation | n/a | n/a | 2 (`OPTIMAL`) | `1e-7` | `1.0151416063308716e-7` | numerical |
| XXL10 | 20260925 | sequential continuous fixing | 558 | `x[32,10]` | 3 (`INFEASIBLE`) | `1e-7` | not reached | numerical |

Observed totals are 20 successful preparations and 10 failed preparations.
All nine sequential failures occur while fixing continuous inventory variables;
none occurs while fixing binary activation variables. The final validation
failure exceeds its gate by only `1.51416063308716e-9`.

## Root cause

The failure pattern is consistent with accumulated floating-point conflict,
not structural infeasibility:

- the unconstrained Gamma-zero nominal solve succeeds before every reported
  sequential failure;
- the primary face is retained with a valid one-sided upper bound for a
  minimization problem;
- exact equalities are added from floating-point continuous primal values over
  tens or hundreds of sequential solves;
- every status-3 failure occurs only after such continuous equalities have
  accumulated; and
- the only completed sequence rejected by the face check misses a fixed
  absolute threshold by approximately `1.5e-9`.

The brittle operations are therefore (a) exact equality fixing of continuous
solver values and (b) a scale-independent absolute-only validation gate. A
repair must leave the primary objective, constraints, ordering, and scientific
meaning of the incumbent unchanged. It should retain exact binary fixing, use
numerically bounded continuous fixing, and validate the primary face with a
small absolute-plus-relative tolerance whose realized absolute value is
recorded.

## Repair contract

The original strict solve remains the first attempt. Only a sequential
canonical-stage infeasibility or a final primary-face numerical rejection can
activate the deterministic repair attempt. A primary nominal model failure is
not retried or reclassified.

The repair rebuilds the same model and retains the same objectives, variable
order, instance, and seed. Binary variables remain fixed exactly. For a
continuous variable, the repair uses the upper bound established by its
lexicographic minimization with a `1e-7` numerical buffer instead of adding an
exact floating-point equality. The primary face is

`max(1e-7, 1e-12 * max(1, abs(z_star)))`.

The validation allowance is an additional `5e-9`, used only to recognize the
solver's residual on the already imposed primary-face constraint. For the ten
failed instances, the realized face tolerances range from
`1.415759287067988e-6` to `4.466949865047146e-6`; no `1e-4` or `1e-3`
tolerance is used. Every repaired artifact records the effective tolerance,
validation slack, continuous fixing tolerance, attempt count, repair flag, and
repair profile `bounded_continuous_fix_abs1e-7_rel1e-12_v1`.

## Repair validation

All ten previously failed instances passed an isolated preparation-only
validation. No Pure, Aggregate, or PRB robust solve was run, and no primary
result directory was written or overwritten.

| Scale | Seed | Primary objective | Objective delta | Effective face tolerance | x0 hash |
|---|---:|---:|---:|---:|---|
| L10 | 20260921 | 1965808.584309447 | 1.9657891243696213e-6 | 1.965808584309447e-6 | `505e46a4a03a1ff25e265a49392e58081ecd85f50a1223fb1551ce50186051c8` |
| L10 | 20260922 | 2204550.8078814093 | 2.205371856689453e-6 | 2.2045508078814093e-6 | `d8fb2cbdd6fe94af6eeb591d5dac6da9a1d28e02685c2d5a87fb2ed485eecc2f` |
| L10 | 20260923 | 1415759.287067988 | 1.4158431440591812e-6 | 1.415759287067988e-6 | `2156393aa544eebcd67dd552fcaf1048a6c4fad5c4faf42019d1516ee31c36cc` |
| L10 | 20260925 | 2054340.740799202 | 2.053799107670784e-6 | 2.0543407407992018e-6 | `c3e9353dd6643f2d08c916d47a8cb6fd4618bf01219087571113e723de771de9` |
| L10 | 20260926 | 1978556.7006113713 | 1.978827640414238e-6 | 1.978556700611371e-6 | `7c25225eadb13f3e24291d9385ea4a23a6efc29dd74029993e4c21563c4f4414` |
| L10 | 20260929 | 2467189.3620543447 | 2.4656765162944794e-6 | 2.467189362054345e-6 | `8c419dd445e173cfb65c30d5c838233259e9536efab68c5c16c64e73dddc330a` |
| L10 | 20260930 | 2251070.3383723125 | 2.251937985420227e-6 | 2.2510703383723126e-6 | `bc53041d595611a7a689bfce5d7bf2eeafcf30e075a889973458db3f29b0fadb` |
| XL10 | 20260921 | 3052197.887960585 | 3.0510127544403076e-6 | 3.0521978879605847e-6 | `89d558ca9bee95e37b1e58408873847a450f1a2dc8b08a42e9b2e09d616d43c3` |
| XL10 | 20260927 | 2661673.411367862 | 2.6640482246875763e-6 | 2.661673411367862e-6 | `1334b2089af441bf2c43c3254a429159c22bbdf89a40c6005cca2378f9578ae2` |
| XXL10 | 20260925 | 4466949.865047147 | 4.466623067855835e-6 | 4.466949865047146e-6 | `0063597cf98a7c560389f2c23ef42830aafb7817336edc26a8de292c204e8b35` |

Every delta is below the recorded effective face tolerance plus `5e-9`.
Capacity and inventory-bound checks pass for all ten. The maximum observed
constraint, bound, and integrality violations are respectively
`2.7939677238464355e-9`, `9.451923688175157e-10`, and `0`.

A second independent regeneration produced identical x0 hashes for all ten
instances. A control regeneration of the already successful L10 seed 20260924
did not activate the repair and reproduced both its stored x0 hash and B_ref
exactly.

## Separate known issue

The Pure Benders cut violation recorded for XL10 seed 20260924 is outside this
audit. It is neither attributed to nor repaired through canonical nominal
baseline preparation.
