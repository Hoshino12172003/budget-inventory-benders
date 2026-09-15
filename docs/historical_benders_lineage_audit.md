# Historical Benders lineage audit

## Decision

`HISTORICAL_BENDERS_NOT_COMPARABLE`

The repository history contains both the 2,154-cut Renault run and genuine
4,000-plus-cut runs. They are separate experiment families. Neither is a
vanilla implementation of the current paper-final reconfiguration model, so
the static comparability gate fails and no development optimization was run.

## Lineage

### Renault 2,154-cut run

- Result source commit: `b78f6c976984ba22602902ed325eb1442d572ba4`.
- Frozen analysis/config commit: `0dd11cc5ffe6230eb865d48a31bd68982062ecec`
  on `origin/pr/86`.
- Iteration log introduction: commit `f8d1012`, file
  `real_data_studies/renault_robust_baseline_v1/results/iteration_logs/210202_B1.00_iterations.csv`.
- Runner: `src/benders_ccg_tail_handoff_runner.py`.
- Solver sources: `src/benders.py` and `src/robust_dual_subproblem.py`.
- Configuration: `experiments/configs/benders_ccg_tail_handoff_210202.yaml`.
- Instance: old formal-v6 `210202_B1.00.json`, with
  \(I=15,R=12,J=8,\Gamma=2\) and 4,657 uncertainty scenarios.

The method is recorded as `adaptive_gap_gamma_benders`, variant
`joint_v1_core_point_strengthened`. It uses a global robust-dual MILP, one
selected cut per iteration, core-point strengthening, adaptive master and
subproblem precision, and historical final-certification machinery. The run
hit its 1,800-second time limit after 2,154 iterations and 2,154 cuts. It ended
uncertified with LB 116802.42332725937, UB 116840.66551645267, and relative gap
0.00032730204868543407.

Master solves consumed 1521.661534596933 seconds (84.5281%); robust
subproblems consumed 254.81346760271106 seconds (14.1548%); core-point
auxiliaries consumed 16.529342701425698 seconds. The last incumbent improvement
was at iteration 1,222. All final 500 recorded cut violations were positive;
their median absolute violation was 59.556645335769645. The old log does not
record adversarial-pattern identities, so worst-case repetition cannot be
reconstructed.

Selected convergence checkpoints are:

| iteration | LB | UB | relative gap |
|---:|---:|---:|---:|
| 539 | 116743.5133 | 116958.3692 | 0.0018370 |
| 1077 | 116799.6527 | 116849.6013 | 0.00042746 |
| 1616 | 116800.4203 | 116840.6655 | 0.000344445 |
| 1939 | 116801.0041 | 116840.6655 | 0.000339448 |
| 2047 | 116801.2921 | 116840.6655 | 0.000336984 |
| 2154 | 116802.4233 | 116840.6655 | 0.000327302 |

The continuing but small lower-bound gains and positive cut violations support
master growth as an observed bottleneck. They do not prove a defective cut.

### Genuine 4,000-plus-cut runs

The 4,000-plus artifacts are in
`analysis/fairness_scalability_s1_attempt2_cross_scale_freeze/frozen_run_matrix.csv`,
frozen through commits `0639558`, `d6ae40c`, and `10fe8aa`. Their recorded run
code commits include `29ae09e968a206b1987714317ff7528165372a46` and
`ec33a047ecd60f4cb473260f1b3c4078726db776`. The execution path is
`src/fairness_scalability_runner.py` to `src/fairness_benders.py`.

These are generated synthetic regional-fairness frontier experiments, not
Renault reconfiguration experiments. The medium-large scale has
\(I=6,R=10,J=6,\Gamma=2\); the large scale has
\(I=8,R=12,J=8,\Gamma=2\). Observed examples include:

| scale/seed | variant | status | runtime s | iterations | cuts | master s | separation s |
|---|---|---|---:|---:|---:|---:|---:|
| medium-large/161 | persistent cache batch-5 | certified | 362.2756 | 1202 | 5778 | 277.3529 | 83.4579 |
| medium-large/161, rho=.01 | persistent cache batch-5 | certified | 456.0822 | 1559 | 7721 | 358.2285 | 96.2408 |
| large/160 | persistent cache | time limit | 1800.0161 | 6581 | 6581 | 1610.4611 | 185.3759 |
| large/160 | persistent cache batch-5 | time limit | 1800.0193 | 2602 | 13010 | 1460.2347 | 336.5511 |
| large/161 | persistent cache | time limit | 1800.0161 | 4950 | 4950 | 1699.2761 | 98.2955 |
| large/161 | persistent cache batch-5 | time limit | 1800.0233 | 1800 | 9000 | 1632.3951 | 165.9251 |

