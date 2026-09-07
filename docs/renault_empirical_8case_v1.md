# Renault empirical eight-case dataset

Dataset identity: `RENAULT_EMPIRICAL_8CASE_V1`.

The dataset contains eight original Renault date cases with one common,
reproducible 12-region geographic mapping, the frozen eight-product set, and
case-specific empirical depot sets. Each case uses a data-driven nominal
incumbent inventory plan and a case-specific budget reference. It must be
described as **empirical Renault cases with data-derived formal
transformations**. The incumbent is not observed initial inventory.

## Frozen identities and transformations

The mapping uses 298 stable common customer identities, latitude/longitude
only, deterministic haversine 12-medoids, nearest-frozen-medoid assignment for
new customers, and west-to-east region ordering. Its SHA-256 is
`0bcdd7bb99926ed780c56764c531b76971dbb0bf24e77198766a754d9dde95ff`.
No center, seed, ordering, assignment rule, or product identity is changed.

All cases use weekday historical daily means, linear 0.90 quantiles for upward
demand deviation, Renault excess-inventory costs, the frozen capacity and UB
formulas, demand-weighted shortage and distance aggregation, service target
0.90, and the frozen fixed-cost and service-penalty calibration rules. The raw
`initial_inventory` field is not used as `x0`.

Formal instances are stored in `data/formal_instances_v2`; the old
`data/formal_instances` namespace remains historical and unchanged. Each new
instance embeds its Candidate A incumbent, obtained from the unconstrained-
budget Gamma=0 nominal model without reconfiguration variables, reconfiguration
cost, or lambda_R. `B_ref` is that incumbent's first-stage spending.

## Deterministic audit result

Two independent construction passes produced identical instance, x0, and
calibration hashes for all eight cases. Capacity and UB violations are zero in
every case. The primary optimal face is diagnosed independently from incumbent
readiness. Case `210428` retains two coordinate ranges above the frozen `1e-3`
structural threshold (maximum `0.002110277802614746`), so its primary face is
reported as nonunique; this diagnostic does not block a reproducible incumbent.

Every case uses the same deterministic selector
`lexicographic_min_y_then_x_on_primary_optimal_face_v1`: solve the unchanged
Gamma=0 economic objective, constrain it to its optimum plus `1e-7`, minimize
`y` in depot order and then `x` in depot-product order while fixing each value
by equality, and finally re-solve the economic objective with all first-stage
variables fixed. The economic model and frozen tolerances are unchanged. All
eight canonical incumbents pass the objective-face, capacity, and UB gates, so
the dataset status is `RENAULT_EMPIRICAL_8CASE_V1_READY`.

The preparation executed 4,302 recorded Gamma=0 optimization calls across the
two independent construction passes and the first-pass structural audit.
Gamma=2 E1 Direct/PRB solves, synthetic execution, and E2--E7 execution are all
zero.

## Paper-final E1 contract

The intended final design is eight cases by two exact methods, for 16
observations at `beta=1.0`, `Gamma=2`, and `lambda_R=0.05`. The authorization
manifest remains fail-closed (`formal_run_authorized=false`). The four earlier
210202/210628 observations are preserved as historical artifacts and are not
paper-final results under this mapping.

Future commands, after a human explicitly changes the authorization manifest,
are:

```powershell
$env:PYTHONPATH = "src"
python experiments/run_e1_empirical_local.py --case 210202 --method direct
python experiments/run_e1_empirical_local.py --case 210202 --method prb
python experiments/run_e1_empirical_local.py --case 210628 --method direct
python experiments/run_e1_empirical_local.py --case 210628 --method prb
python experiments/run_e1_empirical_local.py --case 210129 --method direct
python experiments/run_e1_empirical_local.py --case 210129 --method prb
python experiments/run_e1_empirical_local.py --case 210310 --method direct
python experiments/run_e1_empirical_local.py --case 210310 --method prb
python experiments/run_e1_empirical_local.py --case 210330 --method direct
python experiments/run_e1_empirical_local.py --case 210330 --method prb
python experiments/run_e1_empirical_local.py --case 210323 --method direct
python experiments/run_e1_empirical_local.py --case 210323 --method prb
python experiments/run_e1_empirical_local.py --case 210428 --method direct
python experiments/run_e1_empirical_local.py --case 210428 --method prb
python experiments/run_e1_empirical_local.py --case 210611 --method direct
python experiments/run_e1_empirical_local.py --case 210611 --method prb
```

These commands are documentation, not authorization.
