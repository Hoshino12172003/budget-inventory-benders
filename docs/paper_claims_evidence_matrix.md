# Paper claims evidence matrix

| Claim or output | Evidence level | Decision | Required wording |
|---|---|---|---|
| Original E1a PRB was faster than Direct in 8/8 Renault cases | `HISTORICAL_SUMMARY_ONLY` + `SOURCE_MISSING` | Remove as confirmatory claim | “A historical derivative reported 8/8; original PRB result files are unavailable.” |
| Original E1a PRB geometric-mean speedup was 2.225 | `HISTORICAL_SUMMARY_ONLY` | Supplement/history only | Do not quote as a verified performance estimate. |
| Original E1a PRB iterations and cuts | `HISTORICAL_SUMMARY_ONLY` | Supplement/history only | State that source diagnostics cannot be independently inspected. |
| Renault PRB objective values | `DEVELOPMENT_CROSSCHECK` for later batch; E1a remains historical | Retain as corroborated values | “A later batch on identical instance identities reproduced 8/8 objectives; 7/8 passed strict certification.” |
| Renault 210330 PRB certification | `DEVELOPMENT_CROSSCHECK` FAIL | Retain failure | Never substitute objective agreement for coupling certification. |
| E1b Standard/Aggregate standalone results | `PRIMARY_VERIFIED` where recovered raw chain is present | Retain | Cite their own result/provenance chain. |
| E1b PRB comparison cells | `HISTORICAL_SUMMARY_ONLY` | Mark or remove from confirmatory table | Disclose that E1b reused missing E1a sources. |
| E1c Renault empirical anchor | `HISTORICAL_SUMMARY_ONLY` | Mark or omit | Scaling-only evidence remains separate. |
| E2-E7 reused baseline cells | Mixed; inherited cells historical | Cell-level disclosure | Identify source experiment and reuse status. |
| E2-E7 independently solved cells | `PRIMARY_VERIFIED` or `SECONDARY_RECOMPUTABLE` after their own audit | Retain | Do not generalize evidence status from neighboring reused cells. |
| Scaling V2 certification | Independent | Retain 89/90 | Preserve the Pure-BD XXL10 seed 20260925 failure. |
| XXL10 four-method record matrix | Independent | Retain 40/40 records | Preserve Direct 3/10 exact and the three other methods at 10/10; limited Direct runs remain limited. |
| PRB-BD versus Aggregate-BD on source-complete scaling data | Independent | Retain | Do not attach the E1a limitation to independent paired records. |

## Evidence hierarchy enforcement

`PRIMARY_VERIFIED` and `SECONDARY_RECOMPUTABLE` may support formal claims.
`HISTORICAL_SUMMARY_ONLY` and `DEVELOPMENT_CROSSCHECK` may explain provenance
or corroboration but cannot be combined to simulate missing primary evidence.
`SOURCE_MISSING` is always disclosed.