These variants solve a fairness frontier with Farkas feasibility cuts in
\((y,x,T)\). They use persistent separation, certified scenario caches, and in
batch variants a solution pool and up to five cuts per iteration. Their
baseline anchor also uses `joint_v1_core_point_strengthened`. They do not use
PRB product-risk decomposition and are not a Benders-to-CCG hybrid, but their
model, cut family, cache, and multi-cut behavior make them strengthened legacy
Benders rather than vanilla Benders.

## Algorithm classification

| feature | Renault 2,154-cut | Fairness 4,000+ | Current Pure |
|---|---|---|---|
| classification | `LEGACY_STRENGTHENED_BENDERS` | `LEGACY_STRENGTHENED_BENDERS` | `VANILLA_BENDERS` |
| master surrogate | aggregate robust recourse | fairness frontier variable | one aggregate theta |
| uncertainty oracle | global robust-dual MILP | global fairness separation | global adversarial MILP |
| cut family | strengthened joint optimality cut | Farkas feasibility cut | aggregate supporting cut |
| cuts per iteration | one | one or up to five | one |
| core-point strengthening | yes | anchor/config-dependent; fairness cuts excluded | no |
| adaptive precision | yes | selected anchor/config uses it | no |
| persistent cache/pool | no selected cut pool | yes | no |
| PRB/product-risk decomposition | no | no | no |
| CCG hybridization | no in the Benders-only observation | no | no |

No evidence of Pareto/Magnanti-Wong cuts, trust regions, cut deletion, or PRB
utilities was found in the selected historical paths. Absence from the frozen
configuration is reported as absence, not inferred as a general property of
all old branches.

## Static comparability gate

The 2,154-cut implementation predates Reconfiguration Model V2. Its master has
no frozen \(x^0\), \(a^+\), \(a^-\), or reconfiguration cost. It uses an old
formal-v6 instance, region/data calibration, budget reference, objective
interpretation, adaptive precision, and core-point strengthening. The
4,000-plus family is further removed: it is a synthetic regional-fairness
frontier with a different objective and Farkas cut family.

Making either historical source accept `RENAULT_EMPIRICAL_8CASE_V1` would
require changing its mathematical master, subproblem, and cut semantics. That
is not an import/API compatibility repair and would no longer be restoration
of the historical implementation. Therefore:

- no historical source was copied into the new package;
- no compatibility repair was applied;
- `src/historical_benders_baseline.py` and a development runner were not
  created;
- the 210202 reproduction is `NOT_RUN_STATIC_COMPARABILITY_BLOCK`;
- objective consistency, reproduced T_core, peak memory, and speed ratio are
  `NOT_AVAILABLE`.

The current frozen 210202 Pure result is still useful as context: objective
1058780.7942496866, exact-certified, nine iterations, eight cuts, and T_core
0.41859719999774825 seconds. Its objective scale alone shows it is not the old
formal-v6 problem. The raw time quotient 1800.1849/0.4186 is not a scientific
speedup and is intentionally not reported as one.

## Why the cut counts differ

The evidence supports three bounded conclusions. First, the old Renault run's
master became the dominant cost as 2,154 distinct violated cuts accumulated;
lower-bound progress continued slowly after the last incumbent change. Second,
the 4,000-plus records belong to a different fairness/Farkas algorithm, where
persistent caches and batch multi-cuts can create 5,000-13,000 rows quickly.
Third, current Pure Benders solves the current reconfiguration model with eight
global supporting cuts on case 210202.

The evidence does not isolate a causal decomposition among formulation,
dataset, cut strength, adaptive precision, solver evolution, and implementation
changes. Because the mathematical problems and data are different, attributing
the observed cut-count or runtime gap to one algorithmic improvement would be
invalid. The historical implementations may be called `Historical Benders` or
`Legacy strengthened Benders`; neither may serve as the paper's Pure/Vanilla
baseline. The current independent Pure Benders remains that baseline.

`FOUR_THOUSAND_CUT_ARTIFACT_NOT_FOUND = false`

`historical optimization runs during this audit = 0`

`current optimization reruns during this audit = 0`
