# Renault Enhanced Basic Benders development readiness

Decision: `READY_FOR_AUTHORIZATION`

This protocol is development-only. Authorization is closed, and this audit made zero optimization calls.

## Basic-BD audit

The existing Basic-BD oracle already builds one all-product recourse LP, updates the first-stage supply RHS once per oracle call, updates only demand rows changed by the next enumerated scenario, and repeatedly reoptimizes the same LP. Gurobi can therefore retain the LP basis, although the code does not explicitly save or restore VBasis/CBasis. Scenarios are visited deterministically by cardinality and then lexicographic combination order. Dual coefficients are extracted only when a new worst value is found.

Across the archived eight Basic-BD development runs, oracle work accounts for 98.37% of algorithm core time (range 98.16%–98.68%). The irreducible cost is 4,657 exact LP optimizations per oracle call. The repeated Python construction of global patterns, demand vectors, service totals, and scalar RHS assignments is the engineering overhead targeted here.

## EB-BD design

EB-BD precomputes the complete 4,657-scenario RHS plan once and uses batched RHS writes. It still solves every admissible scenario. It uses the unchanged single-theta master and adds at most one global cut per iteration. It does not import Aggregate-BD or PRB-BD, does not compose product risk budgets, does not add product cuts, and does not invoke the compact Global-BD adversarial MILP.

The optimization changes execution overhead only; it provides no guarantee that EB-BD runtime will lie between Direct and Aggregate-BD.

## Frozen scope and resources

- Cases: 210202, 210628, 210129, 210310, 210330, 210323, 210428, 210611.
- Gamma=2, lambda_R=0.05, frozen x0, B_ref, instances, and solver tolerances.
- 300 seconds per case, 4 GiB process tree, 8 GiB startup memory, 3 GiB system floor, 20 GiB disk gate, 0.25-second monitoring, sequential execution, no automatic retry.
- Dry-run snapshot: 11.820 GiB available RAM and 246.298 GiB free disk.

## Validation status

Static tests cover exact scenario completeness, RHS-plan equivalence, forbidden dependency absence, frozen identities, resource gates, attempt protection, and closed authorization. A tiny Direct-versus-EB exact test is implemented behind `RUN_EB_BD_OPTIMIZATION_TESTS=1`; it was intentionally not executed during this zero-optimization preparation stage.

The comparison template reads existing evidence directly and leaves all EB-BD numeric cells pending. Renault 210330 PRB remains excluded from valid development pairing because its internal global risk-budget coupling certification failed.

## Commands

Dry-run:

```powershell
python experiments\run_renault_enhanced_basic_benders.py --config experiments\configs\development\renault_enhanced_basic_benders_v1.yaml --dry-run
```

Execution after a separate authorization commit:

```powershell
python experiments\run_renault_enhanced_basic_benders.py --config experiments\configs\development\renault_enhanced_basic_benders_v1.yaml --execute
```
