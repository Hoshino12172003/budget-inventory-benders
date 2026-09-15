# E1c Renault-calibrated controlled scaling protocol

## Scientific question

E1c asks: **Does exploiting product separability and the global risk-budget
structure improve computational scalability as network size increases?**

The protocol is direction-neutral. It does not assume that PRB-Benders is
faster. E1a and E1b remain separate empirical benchmarks; E1c is a controlled
scaling experiment and must not be described as additional original Renault
cases.

## Controlled instance family

Every generated economic value is derived from the frozen
`RENAULT_EMPIRICAL_8CASE_V1` pool. The generator is
`deterministic_empirical_bootstrap_v1` and uses five frozen seeds. It applies
balanced, seeded resampling rather than specifying new parametric economic
distributions:

- product donors are shuffled complete cycles of the frozen eight products;
- region donors are sampled without replacement from the 96 observed
  case-region profiles; nominal demand, deviation, and shortage penalty move
  together for each donor region/product;
- depot donors are sampled without replacement from the 122 observed depots;
- capacity-to-system-volume-demand, UB-to-product-demand, and
  fixed-cost-to-system-demand ratios are preserved when dimensions change;
- holding costs are observed donor depot/product values;
- transport costs preserve observed `transport_cost / product_volume` values,
  then apply the donor product volume;
- service targets, service penalties, and product volumes come from the frozen
  product profiles.

The construction is empirical replication and controlled expansion. It is not
new Renault field data and is not an arbitrary random synthetic generator.
Every artifact must record its seed and complete donor indices.

Generated primitive instances deliberately have no `initial_inventory`. Before
formal authorization, each generated instance requires the already frozen
nominal-incumbent procedure: solve the unconstrained-budget Gamma-0 nominal
model, freeze the resulting data-derived incumbent as \(x^0\), perform the
existing stability/capacity/UB audit, and define \(B_{ref}\) as that incumbent's
first-stage expenditure. Those data-preparation solves are currently
unauthorized and were not run in this task.

## Frozen Renault calibration statistics

The design configuration freezes the full count, minimum, P10, P25, median,
mean, P75, P90, and maximum for:

- nominal regional-product demand;
- deviation/nominal ratios for positive-demand cells;
- depot capacity/system volume-demand ratios;
- inventory UB/product nominal-demand ratios;
- transport cost/product-volume ratios;
- fixed depot cost/system nominal-demand ratios;
- holding costs, shortage penalties, service penalties, and product volumes.

It also freezes \(\lambda_R=0.05\), the current \(B_{ref}\) construction rule,
all eight source instance hashes, and the generator hash.

## Scale grid

The originally suggested L and XL levels fail the conservative all-method
resource screen. The proposed formal grid is therefore:

| Scale | I | R | J | First-stage inventory pairs |
|---|---:|---:|---:|---:|
| S | 15 | 12 | 8 | 120 |
| M | 20 | 16 | 10 | 200 |
| L | 25 | 24 | 12 | 300 |

The original candidate M becomes the proposed L. Original candidate L and XL
remain recorded as excluded `RESOURCE_RISK` levels; they are not silently
deleted and cannot be introduced after results are observed.

## Gamma rule

The paper-final recommendation is **fixed Gamma = 2** for all scales. This
retains the Renault baseline interpretation of two simultaneous adverse
region-product cells and holds uncertainty-budget intensity fixed while
network dimensions change. Although Gamma/RJ falls with scale, the number of
competing pairs still grows from 4,657 global scenarios at S to 12,881 at M
and 41,617 at L.

Alternatives were rejected before execution:

- proportional to \(RJ\) gives Gamma 2/6/12/24 on the original candidates and
  expands current product-risk construction to as many as
  3,764,670,964,725,072 blocks;
- proportional to \(J\) gives Gamma 2/3/4/6 and reaches 340,724,856 blocks;
- running Gamma 2/4/8 confounds dimension scaling with uncertainty scaling and
  reaches 11,164,198,440 blocks at candidate XL.

