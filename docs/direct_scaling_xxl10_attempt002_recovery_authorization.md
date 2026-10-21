# Direct XXL10 attempt-002 recovery authorization

- Condition: `DIRECT_XXL10_S20260921`
- Prior attempt: `attempt-001`
- Recovery attempt: `attempt-002`
- Failure classification: `WORKER_INNER_GIT_GATE_MISMATCH`
- Recovery authorization: `false`
- Automatic retry: forbidden

The original formal authorization remains historical evidence for `attempt-001`; it does not authorize a recovery attempt. The recovery path requires a separate change of `recovery_control.authorized` from `false` to `true` after the attempt-001 evidence, frozen identities, live resources, Git allowlist, absent canonical, absent attempt-002, and worker-process preflight all pass.

The recovery launcher preserves the byte identity of `experiments/run_direct_scaling.py`. It starts the same frozen Direct solver through a dedicated worker entry so the child process executes the audited, experiment-specific Git allowlist rather than relying on a parent-process monkey-patch.

Dry-run and child-process preflight:

```powershell
python scripts\run_direct_scaling_xxl10_paired_pilot.py --config experiments\configs\development\direct_scaling_xxl10_paired_pilot_v1.yaml
python scripts\run_direct_scaling_xxl10_paired_pilot.py --worker-preflight --config experiments\configs\development\direct_scaling_xxl10_paired_pilot_v1.yaml
```

The following command remains unavailable until a separate recovery authorization commit:

```powershell
python scripts\run_direct_scaling_xxl10_paired_pilot.py --config experiments\configs\development\direct_scaling_xxl10_paired_pilot_v1.yaml --execute
```
