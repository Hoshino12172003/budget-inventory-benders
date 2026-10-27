# E2 Stockout Scientific Policy Confirmation

## Decision

The user explicitly confirmed the scientific policy definition for the E2
stockout supplement on 2026-10-27:

1. Baseline is `EXISTING_CANONICAL_<case>`.
2. Robust is `ROBUST_EQUIVALENT_SCAL_BASE_<case>`, accepted as a later exactly
   certified robust inventory configuration with its true
   `SERVICE_CALIBRATION_ROBUSTNESS_V2` lineage retained. It is not described as
   recovery of the original E1 or E2 coordinates.
3. Canonical Nominal has the same `x/y/a+/a-` coordinates as Baseline in all
   eight cases. It remains an identity-validation label and is not a third
   independent policy or a scheduled evaluation task.

This confirmation approves the two-policy scientific definition only. It does
not authorize any of the 16 formal case-policy tasks. All formal authorization
flags remain `false` until a separate instruction.

## Frozen identity evidence

The complete source paths, source-run IDs, coordinate-component hashes,
instance hashes, certification paths, provenance hashes, E2 aggregate checks,
inventory totals, warehouse decisions, and first-stage cost components remain
in `artifacts/e2_stockout_policy_identity_manifest.json`. The decisive hashes
are listed below; all values are full SHA-256.

| Case | Instance | Baseline = Nominal coordinates | SCAL_BASE coordinates | SCAL_BASE solution source | SCAL_BASE certification result |
|---|---|---|---|---|---|
| 210129 | `edf794ef39b51c9a84ccdd6e03301e30a24236dee645722a27ff36668e5941d3` | `7f1c1ec2c945cf3671f63d2d6084c28e1574c5422813b1f09f169ef7cf1e7cca` | `d0578e48d010904d1aff85a894f63197b9ab011b5c6de6d54600debedfcf2737` | `f5918ffca080b91e680362f7b1c5c252d54314d10ceb826569a2cbb310e1f2bc` | `131632ec86953300accfed96c960871366d390a324d811ea088357e7a2ee7b29` |
| 210202 | `3827d86c5ec4e290ba7d091648dbe4e1501648bfda54ca485385889e9143ecee` | `608c0e17ebdc96e2594050536131ac649c8487e54a5dc47c1a9eb02f3860963a` | `12c4fb2c017cddc9355aae458af94c8a1c26902e5204464b2dcb6aae6db52458` | `b2dc3b97a866d95c36b0bb9f285a71b332269212587c7e4ef97b89e8c886c1b0` | `4f5d13174b9d1d4b743c36c22f51bd14d2e006409375ac719e86f7a15b36e674` |
| 210310 | `cea7e89477816218fba3021b71a791fa9f86714cecf253f8a58bb477ce2ddad8` | `a7040d6d8d5689c1929a35caeeadb91d95ac99c5421b376b1ca7d9e89ef14776` | `941f1507aeaa9c507ee8205ccebc238086e898ba0df44e7792b24bee99f4a67f` | `82834730a17d2aa046389f198da47b53aa91167ade2a796d5542df74cdd67dce` | `1a563e44427ea5240c1c10b8cb7e19c3f926dbc42ef5ceee47e005f6574459a3` |
| 210323 | `df5fcbaa54a73277948f676fae151d85ad621d9ef417b0906b04066b1ef1109c` | `18f36ad865f2957c6134617a5e52635c3005c37509bc93c208bc549ff07ac496` | `4583b9eef023ffa2cc0eb96a34534180b1f178b1b56cc3ef1733ad723689f857` | `851b3d881d152eb443f20dbe5b3eae176866f5f6ad402ad7c282648e6b19d0bb` | `8baeada5a736cfefcade9996e137be008cd127027127f2aa4c752b056fccb7b0` |
| 210330 | `5c89a9e3151a8372f2be5884130cfc9b6eb84347fd132456527a7fdc984857a1` | `c39d687b4b63901f07e0ef84602a12de824baed53ca8fde1f7c520f316f84832` | `127a10f2ff7af50765151bc1a65772780f74c2fa5f138e62f8af4737570d315e` | `2eb9e44f9d879b9924ae9a844deddb2c711e2995f48ecd750e6b8e1bb7483637` | `3865c2b08df77ad294293df09ce9660d3f9ecd5cd7c77c24ffc4297918300e19` |
| 210428 | `56c76844228179cf3b69827daeb25e4494f2f7435ea4d2335af79102117ce0d7` | `bde8646c6c0db8ae661952596e1fe468f7912b7c53f57ab17c176f6dfd3325f8` | `115dc218627882cd97d0ca4683880c244fb76ee9b6cbda61206f7c610957c3fe` | `5cf1b31281d1a1ffb6df6f867d008504aec209fba3842850d522520034ec61f7` | `f181b1cafca87ed928bcbd749084dbe976637e261cc8cb702f1283f0b8d9dfb2` |
| 210611 | `f244641d602348af8b2ac31a2bb948b4b0ebca8e33ff446dd07298e3e578a9bf` | `892812b40286d821ff107f48bc829d6653069ee2424d9fde65dbda4c7acecb17` | `02103fa83b872738ab4a57b9aa9824d591e20942f48c1867d08c3346a1785e24` | `e16fdd8b1b133cce1804e18723291e92c61c7e5c0ab5bcb93711f60e8f0bb349` | `d78aaf3026e7142212acb5a80441027fb24f8c3215b6fb41668147ab28aa606b` |
| 210628 | `25cf7a38ce49c8380c51830a8fbbb92bad000e4b90c568576a3d0be44f2b7677` | `763ae4f6b1eade52c018765f6cc9ae1d6931a07ab2fc6a06e8f9eebb4c55749e` | `207627c2c490231129c254805ca2c35a7bd26d1d5d3290204b0a3eedcdcffda2` | `d120d26eda9438b1530668ba17ceb0b0cdbededc7a033d17c5d23a23d6d4fc0e` | `67b1cd6ae40eb2da9932d5c012834f0171cbd42ebb63ef7152f1bb7c6ae293b4` |

For all eight Robust candidates, the recorded solver status is `OPTIMAL` and
the exact certification is `CERTIFIED_PRB_EXACT`. These statements certify the
later SCAL_BASE solutions only; they do not expand the conclusion to missing
historical E1/E2 coordinate files.
