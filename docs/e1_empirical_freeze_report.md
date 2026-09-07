# E1 empirical freeze report

Final state: `E1_EMPIRICAL_DATASET_PARTIAL`.

The eight case identities, raw CRC identities, empirical dimensions, frozen
product list, complete deterministic geographic mapping, and mapping audit are
frozen. The mapping itself passes coverage and empty-region checks, but fails
the legacy formal-input compatibility gate described in
`docs/e1_empirical_data_builder.md`.

## Preserved formal material

The existing 210202 and 210628 instances, nominal incumbents, budget references,
and four Direct/PRB E1 observations are unchanged and were not rerun. Their
frozen baseline values are:

| case | total x0 | positive pairs | active depots | B_ref | instance SHA-256 | x0 SHA-256 |
|---|---:|---:|---:|---:|---|---|
| 210202 | 5776.468951048719 | 69 | 13 | 84614.30513135393 | `d40beacd55c43b045db79140e38ee211e904dd72f7d6ca95dfb34c1f5a2cdb35` | `188da42a6e1d53ebba6d5c3c5d3af8042da5e9088bacce1a3041252b56cc41d8` |
| 210628 | 3547.1923076923076 | 64 | 13 | 50558.18771213083 | `32321a9dc18d1b0134a73b45ed4695f44c8425f544ceb498d7c8f7eeda8d6ba9` | `f454e5b0b72f395dad9acb5fd43572fe75dea6f6cb6ad5cd64ecd5a35cd797ea` |

Both preserved baselines are structurally stable and capacity/UB compatible.
The six new cases have no x0, B_ref, instance hash, or baseline audit because
the blocker occurs upstream. No blocked value is filled, inferred, or copied
from another case.

## Reproducibility and execution

Repeated static generation produces the same canonical mapping hash. Formal
instance regeneration is `NOT_RUN_BLOCKED_BY_REGION_MAPPING`, not a claimed
pass. The local runner is deliberately fail-closed: it checks the dataset freeze
before authorization, Git, and output gates, and cannot reach a solver while
the dataset is partial. Its twelve future one-solve commands are:

```text
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

These are documentation only, not authorization. No new Gamma=2 E1 benchmark,
nominal baseline/calibration preparation, or synthetic solve ran. E2--E7
authorization remains false.