These rules would primarily test combinatorial scenario enumeration and would
asymmetrically endanger Direct and both structured-oracle methods. Fixed Gamma
does not remove global coupling: Pure still selects two shocks jointly from
all \(RJ\) cells, while PRB must allocate the same total budget across a growing
number of products.

## Methods and fairness

Each generated condition is evaluated by exactly four methods:

1. Direct Exact;
2. Pure Benders;
3. Aggregate Benders + Structured Oracle;
4. PRB-Benders.

They use the same generated instance/hash, \(x^0\), \(B_{ref}\), Gamma,
\(\beta=1\), \(\lambda_R=0.05\), service target, Gurobi 13.0.2, frozen solver
profile, default thread/seed policy, tolerances, 900-second timeout, hardware,
and exact-certification threshold. No method receives another method's cuts,
solution, or warm start. Scale eligibility is decided for all four methods
before execution; it is never method-specific.

## Replication and run count

Five deterministic seeds are frozen:

`20260911, 20260912, 20260913, 20260914, 20260915`.

Every seed is used at every scale and with every method. Failed, slow, or
unfavorable replicates remain in the analysis. The proposed experiment is
therefore \(3\times5\times4=60\) formal runs. Ten replicates are not justified
before any resource evidence exists; increasing the count after seeing results
is prohibited.

## Runtime and outcome contract

For every method, \(T_{core}\) starts immediately before the first
algorithm-required model construction and ends after exact certification. It
includes master and oracle construction, every `optimize` call, robust-oracle
work, Gamma composition where applicable, cut construction, convergence
checks, and final certification. It excludes paper tables, plots, exhaustive
service reporting, and other nonessential post-evaluation.

Future E1c runners must wrap Direct around both model construction and
optimization; the solver-native `Model.Runtime` alone is insufficient because
it excludes Python/Gurobi construction. This wrapper requirement makes the
four E1c timings comparable and does not alter any algorithm.

Each result is classified as exact solved, timeout with incumbent/bound/gap,
memory failure, or certification failure. The common timeout is 900 seconds.
The primary runtime statistic is the geometric mean of penalized core time:
exact runs use \(T_{core}\), while non-exact runs use \(2\times900\) seconds.
Exact solve rate and raw timeout rate are reported alongside it. Pairwise
speedups use the geometric mean of paired penalized ratios. Objective
consistency is evaluated only among exactly certified methods under the frozen
absolute tolerance.

Report T_core, exact/timeout rates, iterations, cuts, master and oracle time,
objective consistency, and peak memory only when a validated measurement is
available. The three preregistered ratios are Pure/PRB, Direct/PRB, and
Aggregate-Structured/PRB.

## Direction-neutral interpretation

- If Pure is faster and its log-runtime scaling slope is no worse than PRB,
  computational superiority of PRB is not supported.
- If Pure is faster at S but PRB has a lower preregistered log-runtime slope
  and overtakes at L, PRB scalability is supported.
- If Pure or Direct has substantially more L-scale timeouts while PRB remains
  exactly certified, this is strong scalability evidence.

The slope is an OLS coefficient of log penalized T_core on log \(IRJ\), using
all 15 frozen scale-replicate cells. A case-resampling bootstrap interval and
the paired L-scale geometric-mean ratio are reported as uncertainty summaries;
neither the grid nor classification rule may be changed afterward.

## One-factor diagnostic

The appendix-only design holds two dimensions at S and varies the third over:

- I only: 15, 20, 25;
- R only: 12, 16, 24;
- J only: 8, 10, 12.

Gamma remains 2. This diagnostic is `DESIGN_ONLY_NOT_AUTHORIZED` and is not
required for the primary conclusion.

## Authorization

`formal_run_authorized = false`

`development_solve_authorized = false`

`resource_probe_authorized = false`

`instance_generation_authorized = false`

`baseline_preparation_authorized = false`

No instance file, nominal incumbent, budget anchor, development result, or
formal result was generated in this task.
