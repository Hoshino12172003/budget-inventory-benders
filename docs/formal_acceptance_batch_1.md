# Formal acceptance batch 1

This batch authorizes exactly five runs, A1-A5, for Renault case `210202`.
It does not authorize case `210628`, synthetic scaling, or any remaining E1-E7
cell. The full formal configs retain `formal_run_authorized=false`.

The acceptance manifest is an exact run-ID allowlist. The runner refuses
parameter, case, solver-profile, output-path, or authorization drift; refuses to
overwrite an existing attempt; and stops at the first failed contract. Failed
attempt artifacts are retained.

A1 and A2 compare Direct and PRB at `beta=1`, `B=84614.30513135393`,
`Gamma=2`, and `lambda_R=0.05`. A3 fixes `x=x0`; A4 uses `Gamma=0` with
reconfiguration allowed; A5 uses `Gamma=2` with reconfiguration allowed.

Each run writes one formal-schema result and a separate provenance record. The
latter binds the acceptance run ID, authorization manifest, formal config,
source, processed instance, `x0`, calibration evidence, parameter freeze, Git
commit, solver profile/version, Python version, timestamp, hostname, and platform.
