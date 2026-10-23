# Direct scaling L10 formal authorization

## Scope

The user authorized exactly ten Direct Gurobi formal conditions on 2026-10-17:

- scale: `L10` (`I=25`, `R=24`, `J=12`)
- seeds: `20260921` through `20260930`
- condition IDs: the ten `DIRECT_L10_S<seed>` entries in the formal config

`XL10` and `XXL10` remain unauthorized. The runner enforces the condition allowlist in both parent and worker processes, and `--execute-all` means all authorized conditions rather than all 30 configured conditions.

## Frozen execution contract

- Python 3.12.7; gurobipy/native Gurobi 13.0.1.
- The historical Scaling V2 software version remains `NOT_VERIFIABLE`; this run claims protocol-level comparability, not exact historical environment identity.
- Formal solver profile `gurobi-balanced-1e-8-v1`; no parameter, model, instance, objective, constraint, tolerance, seed, or scientific setting is changed.
- Sequential execution only, without MIP starts.
- Per-condition limits remain 7 GiB minimum available RAM, 4 GiB process-tree RSS, 3 GiB minimum system-available RAM, and 900 seconds.
- A new conservative 20 GiB free-disk launch gate is recorded explicitly; the audit observed substantially more free space.
- Existing output is never overwritten. The Renault archive and all Scaling V2 source artifacts are outside the Direct output root.

This authorization changes only the execution gate and its fail-closed routing controls. It does not itself execute optimization.
