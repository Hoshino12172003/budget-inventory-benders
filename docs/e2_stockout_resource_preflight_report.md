# E2 Stockout Full-Case Resource Preflight and Admission Report

## Scope and classification

This report covers the explicitly authorized non-publishable resource and
recovery preflight for Renault case `210202` and policy
`EXISTING_CANONICAL_210202`. It is not a paper result and does not authorize or
start any of the 16 formal evaluation tasks.

- classification: `PREFLIGHT_NON_PUBLISHABLE`;
- first stage: fixed and hash-checked before and after evaluation;
- scenarios: all 4,657 frozen IDs under `Gamma=2`;
- product-local recourse blocks: 632/632;
- execution: serial, Gurobi `Threads=1`;
- formal authorization: `false` throughout.

## Scientific policy confirmation

The user confirmed the two independent configurations in
`docs/e2_stockout_scientific_policy_confirmation.md`:

- Baseline = `EXISTING_CANONICAL_<case>`;
- Robust = later exactly certified `ROBUST_EQUIVALENT_SCAL_BASE_<case>`, with
  its true `SERVICE_CALIBRATION_ROBUSTNESS_V2` lineage retained;
- Nominal has the same coordinates as Baseline and remains only a validation
  label.

The original E2 Nominal and original E1/E2 Robust coordinates remain
unrecovered. Nothing in this confirmation relabels SCAL_BASE as a historical
coordinate recovery.

## Frozen preflight identity

| Item | Frozen value |
|---|---|
| Instance SHA-256 | `3827d86c5ec4e290ba7d091648dbe4e1501648bfda54ca485385889e9143ecee` |
| Policy coordinate SHA-256 | `608c0e17ebdc96e2594050536131ac649c8487e54a5dc47c1a9eb02f3860963a` |
| Preflight authorization SHA-256 | `bc92da739b66fe560f42e0561a341f7f70e3b6f04ec188673141975f1f9152c9` |
| Runner SHA-256 | `f37e469a2697fc6ce04b1047ba95170cdf22bce5e31c442728927bbf1d933fc4` |
| Evaluator SHA-256 | `54f2fd55ab0d3463c52ea5312f5eb4fbd3ee116e1a6558c79ae798545413e556` |
| Block-order SHA-256 | `d152dc49d113c8fdf7db80ee855576d38955d1f609b63719e4489f08cd628364` |
| Solver | Gurobi `13.0.1`, `Threads=1` |

The authorization also freezes the policy/instance manifests, scenario order,
scenario-ID order, protocol, checkpoint schema, scientific confirmation, and
all evaluator dependencies.

## Interrupted-checkpoint recovery evidence

The run was deliberately stopped after the predeclared 16th block. The first
checkpoint contained only the exact frozen 16-block prefix, had a matching
sidecar digest, contained no complete evaluation or formal-result fields, and
was marked `INTERRUPTED_BY_PROTOCOL`.

The resume command revalidated that digest, every code/config/instance/policy
identity, and the exact completed prefix before beginning block 17. The final
checkpoint records:

| Segment | Start | End | Runtime | Peak RSS | End reason |
|---|---:|---:|---:|---:|---|
| Initial | 0 | 16 | 0.3903 s | 35,782,656 bytes | `PREDECLARED_PROTOCOL_INTERRUPT` |
| Resume | 16 | 632 | 18.2974 s | 40,067,072 bytes | `ALL_REMAINING_BLOCKS_COMPLETE` |

This demonstrates recovery from an incomplete checkpoint, not merely reading a
completed checkpoint. Checkpoint writes use same-directory temporary files,
atomic replacement, and bounded retry; corrupt digests and identity mismatches
fail closed.

## Resource and result integrity

