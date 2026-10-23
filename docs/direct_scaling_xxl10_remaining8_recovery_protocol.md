# Direct XXL10 remaining-eight recovery protocol

Protocol: `DIRECT_XXL10_REMAINING8_RECOVERY_V1_METHOD2_THREADS2`

Scope: `DIRECT_XXL10_S20260923` through `DIRECT_XXL10_S20260930`, each at `attempt-001` only.

The historical remaining-nine batch and its report remain read-only. `DIRECT_XXL10_S20260922` is retained as an executed, non-certified `TIME_LIMIT` result. Its canonical result contains no incumbent (`objective=null`, `best_bound=null`, and `mip_gap=null`), while the solver log records `Solution count 0`. The old report's `STOPPED_INTEGRITY_FAILURE` value is preserved as history; the new audit records the evidence-backed post-hoc classification `TIME_LIMIT_NO_INCUMBENT` without rewriting that report.

`TIME_LIMIT_WITH_INCUMBENT` and `TIME_LIMIT_NO_INCUMBENT` both require a clean Worker exit, no resource stop, complete provenance, and consistent solver evidence. Neither classification is exact-certified success. Partially populated progress fields remain an integrity failure.

The recovery protocol freezes `Threads=2`, `Method=2`, `MIPGap=0`, 900 seconds, 13 GiB process-tree RSS, 16 GiB startup RAM, 3 GiB system-available floor, 20 GiB disk, 0.25-second monitoring, one Worker, and no automatic retry.

It is prepared with `formal_run_authorized=false`; this document is not execution authorization.

Dry-run:

```powershell
python scripts\run_direct_scaling_xxl10_remaining8.py --config experiments\configs\development\direct_scaling_xxl10_remaining8_v1.yaml
```

After a separate authorization commit, the execution command would be:

```powershell
python scripts\run_direct_scaling_xxl10_remaining8.py --config experiments\configs\development\direct_scaling_xxl10_remaining8_v1.yaml --execute
```
