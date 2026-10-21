# Direct XXL10 remaining-nine authorization record

Protocol: `DIRECT_XXL10_REMAINING9_V1_METHOD2_THREADS2`

Scope: `DIRECT_XXL10_S20260922` through `DIRECT_XXL10_S20260930`, each at `attempt-001` only.

The protocol is prepared with `formal_run_authorized=false`. Static readiness does not authorize execution. A later, separate authorization commit must change only that field after live identity, Git, worker, RAM, and disk gates pass.

The completed seed-20260921 pilot remains read-only. Its attempt-001 startup failure and attempt-002 `TIME_LIMIT` result are not retries available to this protocol. A solver `TIME_LIMIT` with a feasible incumbent is a canonical time-limited result, never an exact-certified result. No automatic retry is permitted.

Dry-run:

```powershell
python scripts\run_direct_scaling_xxl10_remaining9.py --config experiments\configs\development\direct_scaling_xxl10_remaining9_v1.yaml
```

Execution is forbidden until separately authorized. After authorization, the command would be:

```powershell
python scripts\run_direct_scaling_xxl10_remaining9.py --config experiments\configs\development\direct_scaling_xxl10_remaining9_v1.yaml --execute
```
