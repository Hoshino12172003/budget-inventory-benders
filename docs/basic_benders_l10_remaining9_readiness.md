# Basic-BD L10 remaining-nine readiness

Decision: `READY_FOR_AUTHORIZATION`

Authorization remains false and the dry-run made zero optimization calls.

## Fixed scope

- Conditions: `BASIC_L10_S20260922` through `BASIC_L10_S20260930` (nine fixed denominator conditions).
- Each next identity is `attempt-001`; no attempt or canonical output currently exists for the nine conditions.
- The certified `BASIC_L10_S20260921 / attempt-001` archive remains unchanged.

## Resource contract

- 900 seconds, 4 GiB process tree, 7 GiB startup gate, 3 GiB system floor, 20 GiB disk gate, and 0.25-second monitoring. Snapshot available RAM: 13.806 GiB; free disk: 246.313 GiB.
- Conditions run serially in seed order. Resource/time failures are preserved and may continue only after worker exit and renewed gates. Identity, hash, numerical-certification, or unknown worker failures stop the batch immediately.

## Execution command after a separate authorization commit

```powershell
python scripts\run_basic_benders_scaling_l10_remaining9.py --config experiments\configs\development\basic_benders_scaling_l10_remaining9_v1.yaml --execute
```
