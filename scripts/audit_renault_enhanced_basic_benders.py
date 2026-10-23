from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.run_renault_enhanced_basic_benders import DEFAULT_CONFIG, build_dry_run


OUTPUT = ROOT / "artifacts/renault_enhanced_basic_benders_readiness.json"
REPORT = ROOT / "docs/renault_enhanced_basic_benders_design.md"
BASIC_PILOT_ROOT = ROOT / "experiments/results/renault_vanilla_bd_pilot_210202_development_v1"
BASIC_REMAINING_ROOT = ROOT / "experiments/results/renault_vanilla_bd_remaining7_development_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(root: Path) -> dict:
    manifest = root / "sha256.txt"
    failures = []
    entries = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = root / relative
        entries += 1
        if not path.is_file() or sha256(path) != expected:
            failures.append(relative)
    return {
        "path": str(manifest.relative_to(ROOT)),
        "sha256": sha256(manifest),
        "entries": entries,
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def basic_profile() -> dict:
    pilot = json.loads((BASIC_PILOT_ROOT / "summary.json").read_text(encoding="utf-8"))
    rows = {"210202": pilot["vanilla"]}
    for case_id in ("210628", "210129", "210310", "210330", "210323", "210428", "210611"):
        rows[case_id] = json.loads(
            (BASIC_REMAINING_ROOT / case_id / "vanilla_outcome.json").read_text(encoding="utf-8")
        )
    case_rows = {
        case_id: {
            "algorithm_seconds": result["algorithm_seconds"],
            "oracle_seconds": result["oracle_seconds"],
            "oracle_share": result["oracle_seconds"] / result["algorithm_seconds"],
            "iterations": result["iterations"],
        }
        for case_id, result in rows.items()
    }
    return {
        "cases": case_rows,
        "mean_oracle_share": sum(row["oracle_share"] for row in case_rows.values()) / len(case_rows),
        "minimum_oracle_share": min(row["oracle_share"] for row in case_rows.values()),
        "maximum_oracle_share": max(row["oracle_share"] for row in case_rows.values()),
    }


def build_audit() -> dict:
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    dry = build_dry_run(DEFAULT_CONFIG)
    implementation = (
        ROOT / "src/robust_inventory_reconfiguration/enhanced_basic_benders.py"
    ).read_text(encoding="utf-8")
    basic_source = (
        ROOT / "experiments/run_renault_vanilla_bd_pilot.py"
    ).read_text(encoding="utf-8")
    history = {
        "pilot_210202": verify_manifest(BASIC_PILOT_ROOT),
        "remaining_seven": verify_manifest(BASIC_REMAINING_ROOT),
    }
    checks = {
        "authorization_closed": config["formal_run_authorized"] is False,
        "exact_eight_case_scope": len(dry["conditions"]) == 8,
        "all_frozen_identities": dry["gates"]["all_case_identities"],
        "no_existing_attempts": dry["gates"]["all_attempts_absent"],
        "no_existing_canonical_results": dry["gates"]["all_canonical_results_absent"],
        "all_candidates_enumerated": "for plan in self.plans:" in implementation,
        "no_candidate_pruning": '"candidate_pruning": False' in implementation,
        "batched_rhs_updates": "setAttr(GRB.Attr.RHS" in implementation,
        "scenario_rhs_precomputed": "build_scenario_rhs_plans" in implementation,
        "single_lp_reused": "self.model.optimize()" in implementation,
        "basic_already_reused_lp": "self.model.optimize()" in basic_source,
        "basic_already_updated_rhs": ".RHS =" in basic_source,
        "no_aggregate_import": "standard_benders import" not in implementation,
        "no_prb_import": "product_risk_budget_benders import" not in implementation,
        "historical_basic_manifests": all(row["status"] == "PASS" for row in history.values()),
        "zero_optimization_dry_run": dry["optimization_calls"] == 0,
    }
    readiness_gates = {
        **dry["gates"],
        "static_algorithm_checks": all(checks.values()),
    }
    return {
        "schema": "renault_enhanced_basic_benders_readiness_v1",
        "status": "STATIC_AUDIT_PASS" if all(checks.values()) else "STATIC_AUDIT_FAIL",
        "decision": "READY_FOR_AUTHORIZATION" if all(readiness_gates.values()) else "BLOCKED",
        "formal_run_authorized": config["formal_run_authorized"],
        "optimization_calls": 0,
        "basic_bd_audit": {
            "existing_mechanisms": [
                "one reusable all-product LP per oracle object",
                "supply RHS update once per first-stage point",
                "demand RHS updates limited to the scenario symmetric difference",
                "successive LP reoptimization permits native basis reuse",
                "dual extraction only for a new incumbent worst scenario",
                "deterministic cardinality-then-lexicographic combination ordering",
                "no explicit VBasis/CBasis assignment; warm reuse is native reoptimization of the unchanged LP",
            ],
            "observed_bottleneck": "all 4657 scenario LP optimizations are mandatory on every oracle call; Python-side scenario/RHS preparation is repeated on every call",
            "historical_profile": basic_profile(),
            "historical_evidence": history,
        },
        "eb_bd_design": {
            "changes": [
                "precompute all 4657 exact global scenario demand/service RHS plans once",
                "write supply, demand, and service RHS vectors through batched Gurobi setAttr calls",
                "retain the same reusable all-product LP and all candidate solves",
            ],
            "correctness_boundary": [
                "one global theta",
                "at most one global optimality cut per iteration",
                "no product risk-budget composition",
                "no product multicut",
                "no compact Global-BD adversarial MILP",
                "no scenario pruning or skipped candidate",
            ],
        },
        "checks": checks,
        "readiness_gates": readiness_gates,
        "dry_run": dry,
        "sha256": {
            "config": sha256(DEFAULT_CONFIG),
            "implementation": sha256(ROOT / "src/robust_inventory_reconfiguration/enhanced_basic_benders.py"),
            "runner": sha256(ROOT / "experiments/run_renault_enhanced_basic_benders.py"),
            "comparison_builder": sha256(ROOT / "scripts/summarize_renault_enhanced_basic_benders.py"),
        },
    }


def write_outputs() -> dict:
    audit = build_audit()
    OUTPUT.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    dry = audit["dry_run"]
    resources = dry["resource_snapshot"]
    REPORT.write_text("\n".join([
        "# Renault Enhanced Basic Benders development readiness",
        "",
        f"Decision: `{audit['decision']}`",
        "",
        "This protocol is development-only. Authorization is closed, and this audit made zero optimization calls.",
        "",
        "## Basic-BD audit",
        "",
        "The existing Basic-BD oracle already builds one all-product recourse LP, updates the first-stage supply RHS once per oracle call, updates only demand rows changed by the next enumerated scenario, and repeatedly reoptimizes the same LP. Gurobi can therefore retain the LP basis, although the code does not explicitly save or restore VBasis/CBasis. Scenarios are visited deterministically by cardinality and then lexicographic combination order. Dual coefficients are extracted only when a new worst value is found.",
        "",
        f"Across the archived eight Basic-BD development runs, oracle work accounts for {audit['basic_bd_audit']['historical_profile']['mean_oracle_share']:.2%} of algorithm core time (range {audit['basic_bd_audit']['historical_profile']['minimum_oracle_share']:.2%}–{audit['basic_bd_audit']['historical_profile']['maximum_oracle_share']:.2%}). The irreducible cost is 4,657 exact LP optimizations per oracle call. The repeated Python construction of global patterns, demand vectors, service totals, and scalar RHS assignments is the engineering overhead targeted here.",
        "",
        "## EB-BD design",
        "",
        "EB-BD precomputes the complete 4,657-scenario RHS plan once and uses batched RHS writes. It still solves every admissible scenario. It uses the unchanged single-theta master and adds at most one global cut per iteration. It does not import Aggregate-BD or PRB-BD, does not compose product risk budgets, does not add product cuts, and does not invoke the compact Global-BD adversarial MILP.",
        "",
        "The optimization changes execution overhead only; it provides no guarantee that EB-BD runtime will lie between Direct and Aggregate-BD.",
        "",
        "## Frozen scope and resources",
        "",
        "- Cases: 210202, 210628, 210129, 210310, 210330, 210323, 210428, 210611.",
        "- Gamma=2, lambda_R=0.05, frozen x0, B_ref, instances, and solver tolerances.",
        "- 300 seconds per case, 4 GiB process tree, 8 GiB startup memory, 3 GiB system floor, 20 GiB disk gate, 0.25-second monitoring, sequential execution, no automatic retry.",
        f"- Dry-run snapshot: {resources['available_memory_gib']:.3f} GiB available RAM and {resources['free_disk_gib']:.3f} GiB free disk.",
        "",
        "## Validation status",
        "",
        "Static tests cover exact scenario completeness, RHS-plan equivalence, forbidden dependency absence, frozen identities, resource gates, attempt protection, and closed authorization. A tiny Direct-versus-EB exact test is implemented behind `RUN_EB_BD_OPTIMIZATION_TESTS=1`; it was intentionally not executed during this zero-optimization preparation stage.",
        "",
        "The comparison template reads existing evidence directly and leaves all EB-BD numeric cells pending. Renault 210330 PRB remains excluded from valid development pairing because its internal global risk-budget coupling certification failed.",
        "",
        "## Commands",
        "",
        "Dry-run:",
        "",
        "```powershell",
        "python experiments\\run_renault_enhanced_basic_benders.py --config experiments\\configs\\development\\renault_enhanced_basic_benders_v1.yaml --dry-run",
        "```",
        "",
        "Execution after a separate authorization commit:",
        "",
        "```powershell",
        "python experiments\\run_renault_enhanced_basic_benders.py --config experiments\\configs\\development\\renault_enhanced_basic_benders_v1.yaml --execute",
        "```",
    ]) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    audit = write_outputs()
    print(json.dumps({
        "status": audit["status"],
        "decision": audit["decision"],
        "formal_run_authorized": audit["formal_run_authorized"],
        "conditions": len(audit["dry_run"]["conditions"]),
        "optimization_calls": audit["optimization_calls"],
    }, indent=2))