| Measure | Result |
|---|---:|
| Total measured solver/runtime | 18.6877 s |
| Peak process RSS | 40,067,072 bytes (about 38.2 MiB) |
| Checkpoint plus digest size | 8,734,061 bytes (about 8.33 MiB) |
| Economic block statuses | 632 `OPTIMAL` |
| Reporting tie-break statuses | 632 `OPTIMAL` |
| Scenario rows | 4,657 complete and `OPTIMAL` |
| Checkpoint SHA-256 | `67c064a0b7d6c3a6fbdb0831a942331d4f0f7214cef37f009143c5b69c6d097b` |
| Result-manifest SHA-256 | `1a18f43f2c7b91d0825d312edfb38db2a614fd5a45f58962659882b4befd7a20` |

Independent validation reconstructed all scenario identities and shock sets,
verified before/after first-stage coordinate hashes, required all product keys
and finite metrics, reconciled shipment/shortage/service totals, reconciled
transportation plus shortage plus service penalty with recourse cost, enforced
the economic tie-break band, and recomputed the complete-set summary. Maximum
shortage, maximum service excess, maximum shortage penalty, and maximum
economic recourse cost remain four separate selectors. No preflight metric is
admitted to a paper table.

## Failed and superseded attempts

`experiments/audits/e2_stockout_preflight_failed_attempt.json` retains the
non-paper audit trail:

1. A newly added absolute-delta guard incorrectly rejected a reporting solution
   that was economically lower than the first LP objective by `1.1880106e-6`.
   The correction records the lower feasible cost in both evaluator paths and
   continues to reject positive upper-band violations; no model or tolerance
   changed.
2. A Windows in-place checkpoint write returned `OSError 22`. The last file was
   intact and digest-valid, but the write path was replaced with atomic writes
   before restarting.
3. Two numerically complete runs were discarded after intentional additions to
   the frozen verifier/identity chain changed runner SHA. Neither was reused as
   final evidence.

The final admitted output was rerun from zero under the final frozen identity.

## Scoped regression gate

The frozen gate in
`experiments/configs/e2_stockout_scoped_regression_gate.json` passed:

- scoped E2/scenario/recourse/first-stage/Renault tests: **73 passed**;
- current full suite: **416 passed, 32 failed, 11 errors**;
- exact PR base `ed240826...`: **377 passed, 33 failed, 11 errors**;
- current failed/error node set: 43 nodes, SHA-256
  `a58ad07b82018019017079784b23711d384347d09b9a4e4f1bd55cf704efd483`;
- base failed/error node set: 44 nodes, SHA-256
  `8d30726497ddc4fea5e3b90bad6666ec0f1f22ca7f650964f88e17fa2ce1885a`;
- base-only node: `tests/test_e2_protocol.py::test_e2_identity_and_reuse_contract`;
- current-only failed/error nodes: none.

The 43 remaining historical nodes are listed by exact name in
`docs/e2_stockout_blocker_remediation_review.md` and remain classified as:

- identity/freeze contracts: 11 failures and 11 E7 setup errors;
- missing archived/development inputs: 19 failures;
- missing temporary provenance fixture source: 1 failure;
- pre-existing absolute-path provenance: 1 failure.

No historical result or authorization was modified to make these tests pass,
and the full repository suite is not described as green.

## Admission conclusion and prepared formal checklist

**`APPROVE_FOR_MANUAL_AUTHORIZATION`** is supported for a separate future
authorization action. Scientific policy definition, full-case resource and
recovery preflight, identity validation, cost reconciliation, and the scoped
regression gate have passed.

The current supplemental authorization deliberately remains locked:

- `formal_run_authorized=false`;
- `authorization_transition=[false]`;
- `authorized_task_ids=[]`;
- all identity/scenario/policy formal flags remain `false`;
- no formal result directory exists.

A later, explicit authorization must atomically freeze `[false,true]`, all 16
planned task IDs, the two selected policies only, and the then-current hashes.
Only after that reviewed change may the formal command be run:

```powershell
$env:PYTHONPATH='src'
python experiments/run_e2_stockout_common_scenario.py formal-run
```

For an interrupted authorized formal run, the separate recovery command is:

```powershell
$env:PYTHONPATH='src'
python experiments/run_e2_stockout_common_scenario.py resume-formal
```

Both commands must continue to refuse execution under the files delivered by
this PR. This report does not grant that later authorization.
