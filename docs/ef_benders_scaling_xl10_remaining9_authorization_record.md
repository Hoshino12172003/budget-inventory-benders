# EF-BD XL10 remaining-nine authorization record

## Frozen scope

- Protocol: `EF_BD_XL10_REMAINING9_V1`
- Conditions: `EF_XL10_S20260922` through `EF_XL10_S20260930`
- Attempts: `attempt-001` only
- Completed pilot: `EF_XL10_S20260921/attempt-001` is immutable and excluded from execution
- Authorization: `formal_run_authorized=true`
- Authorization commit: `587ab8ac90eeac3e6e3680a368643176e98f5f83`
- Automatic retry: forbidden

The independent authorization commit changed only the versioned authorization field after repeating the pilot, input, environment, resource, process, Git, and output-absence gates. It did not execute optimization.

## Frozen method and resources

The batch reuses the pilot-certified EF-BD implementation: one global theta, at most one aggregate optimality cut per iteration, and one complete Direct-equivalent recourse LP Oracle. Product risk-budget decomposition, PRB multicut, SG pruning, and the compact Pure oracle remain disabled.

Each condition retains the pilot resource contract: one worker, `Threads=2`, 8 GiB process-tree RSS cap, 12 GiB startup-available-memory gate, 3 GiB system-available-memory floor, 20 GiB free-disk gate, 900-second wall-time limit, and 0.25-second monitoring interval.

Resource or time stops are preserved as failures and may be followed by the next independent condition only after the worker has exited and the next condition passes every preflight gate again. Identity, hash, certification, unknown worker, and archive failures stop the entire batch.

## Commands

Zero-optimization dry-run:

```powershell
python scripts\run_ef_benders_scaling_xl10_remaining9.py --config experiments\configs\development\ef_benders_scaling_xl10_remaining9_v1.yaml
```

After a fresh live dry-run passes every gate, the authorized execution command is:

```powershell
python scripts\run_ef_benders_scaling_xl10_remaining9.py --config experiments\configs\development\ef_benders_scaling_xl10_remaining9_v1.yaml --execute
```
