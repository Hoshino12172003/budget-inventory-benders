# Historical Pure Benders / CCG comparison audit

## Match status

`HISTORICAL_4000S_VS_1S_EXACT_MATCH = NOT_RECOVERED`

Repository-wide history search did not recover a frozen result whose reported
Pure Benders runtime is 4,000+ seconds paired with a 1+ second CCG runtime.
The closest fully attributable Renault experiment is the diagnostic chain on
old repository branch `origin/pr/86`:

- source result commit `b78f6c976984ba22602902ed325eb1442d572ba4`;
- final compact audit commit `0dd11cc5ffe6230eb865d48a31bd68982062ecec`;
- configuration `experiments/configs/benders_ccg_tail_handoff_210202.yaml`;
- runner `src/benders_ccg_tail_handoff_runner.py`;
- Renault case 210202, \(I=15,R=12,J=8,\Gamma=2\), 4,657 scenarios;
- Benders-only run: 1,800.1849 seconds, 2,154 iterations/cuts, time limit,
  uncertified, relative gap 0.0003273020;
- Pure CCG: 1.7698352 seconds, six iterations, five scenarios added, exact
  adversarial final certification.

Both reported runtimes are algorithm-phase totals; the compact record does not
identify a separate post-evaluation component. The CCG implementation is a
restricted scenario-master method with exact global adversarial scenario
generation.

## Equivalence to the new baseline

The historical Benders is not algorithmically identical to the new Pure
baseline. It did use `robust_dual_milp` global separation and one cut per
iteration, but its frozen method was `adaptive_gap_gamma_benders`, variant
`joint_v1_core_point_strengthened`, with core-point cut strengthening,
adaptive precision and historical convergence machinery. The new baseline has
none of those enhancements: it uses a standalone single-theta master, one
unstrengthened aggregate supporting cut from one exact global dual MILP, and a
fixed final global certification contract.

Accordingly, the historical evidence motivates the ablation but must not be
presented as a runtime estimate for the new implementation. No historical
artifact was migrated or modified.
