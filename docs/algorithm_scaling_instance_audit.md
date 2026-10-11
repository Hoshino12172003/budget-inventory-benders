# Controlled scaling instance audit

## Finding

The existing controlled family is suitable for the new formal protocol without introducing XXXL:

| Label | I | R | J | Seeds | Formal method runs |
|---|---:|---:|---:|---:|---:|
| L10 | 25 | 24 | 12 | 10 | 30 |
| XL10 | 30 | 30 | 14 | 10 | 30 |
| XXL10 | 36 | 36 | 16 | 10 | 30 |

The seeds are frozen at `20260921–20260930`. Instances use the existing deterministic Renault
empirical bootstrap generator and the same eight source cases. Static generation of all 30
primitive instances confirms the frozen `SL=0.90` vector and
`phi_j=1.85 max_r p_rj` penalty rule. Primitive hashes are saved in the static-audit artifact.

## Existing evidence boundary

The repository contains a 90-row large-scale development summary for this same size/seed/method
design. It is useful evidence for choosing the grid and shows that the three-scale family already
exhibits a scaling trend. It is not reused as a new formal result because:

- the records were explicitly marked development-only;
- the raw prepared instances and per-iteration artifacts are not tracked on this code line;
- the old summaries do not carry the complete new config/model/solver identity chain;
- the new protocol requires per-round timing and normalized lower-bound trajectories.

Consequently the formal reuse count is zero. Future execution will deterministically regenerate
and hash 30 prepared instances, then execute 90 paired method conditions.

## Direct reference decision

Direct is not forced onto L10, XL10, or XXL10. Algebraic sizing makes even L10 a multi-million-
variable deterministic-equivalent expansion, while the available machine budget is about 32 GiB.
Without a separately certified safe scale inside this frozen family, the fail-closed choice is
zero Direct runs. This does not change the three-method comparison or add a smaller, scientifically
different scale solely to accommodate Direct.
