# EF-BD XL10 single-pilot preparation

## Frozen scope

The only candidate is `EF_XL10_S20260921`, mapped to the existing Scaling V2 input `ASC_INSTANCE_XL10_S20260921`. The configuration is authorization-closed and targets `attempt-001`. It uses the unchanged EF-BD implementation certified on all ten L10 instances: one global theta, at most one aggregate optimality cut per iteration, and the complete Direct-equivalent recourse LP. Product multicut, product risk-budget decomposition, SG pruning, and the compact Pure oracle remain excluded.

The frozen identity is:

- instance SHA-256: `16abfafe6fb84902ddac9734edf17716c1d7d9a4c6fd01adad73032054b221a1`;
- preparation SHA-256: `a23ff34dcee1bad5ce98414ef388c73e40cfdc41d640f47c42214f330d01b626`;
- instance hash: `73732c6523ff154f1e5e7891641c25102345bc40c65bfb72630c817c78349695`;
- x0 hash: `89d558ca9bee95e37b1e58408873847a450f1a2dc8b08a42e9b2e09d616d43c3`.

## Static model size

For `I=30`, `R=30`, `J=14`, and `Gamma=2`, each product has `1+30+C(30,2)=466` local scenario blocks. The EF Oracle therefore has 6,524 product-local scenario blocks and 120 global risk-budget allocations.

| model | variables | constraints | nonzeros |
|---|---:|---:|---:|
| EF-BD monolithic recourse Oracle | 6,073,887 | 404,608 | 18,223,332 |
| frozen Direct extensive form | 6,075,177 | 405,479 | 18,422,892 |

These are exact algebraic counts from the current model structure. No Gurobi model was built and no memory measurement is inferred from these counts alone.

## Resource protocol

The ten certified L10 EF-BD runs peaked between 1.519 and 1.787 GiB. Scaling the maximum observed peak by the XL10/L10 nonzero ratio (2.6903) gives a coarse 4.807-GiB projection. The certified same-seed Direct XL10 attempt peaked at 6.852 GiB; an earlier Direct attempt crossed its 7-GiB cap. Direct and EF-BD have different solve mechanics, so these values bound risk rather than predict EF memory exactly.

The candidate protocol uses an 8-GiB process-tree cap, 12-GiB startup gate, 3-GiB system-available floor, 20-GiB disk gate, 900-second wall limit, 0.25-second monitoring, `Threads=2`, one worker, and no automatic retry. At the startup threshold, a process at the cap leaves 4 GiB available. The classification is moderate-to-high resource risk: safe for one monitored pilot, not proven sufficient for completion.

Resource or time termination remains a preserved failed attempt. Numerical, identity, hash, worker, or archive failure is fail-closed. A canonical result is accepted only after exact certification, cut validity, clean resource termination, provenance hashes, and attempt/canonical byte equality all pass.

No optimization is authorized by this preparation.
