# EF-BD XXL10 remaining-nine authorization record

- Protocol: `EF_BD_XXL10_REMAINING9_V1`
- Scope: `EF_XXL10_S20260922` through `EF_XXL10_S20260930`
- Expected attempt for every condition: `attempt-001`
- Completed pilot excluded from scope: `EF_XXL10_S20260921 / attempt-001`
- Authorization: `formal_run_authorized=false`
- Automatic retry: forbidden

The protocol inherits the certified XXL10 pilot algorithm, solver environment, tolerances, and frozen Scaling V2 inputs. Each condition uses a 13-GiB process-tree cap, 17-GiB startup gate, 3-GiB system-available floor, 20-GiB disk gate, 900-second limit, two threads, and a 0.25-second monitor interval. Conditions run sequentially with one worker.

Resource or time stops remain failed attempts and may continue only after the worker has exited and the next condition passes every preflight gate. Identity, hash, certification, archive, monitoring, or unknown worker failures stop the batch. No condition is retried automatically.

Dry-run:

```powershell
python scripts\run_ef_benders_scaling_xxl10_remaining9.py --config experiments\configs\development\ef_benders_scaling_xxl10_remaining9_v1.yaml
```

Execution remains unavailable until an independent authorization changes only `formal_run_authorized` to `true` and all live gates pass:

```powershell
python scripts\run_ef_benders_scaling_xxl10_remaining9.py --config experiments\configs\development\ef_benders_scaling_xxl10_remaining9_v1.yaml --execute
```
