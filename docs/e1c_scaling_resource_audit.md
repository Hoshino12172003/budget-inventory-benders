# E1c controlled scaling resource audit

## Decision

The recommended S/M/L grid passes static resource design review on the
31.5-GiB machine. The original candidate L and XL do not. The recommended L
still requires a development-only resource probe before the grid is frozen,
because Pure Benders is very fast at the empirical S scale.

## Counting formulas

For fixed Gamma \(G=2\), define

\[
P(R,G)=\sum_{g=0}^{G}{R\choose g}.
\]

The first stage has \(I+3IJ\) variables. The Pure global adversarial MILP has
\(RJ\) binary variables, \(IJ+3RJ+J\) continuous variables, and
\(IRJ+7RJ+1\) constraints. PRB and the structured aggregate oracle construct
\(J P(R,G)\) product-risk scenario blocks; the PRB master has
\(J(G+1)+1\) recourse surrogates, and each product cut has I coefficients.

The current factorized Direct exact formulation has

\[
I+3IJ+J(G+1)+1+JP(R,G)(IR+R+1)
\]

variables. Its corresponding constraint count is

\[
I+2IJ+1+JP(R,G)(R+I+2)+{J+G\choose G}.
\]

These are algebraic construction counts, not measured peak memory.

## Candidate grid audit

| Scale | I/R/J | Pure vars / constraints | PRB blocks | Direct vars / constraints | Risk |
|---|---|---:|---:|---:|---|
| S | 15/12/8 | 512 / 2,113 | 632 | 122,376 / 18,629 | LOW |
| M | 25/24/12 | 1,464 / 9,217 | 3,612 | 2,258,462 / 184,929 | MODERATE_HIGH |
| L | 40/36/16 | 2,960 / 27,073 | 10,672 | 15,764,553 / 833,890 | RESOURCE_RISK |
| XL | 60/48/24 | 6,072 / 77,185 | 28,248 | 82,742,845 / 3,110,546 | RESOURCE_RISK |

The risk at candidate L/XL is not the Pure global MILP. It is the explicit
scenario-block construction required by Direct and both current structured
oracles. Python/Gurobi object overhead and constraint matrix storage make the
82.7-million-variable XL construction plainly inappropriate for a 31.5-GiB
machine. Running only the methods that fit would violate the four-method
fairness contract.

## Recommended grid

| Scale | I/R/J | Pure vars / constraints | PRB blocks | Direct vars / constraints | Risk |
|---|---|---:|---:|---:|---|
| S | 15/12/8 | 512 / 2,113 | 632 | 122,376 / 18,629 | LOW |
| M | 20/16/10 | 850 / 4,321 | 1,370 | 462,341 / 52,547 | MODERATE |
| L | 25/24/12 | 1,464 / 9,217 | 3,612 | 2,258,462 / 184,929 | MODERATE_HIGH |

This grid expands \(IRJ\) from 1,440 to 7,200 and inventory pairs from 120 to
300 while keeping every current exact method below the static construction
caps. It is large enough to estimate a growth trend without knowingly entering
an out-of-memory regime.

## Conservative safety gate

Before any future run, all conditions must hold:

- at least 24 GiB system memory is available;
- only one E1c process runs at a time;
- projected Direct variables do not exceed 3,000,000;
- product-risk blocks do not exceed 4,000;
- Pure adversarial variables/constraints do not exceed 10,000/100,000;
- the output directory does not already exist;
- the generated instance, x0, B_ref, generator, config, solver, and Git hashes
  match an independently authorized manifest.

Failure excludes the complete scale-method block before execution; it never
grants one algorithm a different timeout or machine. An OS memory failure is
recorded, not retried with a scientifically different configuration.

## Timeout

The uniform recommendation is 900 seconds per method-condition. This matches
the existing Pure safety guard and keeps 60 runs bounded while still allowing
meaningful censoring. An 1,800-second alternative is not selected without a
resource probe; no such probe is currently authorized.

## Gamma resource interaction

On the original candidate grid, proportional-RJ Gamma produces product-block
counts of 632, 2,280,612, 35,869,002,368, and
3,764,670,964,725,072. Proportional-J Gamma reaches 340,724,856 blocks at XL.
Even the fixed sequence Gamma 2/4/8 reaches 11,164,198,440 XL blocks. These
rules fail the resource and fairness screen for the current exact
implementations. Fixed Gamma 2 is therefore the only audited rule that isolates
dimension scaling and permits all four methods.

For the recommended S/M/L grid, the proportional-exposure rule gives Gamma
2/4/6. Its exact static consequences are:

| Scale | Gamma | Gamma/RJ | Product-risk blocks | Direct vars / constraints |
|---|---:|---:|---:|---:|
| S | 2 | 0.020833 | 632 | 122,376 / 18,629 |
| M | 4 | 0.025000 | 25,170 | 8,482,961 / 957,882 |
| L | 6 | 0.020833 | 2,280,612 | 1,425,383,510 / 116,330,402 |

The ceiling makes M slightly more intense than S/L. More importantly, the
rule preserves exposure share by increasing scenario depth, so it conflates
dimension scaling with a sharp combinatorial change. `FIXED_GAMMA_2` is the
pre-result recommendation. This is a design/fairness decision, not a claim
that proportional Gamma is mathematically invalid.

## XL search-box audit

All counts below use fixed Gamma 2:

| Anchor | I/R/J | Pure vars / constraints | Product-risk blocks | Direct vars / constraints | Static status |
|---|---|---:|---:|---:|---|
| XL-low | 30/30/14 | 2,114 / 15,541 | 6,524 | 6,075,177 / 405,479 | ABOVE_CURRENT_GATE |
| XL-mid | 32/33/15 | 2,475 / 19,306 | 8,430 | 9,190,218 / 565,939 | RESOURCE_RISK |
| XL-high | 35/36/16 | 2,880 / 24,193 | 10,672 | 13,843,348 / 780,365 | RESOURCE_RISK |

The Pure global MILP remains modest across this box; the risk comes from the
explicit Direct and structured product-risk constructions. No XL anchor is
currently formal-grid eligible. XL-low is the only proposed development probe,
and only with explicit authorization, process isolation, a 22-GiB memory stop,
and the unchanged 900-second wall guard.

## Probe and freeze policy

The proposed probes are one seed at current L and one seed at XL-low. Direct is
tested first because it is the construction bottleneck. They are development
resource observations only and cannot enter paper statistics or determine the
grid based on algorithm ranking.

The largest scale is frozen only if deterministic generation succeeds, memory
remains controlled, and Pure and PRB are invocable under the common timeout.
Direct timeout is admissible and recorded, but unsafe Direct construction
excludes the entire scale. The default remains three scales, five replicates,
and 60 formal runs. Adding a safe XL would yield 80; increasing to ten
replicates is permitted only under the preregistered sub-60-second/sub-12-GiB
probe rule and before formal execution.

## Remaining authorization prerequisites

Static design readiness is not execution readiness. Before formal runs, a
separate authorized preparation phase must:

1. generate all 15 primitive instances twice and verify canonical hashes;
2. create and stability-audit all Gamma-0 nominal incumbents;
3. freeze all B_ref values and identities;
4. implement a four-method runner with whole-entry T_core wrappers, resource
   monitoring, atomic outputs, and no-overwrite behavior;
5. validate objective equality on tiny generated instances;
6. freeze the final authorization manifest with `formal_run_authorized=false`
   pending explicit approval.

No optimization or instance artifact was produced by this audit.
