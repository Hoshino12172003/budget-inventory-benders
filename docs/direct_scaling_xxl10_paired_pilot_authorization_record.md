# Direct XXL10 paired-pilot authorization record

- Protocol: `DIRECT_XXL10_PAIRED_PILOT_V1_METHOD2_THREADS2`
- Condition: `DIRECT_XXL10_S20260921`
- Attempt: `attempt-001`
- Frozen source: `ASC_INSTANCE_XXL10_S20260921`
- Authorization: `formal_run_authorized=false`
- Automatic retry: forbidden

The Direct pilot is independently authorization-closed. Its authorization cannot enable the EF-BD pilot. The protocol retains the frozen Direct model, tolerances, `Method=2`, `Threads=2`, 13-GiB process-tree cap, 16-GiB startup gate, 3-GiB system floor, 20-GiB disk gate, 900-second limit, and 0.25-second monitor interval.

The current 32-GiB computer is not presumed sufficient. Static model size and historical XL10 peaks indicate high root-node Barrier/Crossover memory risk. A later authorization may permit one monitored attempt only after the live 16-GiB startup gate and every identity gate pass.

Dry-run:

```powershell
python scripts\run_direct_scaling_xxl10_paired_pilot.py --config experiments\configs\development\direct_scaling_xxl10_paired_pilot_v1.yaml
```

Execution remains unavailable until a separate authorization changes only this protocol's authorization field:

```powershell
python scripts\run_direct_scaling_xxl10_paired_pilot.py --config experiments\configs\development\direct_scaling_xxl10_paired_pilot_v1.yaml --execute
```
