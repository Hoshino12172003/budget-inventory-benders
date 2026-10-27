from __future__ import annotations

import copy
import ast
import hashlib
import json
import math
import os
import platform
import threading
import time
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from .first_stage_solution import (
    load_first_stage_solution_artifact,
    matrix_from_artifact,
)
from .instance import InventoryInstance, load_instance
from .robust_service import canonical_fixed_inventory
from .scenarios import enumerate_scenario_components, scenario_count
from .solver_profile import (
    FORMAL_SOLVER_NATIVE_PROFILE,
    FORMAL_SOLVER_PROFILE_ID,
    apply_formal_solver_profile,
)


GAMMA = 2
FORMAL_SCENARIO_COUNT = 4657
REPORTING_TIE_BREAK_TOLERANCE = 1e-7
PILOT_MAX_SCENARIOS = 8
FORBIDDEN_FIRST_STAGE_CALLS = (
    "solve_prb_benders",
    "solve_exact_reconfiguration",
    "build_exact_reconfiguration_model",
    "optimize_first_stage",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coordinate_payload(
    y: list[int],
    x: list[list[float]],
    a_plus: list[list[float]],
    a_minus: list[list[float]],
) -> dict[str, Any]:
    return {"y": y, "x": x, "a_plus": a_plus, "a_minus": a_minus}


def coordinate_sha256(
    y: list[int],
    x: list[list[float]],
    a_plus: list[list[float]],
    a_minus: list[list[float]],
) -> str:
    return canonical_sha256(coordinate_payload(y, x, a_plus, a_minus))


def scenario_payload(instance: InventoryInstance, gamma: int = GAMMA) -> list[list[list[str]]]:
    return [
        [[instance.region_ids[r], instance.product_ids[j]] for r, j in scenario]
        for scenario in enumerate_scenario_components(instance, gamma)
    ]


def scenario_manifest_sha256(instance: InventoryInstance, gamma: int = GAMMA) -> str:
    return canonical_sha256(scenario_payload(instance, gamma))


def scenario_id(index: int) -> str:
    return f"S{index:04d}"


def scenario_id_order_sha256(count: int = FORMAL_SCENARIO_COUNT) -> str:
    return canonical_sha256([scenario_id(index) for index in range(count)])


@dataclass(frozen=True)
class FrozenPolicy:
    policy_id: str
    case_id: str
    lineage: str
    source_path: Path
    source_run_id: str
    certification_source_path: Path
    certification_source_sha256: str
    instance_sha256: str
    source_file_sha256: str
    coordinates_sha256: str
    solver_status: str
    exact_certification: str
    pilot_authorized: bool
    formal_authorized: bool
    y: list[int]
    x: list[list[float]]
    a_plus: list[list[float]]
    a_minus: list[list[float]]


def _zeros(instance: InventoryInstance) -> list[list[float]]:
    return [
        [0.0 for _ in range(instance.num_products)]
        for _ in range(instance.num_depots)
    ]


def _load_x0_policy(
    root: Path,
    case_id: str,
    *,
    policy_id: str,
    lineage: str,
    pilot_authorized: bool,
) -> FrozenPolicy:
    instance_path = root / f"data/formal_instances_v2/{case_id}.json"
    source_path = root / f"artifacts/renault_empirical_8case_v1/x0/{case_id}.json"
    instance = load_instance(instance_path)
    artifact = json.loads(source_path.read_text(encoding="utf-8"))
    stability_path = root / f"artifacts/renault_empirical_8case_v1/stability/{case_id}.json"
    stability = json.loads(stability_path.read_text(encoding="utf-8"))
    if artifact["instance_sha256"] != file_sha256(instance_path):
        raise ValueError(f"{case_id} x0 instance hash mismatch")
    if (
        stability.get("status") != "PASS"
        or stability.get("canonical_incumbent_status") != "PASS"
    ):
        raise ValueError(f"{case_id} canonical incumbent stability audit failed")
    x = [[float(value) for value in row] for row in artifact["x0"]]
    y = [int(value) for value in artifact["y0"]]
    a_plus = _zeros(instance)
    a_minus = _zeros(instance)
    return FrozenPolicy(
        policy_id=policy_id,
        case_id=case_id,
        lineage=lineage,
        source_path=source_path,
        source_run_id=f"RENAULT_EMPIRICAL_8CASE_V1-X0-{case_id}",
        certification_source_path=stability_path,
        certification_source_sha256=file_sha256(stability_path),
        instance_sha256=file_sha256(instance_path),
        source_file_sha256=file_sha256(source_path),
        coordinates_sha256=coordinate_sha256(y, x, a_plus, a_minus),
        solver_status="NOT_RECORDED_IN_X0_ARTIFACT",
        exact_certification="CANONICAL_INCUMBENT_STABILITY_PASS_NOT_E2_SOLVER_CERTIFICATE",
        pilot_authorized=pilot_authorized,
        formal_authorized=False,
        y=y,
        x=x,
        a_plus=a_plus,
        a_minus=a_minus,
    )


def _load_robust_candidate(root: Path, case_id: str) -> FrozenPolicy:
    instance_path = root / f"data/formal_instances_v2/{case_id}.json"
    source_dir = (
        root
        / "experiments/results/service_calibration_robustness_v2_fixed_recourse"
        / "physical_results"
        / f"SCAL_BASE_{case_id}"
    )
    source_path = source_dir / "first_stage_solution.json"
    instance = load_instance(instance_path)
    artifact = load_first_stage_solution_artifact(source_path, instance)
    result_path = source_dir / "result.json"
    provenance_path = source_dir / "provenance.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    provenance = json.loads(
        provenance_path.read_text(encoding="utf-8")
    )
    if provenance["first_stage_solution_sha256"] != file_sha256(source_path):
        raise ValueError(f"{case_id} robust candidate provenance hash mismatch")
    if provenance["result_sha256"] != file_sha256(result_path):
        raise ValueError(f"{case_id} robust result provenance hash mismatch")
    if result["instance_hash"] != file_sha256(instance_path):
        raise ValueError(f"{case_id} robust candidate instance hash mismatch")
    if (
        result.get("solver_status") != "OPTIMAL"
        or result.get("optimality_certification") != "CERTIFIED_PRB_EXACT"
    ):
        raise ValueError(f"{case_id} robust candidate is not exactly certified")
    y = [int(entry["value"]) for entry in artifact["y"]]
    x = matrix_from_artifact(artifact, instance, "x")
    a_plus = matrix_from_artifact(artifact, instance, "a_plus")
    a_minus = matrix_from_artifact(artifact, instance, "a_minus")
    return FrozenPolicy(
        policy_id=f"ROBUST_EQUIVALENT_SCAL_BASE_{case_id}",
        case_id=case_id,
        lineage="SUBSEQUENT_NUMERICALLY_EQUIVALENT_SOLUTION_NOT_ORIGINAL_E1_E2",
        source_path=source_path,
        source_run_id=f"SCAL_BASE_{case_id}",
        certification_source_path=result_path,
        certification_source_sha256=file_sha256(result_path),
        instance_sha256=file_sha256(instance_path),
        source_file_sha256=file_sha256(source_path),
        coordinates_sha256=coordinate_sha256(y, x, a_plus, a_minus),
        solver_status=str(result["solver_status"]),
        exact_certification=str(result["optimality_certification"]),
        pilot_authorized=False,
        formal_authorized=False,
        y=y,
        x=x,
        a_plus=a_plus,
        a_minus=a_minus,
    )


def recover_policy_candidates(root: Path, case_id: str) -> list[FrozenPolicy]:
    existing = _load_x0_policy(
        root,
        case_id,
        policy_id=f"EXISTING_CANONICAL_{case_id}",
        lineage="ORIGINAL_CANONICAL_EXISTING_POLICY",
        pilot_authorized=True,
    )
    nominal = _load_x0_policy(
        root,
        case_id,
        policy_id=f"NOMINAL_CANONICAL_REDECLARED_{case_id}",
        lineage="REDECLARED_CANONICAL_POLICY_NOT_RECOVERED_E2_COORDINATES",
        pilot_authorized=False,
    )
    robust = _load_robust_candidate(root, case_id)
    if existing.coordinates_sha256 != nominal.coordinates_sha256:
        raise ValueError(f"{case_id} canonical Existing and Nominal differ")
    return [existing, nominal, robust]


def _e2_consistency(root: Path, policy: FrozenPolicy) -> dict[str, Any]:
    rows = {
        row["case"]: row
        for row in _read_csv(root / "artifacts/e2_policy_contrast_summary.csv")
    }
    row = rows[policy.case_id]
    if policy.policy_id.startswith("EXISTING"):
        return {
            "e2_derived_objective": float(row["existing_objective"]),
            "objective_delta": None,
            "ri_delta": 0.0,
            "consistency_status": "AGGREGATE_ONLY_NO_COORDINATE_SOURCE",
        }
    if policy.policy_id.startswith("NOMINAL"):
        return {
            "e2_derived_objective": float(row["nominal_objective"]),
            "objective_delta_vs_existing": float(row["existing_nominal_abs_objective_diff"]),
            "consistency_status": "MATERIAL_POLICY_MATCH_ONLY_NOT_COORDINATE_RECOVERY",
        }
    result_path = policy.source_path.parent / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    objective_delta = float(result["objective"]) - float(row["robust_objective"])
    ri_delta = float(result["RI"]) - float(row["RI"])
    rs_delta = (
        float(result["reconfiguration_spending"]) / float(result["budget"])
        - float(row["RS"])
    )
    return {
        "e2_derived_objective": float(row["robust_objective"]),
        "candidate_objective": float(result["objective"]),
        "objective_delta": objective_delta,
        "ri_delta": ri_delta,
        "rs_delta": rs_delta,
        "active_depot_count": int(result["active_depot_count"]),
        "consistency_status": (
            "NUMERICALLY_EQUIVALENT_WITHIN_1E_6"
            if max(abs(objective_delta), abs(ri_delta), abs(rs_delta)) <= 1e-6
            else "MISMATCH"
        ),
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def build_policy_identity_manifest(root: Path) -> dict[str, Any]:
    cases = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")
    entries = []
    for case_id in cases:
        for policy in recover_policy_candidates(root, case_id):
            entry = {
                    "case_id": policy.case_id,
                    "policy_id": policy.policy_id,
                    "lineage": policy.lineage,
                    "source_path": policy.source_path.relative_to(root).as_posix(),
                    "source_run_id": policy.source_run_id,
                    "certification_source_path": policy.certification_source_path.relative_to(root).as_posix(),
                    "certification_source_sha256": policy.certification_source_sha256,
                    "instance_sha256": policy.instance_sha256,
                    "source_file_sha256": policy.source_file_sha256,
                    "coordinates_sha256": policy.coordinates_sha256,
                    "coordinate_component_sha256": {
                        "y": canonical_sha256(policy.y),
                        "x": canonical_sha256(policy.x),
                        "a_plus": canonical_sha256(policy.a_plus),
                        "a_minus": canonical_sha256(policy.a_minus),
                    },
                    "solver_status": policy.solver_status,
                    "exact_certification": policy.exact_certification,
                    "pilot_authorized": policy.pilot_authorized,
                    "formal_authorized": policy.formal_authorized,
                    "same_configuration_group": f"CANONICAL_X0_{case_id}"
                    if not policy.policy_id.startswith("ROBUST")
                    else None,
                    "e2_aggregate_consistency": _e2_consistency(root, policy),
                }
            if policy.policy_id.startswith("ROBUST"):
                source_dir = policy.source_path.parent
                result_path = source_dir / "result.json"
                provenance_path = source_dir / "provenance.json"
                provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
                entry["robust_source_evidence"] = {
                    "classification": "SUBSEQUENT_CERTIFIED_NUMERICALLY_EQUIVALENT_CANDIDATE",
                    "result_path": result_path.relative_to(root).as_posix(),
                    "result_sha256": file_sha256(result_path),
                    "provenance_path": provenance_path.relative_to(root).as_posix(),
                    "provenance_sha256": file_sha256(provenance_path),
                    "provenance_recorded_result_sha256": provenance["result_sha256"],
                    "provenance_recorded_first_stage_solution_sha256": provenance[
                        "first_stage_solution_sha256"
                    ],
                    "result_hash_link_verified": (
                        provenance["result_sha256"] == file_sha256(result_path)
                    ),
                    "solution_hash_link_verified": (
                        provenance["first_stage_solution_sha256"]
                        == policy.source_file_sha256
                    ),
                    "historical_e1_e2_coordinates_recovered": False,
                }
            entries.append(entry)
    payload = {
        "schema_version": "1.0",
        "experiment_id": "E2_STOCKOUT_COMMON_SCENARIO_V1",
        "identity_freeze_status": "PARTIAL_REQUIRES_HUMAN_CONFIRMATION",
        "formal_run_authorized": False,
        "policy_decision": "B",
        "policy_decision_reason": (
            "Original E2 Nominal coordinates and original E1/E2 Robust artifacts were not "
            "found. Canonical Nominal redeclaration and SCAL_BASE Robust lineage require review."
        ),
        "cases": list(cases),
        "policies": entries,
    }
    return {**payload, "manifest_payload_sha256": canonical_sha256(payload)}


def build_common_scenario_manifest(
    root: Path, identity_manifest: dict[str, Any]
) -> dict[str, Any]:
    cases = []
    for case_id in identity_manifest["cases"]:
        instance_path = root / f"data/formal_instances_v2/{case_id}.json"
        instance = load_instance(instance_path)
        if instance.num_regions != 12 or instance.num_products != 8:
            raise ValueError(f"{case_id} dimensions differ from the frozen protocol")
        cases.append(
            {
                "case_id": case_id,
                "instance_path": instance_path.relative_to(root).as_posix(),
                "instance_sha256": file_sha256(instance_path),
                "num_depots": instance.num_depots,
                "num_regions": instance.num_regions,
                "num_products": instance.num_products,
                "uncertain_components": instance.num_regions * instance.num_products,
                "scenario_count": scenario_count(instance, GAMMA),
                "scenario_order_sha256": scenario_manifest_sha256(instance, GAMMA),
                "scenario_id_order_sha256": scenario_id_order_sha256(),
                "policy_coordinate_hashes": {
                    row["policy_id"]: row["coordinates_sha256"]
                    for row in identity_manifest["policies"]
                    if row["case_id"] == case_id
                },
            }
        )
    try:
        import gurobipy as gp

        solver_version = ".".join(map(str, gp.gurobi.version()))
    except ImportError:
        solver_version = "UNAVAILABLE"
    payload = {
        "schema_version": "1.0",
        "experiment_id": "E2_STOCKOUT_COMMON_SCENARIO_V1",
        "formal_run_authorized": False,
        "pilot_authorized": True,
        "pilot_case_id": "210202",
        "pilot_policy_id": "EXISTING_CANONICAL_210202",
        "pilot_scenario_ids": ["S0000", "S0001", "S0097"],
        "pilot_max_scenarios": PILOT_MAX_SCENARIOS,
        "gamma": GAMMA,
        "scenario_definition": "canonical region-major binary shocks with cardinality <= Gamma",
        "reporting_tie_break": "minimize sum of squared shortages within 1e-7 of each product-local economic optimum",
        "reporting_tie_break_tolerance": REPORTING_TIE_BREAK_TOLERANCE,
        "solver_profile_id": FORMAL_SOLVER_PROFILE_ID,
        "solver_native_profile": FORMAL_SOLVER_NATIVE_PROFILE,
        "threads": 1,
        "python_version": platform.python_version(),
        "solver_version": solver_version,
        "identity_manifest_sha256": identity_manifest["manifest_payload_sha256"],
        "comparison_definition": {
            "independent_first_stage_configuration_count": 2,
            "baseline": "EXISTING_CANONICAL",
            "robust_candidate": "ROBUST_EQUIVALENT_SCAL_BASE_REQUIRES_HUMAN_CONFIRMATION",
            "nominal_role": "VALIDATION_LABEL_SAME_COORDINATES_AS_BASELINE_NOT_SEPARATE_CONFIGURATION",
            "original_e2_nominal_coordinates_recovered": False,
        },
        "cases": cases,
    }
    return {**payload, "manifest_payload_sha256": canonical_sha256(payload)}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def validate_manifest_hash(manifest: dict[str, Any]) -> None:
    recorded = manifest.get("manifest_payload_sha256")
    payload = {key: value for key, value in manifest.items() if key != "manifest_payload_sha256"}
    if recorded != canonical_sha256(payload):
        raise ValueError("manifest payload hash mismatch")


def policy_from_manifest(root: Path, row: dict[str, Any]) -> FrozenPolicy:
    case_id = row["case_id"]
    if row["policy_id"].startswith("ROBUST"):
        policy = _load_robust_candidate(root, case_id)
    elif row["policy_id"].startswith("NOMINAL"):
        policy = _load_x0_policy(
            root,
            case_id,
            policy_id=row["policy_id"],
            lineage="REDECLARED_CANONICAL_POLICY_NOT_RECOVERED_E2_COORDINATES",
            pilot_authorized=False,
        )
    else:
        policy = _load_x0_policy(
            root,
            case_id,
            policy_id=row["policy_id"],
            lineage="ORIGINAL_CANONICAL_EXISTING_POLICY",
            pilot_authorized=True,
        )
    for field in (
        "instance_sha256",
        "source_file_sha256",
        "coordinates_sha256",
        "source_run_id",
        "lineage",
        "certification_source_sha256",
    ):
        if getattr(policy, field) != row[field]:
            raise ValueError(f"policy identity mismatch: {field}")
    return policy


def _selected_scenarios(
    instance: InventoryInstance, selected_ids: Iterable[str]
) -> list[tuple[str, tuple[tuple[int, int], ...]]]:
    all_scenarios = enumerate_scenario_components(instance, GAMMA)
    selected = []
    for identifier in selected_ids:
        if not identifier.startswith("S") or not identifier[1:].isdigit():
            raise ValueError(f"invalid scenario ID: {identifier}")
        index = int(identifier[1:])
        if index >= len(all_scenarios) or scenario_id(index) != identifier:
            raise ValueError(f"scenario ID is outside the frozen manifest: {identifier}")
        selected.append((identifier, all_scenarios[index]))
    if len({identifier for identifier, _ in selected}) != len(selected):
        raise ValueError("duplicate scenario ID")
    return selected


def require_optimal_solver_status(
    status: int | None, *, optimal_status: int, phase: str
) -> None:
    if status != optimal_status:
        raise RuntimeError(f"{phase} failed or was incomplete: solver status={status}")


class _PeakMemoryMonitor:
    def __init__(self) -> None:
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        try:
            import psutil

            process = psutil.Process(os.getpid())
            while not self._stop.wait(0.02):
                self.peak_bytes = max(self.peak_bytes, process.memory_info().rss)
        except ImportError:
            self.peak_bytes = -1

    def __enter__(self) -> "_PeakMemoryMonitor":
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()


def evaluate_fixed_policy_scenarios(
    instance: InventoryInstance,
    policy: FrozenPolicy,
    selected_ids: list[str],
    *,
    threads: int = 1,
) -> dict[str, Any]:
    """Solve only fixed-inventory recourse blocks for preselected full scenarios."""
    import gurobipy as gp
    from gurobipy import GRB

    if threads != 1:
        raise ValueError("the frozen resource protocol requires Threads=1")
    selected = _selected_scenarios(instance, selected_ids)
    before = copy.deepcopy(coordinate_payload(policy.y, policy.x, policy.a_plus, policy.a_minus))
    before_hash = canonical_sha256(before)
    fixed_x = canonical_fixed_inventory(instance, policy.x)
    depots = range(instance.num_depots)
    regions = range(instance.num_regions)

    block_keys = sorted(
        {
            (j, tuple(r for r, product in scenario if product == j))
            for _, scenario in selected
            for j in range(instance.num_products)
        }
    )
    model = gp.Model(f"e2_stockout_fixed_{policy.case_id}_{policy.policy_id}")
    model.Params.OutputFlag = 0
    apply_formal_solver_profile(model, mixed_integer=False)
    model.Params.Threads = threads
    q_vars: dict[tuple[int, tuple[int, ...]], Any] = {}
    u_vars: dict[tuple[int, tuple[int, ...]], Any] = {}
    e_vars: dict[tuple[int, tuple[int, ...]], Any] = {}
    components: dict[tuple[int, tuple[int, ...]], tuple[Any, Any, Any]] = {}
    costs: dict[tuple[int, tuple[int, ...]], Any] = {}

    for j, shocked_regions in block_keys:
        suffix = "none" if not shocked_regions else "-".join(map(str, shocked_regions))
        q = model.addVars(depots, regions, lb=0, name=f"q_p{j}_s{suffix}")
        u = model.addVars(regions, lb=0, name=f"u_p{j}_s{suffix}")
        e = model.addVar(lb=0, name=f"e_p{j}_s{suffix}")
        shocked = set(shocked_regions)
        demand = [
            instance.base_demand[r][j]
            + (instance.demand_deviation[r][j] if r in shocked else 0.0)
            for r in regions
        ]
        for r in regions:
            model.addConstr(gp.quicksum(q[i, r] for i in depots) + u[r] >= demand[r])
        for i in depots:
            model.addConstr(gp.quicksum(q[i, r] for r in regions) <= fixed_x[i][j])
        model.addConstr(
            gp.quicksum(u[r] for r in regions) - e
            <= (1.0 - instance.service_level[j]) * sum(demand)
        )
        transportation = gp.quicksum(
            instance.transport_cost[i][r][j] * q[i, r]
            for i in depots
            for r in regions
        )
        shortage = gp.quicksum(
            instance.shortage_penalty[r][j] * u[r] for r in regions
        )
        service = instance.service_penalty[j] * e
        key = (j, shocked_regions)
        q_vars[key], u_vars[key], e_vars[key] = q, u, e
        components[key] = (transportation, shortage, service)
        costs[key] = transportation + shortage + service

    model.setObjective(gp.quicksum(costs.values()), GRB.MINIMIZE)
    model.optimize()
    require_optimal_solver_status(
        model.Status, optimal_status=GRB.OPTIMAL, phase="fixed-policy economic recourse solve"
    )
    economic_optimum = {key: float(cost.getValue()) for key, cost in costs.items()}
    for key, cost in costs.items():
        model.addConstr(cost <= economic_optimum[key] + REPORTING_TIE_BREAK_TOLERANCE)
    model.setObjective(
        gp.quicksum(u_vars[key][r] * u_vars[key][r] for key in block_keys for r in regions),
        GRB.MINIMIZE,
    )
    model.optimize()
    require_optimal_solver_status(
        model.Status, optimal_status=GRB.OPTIMAL, phase="fixed-policy reporting tie-break"
    )

    block_results: dict[tuple[int, tuple[int, ...]], dict[str, Any]] = {}
    for key in block_keys:
        transportation, shortage, service = components[key]
        shipment = sum(q_vars[key][i, r].X for i in depots for r in regions)
        shortage_values = [float(u_vars[key][r].X) for r in regions]
        block_results[key] = {
            "total_shipment": float(shipment),
            "total_shortage": float(sum(shortage_values)),
            "service_violation": float(e_vars[key].X),
            "transportation_cost": float(transportation.getValue()),
            "shortage_penalty_cost": float(shortage.getValue()),
            "service_penalty_cost": float(service.getValue()),
            "economic_optimum_cost": economic_optimum[key],
        }

    scenario_results = []
    for identifier, scenario in selected:
        keys = [
            (j, tuple(r for r, product in scenario if product == j))
            for j in range(instance.num_products)
        ]
        shortage_by_product = {
            instance.product_ids[j]: block_results[keys[j]]["total_shortage"]
            for j in range(instance.num_products)
        }
        violation_by_product = {
            instance.product_ids[j]: block_results[keys[j]]["service_violation"]
            for j in range(instance.num_products)
        }
        transportation_cost = sum(block_results[key]["transportation_cost"] for key in keys)
        shortage_cost = sum(block_results[key]["shortage_penalty_cost"] for key in keys)
        service_cost = sum(block_results[key]["service_penalty_cost"] for key in keys)
        component_sum = transportation_cost + shortage_cost + service_cost
        optimum_cost = sum(block_results[key]["economic_optimum_cost"] for key in keys)
        numeric_values = (
            transportation_cost,
            shortage_cost,
            service_cost,
            component_sum,
            optimum_cost,
            *(shortage_by_product.values()),
            *(violation_by_product.values()),
        )
        if not all(math.isfinite(value) for value in numeric_values):
            raise RuntimeError(f"non-finite recourse result for {identifier}")
        if any(value < -1e-7 for value in numeric_values):
            raise RuntimeError(f"materially negative recourse result for {identifier}")
        tie_break_delta = component_sum - optimum_cost
        if abs(tie_break_delta) > (
            len(keys) * REPORTING_TIE_BREAK_TOLERANCE + 1e-6
        ):
            raise RuntimeError(f"cost identity exceeds tie-break band for {identifier}")
        scenario_results.append(
            {
                "scenario_id": identifier,
                "shock_set": [
                    [instance.region_ids[r], instance.product_ids[j]] for r, j in scenario
                ],
                "policy_id": policy.policy_id,
                "policy_hash": policy.coordinates_sha256,
                "instance_hash": policy.instance_sha256,
                "solver_status": "OPTIMAL",
                "total_shipment": sum(block_results[key]["total_shipment"] for key in keys),
                "total_shortage": sum(shortage_by_product.values()),
                "shortage_by_product": shortage_by_product,
                "service_violation_by_product": violation_by_product,
                "total_service_violation": sum(violation_by_product.values()),
                "transportation_cost": transportation_cost,
                "shortage_penalty_cost": shortage_cost,
                "service_penalty_cost": service_cost,
                "recourse_cost": component_sum,
                "economic_optimum_recourse_cost": optimum_cost,
                "reporting_tie_break_cost_delta": tie_break_delta,
            }
        )

    after_hash = canonical_sha256(
        coordinate_payload(policy.y, policy.x, policy.a_plus, policy.a_minus)
    )
    if before_hash != after_hash or before_hash != policy.coordinates_sha256:
        raise RuntimeError("first-stage coordinates changed during recourse evaluation")
    model.dispose()
    return {
        "policy_coordinates_before_sha256": before_hash,
        "policy_coordinates_after_sha256": after_hash,
        "unique_product_local_blocks": len(block_keys),
        "scenarios": scenario_results,
    }


def frozen_scenario_ids(expected_scenario_count: int) -> tuple[str, ...]:
    if expected_scenario_count <= 0:
        raise ValueError("expected scenario count must be positive")
    return tuple(scenario_id(index) for index in range(expected_scenario_count))


def frozen_scenario_ids_from_manifest(
    scenario_manifest: dict[str, Any], case_id: str
) -> tuple[str, ...]:
    validate_manifest_hash(scenario_manifest)
    if scenario_manifest.get("experiment_id") != "E2_STOCKOUT_COMMON_SCENARIO_V1":
        raise ValueError("unexpected common-scenario experiment identity")
    if scenario_manifest.get("gamma") != GAMMA:
        raise ValueError("frozen Gamma identity mismatch")
    try:
        case = next(row for row in scenario_manifest["cases"] if row["case_id"] == case_id)
    except (KeyError, StopIteration) as exc:
        raise ValueError(f"case {case_id} is absent from the frozen scenario manifest") from exc
    if case.get("scenario_count") != FORMAL_SCENARIO_COUNT:
        raise ValueError("frozen scenario count is not 4657")
    expected = frozen_scenario_ids(FORMAL_SCENARIO_COUNT)
    if case.get("scenario_id_order_sha256") != canonical_sha256(list(expected)):
        raise ValueError("frozen scenario ID order hash mismatch")
    return expected


def _validate_solved_metric_rows(rows: list[dict[str, Any]]) -> None:
    required_fields = (
        "total_shortage",
        "total_service_violation",
        "shortage_penalty_cost",
        "service_penalty_cost",
        "transportation_cost",
        "recourse_cost",
        "economic_optimum_recourse_cost",
    )
    for row in rows:
        identifier = row.get("scenario_id")
        if row.get("solver_status") != "OPTIMAL":
            raise ValueError(f"scenario {identifier} has an incomplete solver result")
        missing = [field for field in required_fields if row.get(field) is None]
        if missing:
            raise ValueError(f"scenario {identifier} has incomplete metrics: {missing}")


def validate_complete_scenario_rows(
    rows: list[dict[str, Any]], expected_scenario_ids: Iterable[str]
) -> tuple[str, ...]:
    expected = tuple(expected_scenario_ids)
    expected_set = set(expected)
    if len(expected_set) != len(expected):
        raise ValueError("frozen expected scenario IDs contain duplicates")
    actual = [row.get("scenario_id") for row in rows]
    if any(not isinstance(identifier, str) for identifier in actual):
        raise ValueError("incomplete frozen scenario set: missing or invalid scenario ID")
    actual_set = set(actual)
    duplicates = sorted(identifier for identifier, count in Counter(actual).items() if count > 1)
    missing = sorted(expected_set - actual_set)
    unknown = sorted(actual_set - expected_set, key=str)
    if duplicates or missing or unknown or len(actual) != len(expected):
        raise ValueError(
            "incomplete frozen scenario set: "
            f"duplicates={duplicates}, missing={missing}, unknown={unknown}, "
            f"actual_count={len(actual)}, expected_count={len(expected)}"
        )
    _validate_solved_metric_rows(rows)
    return expected


def _validate_partial_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("partial scenario diagnostic contains no rows")
    identifiers = [row.get("scenario_id") for row in rows]
    if any(not isinstance(identifier, str) for identifier in identifiers):
        raise ValueError("partial scenario diagnostic has a missing scenario ID")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("partial scenario diagnostic contains duplicate scenario IDs")
    _validate_solved_metric_rows(rows)


def _worst_metric(
    rows: list[dict[str, Any]], key: str, tolerance: float
) -> dict[str, Any]:
    maximum = max(float(row[key]) for row in rows)
    tied = [
        row["scenario_id"]
        for row in rows
        if abs(float(row[key]) - maximum) <= tolerance
    ]
    return {
        "value": maximum,
        "representative_scenario_id": tied[0],
        "tied_scenario_ids": tied,
        "tie_count": len(tied),
    }


def improvement_percent(
    baseline: float, policy: float, *, denominator_tolerance: float
) -> float | None:
    if baseline <= denominator_tolerance:
        return None
    return 100.0 * (baseline - policy) / baseline


def _summarize_nominal_common_scenario(
    rows: list[dict[str, Any]], nominal_keys: tuple[str, ...]
) -> dict[str, Any] | None:
    by_id = {row["scenario_id"]: row for row in rows}
    if "S0000" not in by_id:
        return None
    return {
        "scenario_id": "S0000",
        **{key: float(by_id["S0000"][key]) for key in nominal_keys},
    }


def _metric_summary(
    rows: list[dict[str, Any]],
    *,
    tie_tolerance: float = 1e-9,
    baseline_rows: list[dict[str, Any]] | None = None,
    denominator_tolerance: float = 1e-9,
) -> dict[str, Any]:
    nominal_keys = (
        "total_shortage",
        "total_service_violation",
        "shortage_penalty_cost",
        "service_penalty_cost",
        "transportation_cost",
        "recourse_cost",
        "economic_optimum_recourse_cost",
    )
    nominal = _summarize_nominal_common_scenario(rows, nominal_keys)
    worst = {
        key: _worst_metric(rows, key, tie_tolerance)
        for key in (
            "total_shortage",
            "total_service_violation",
            "shortage_penalty_cost",
            "economic_optimum_recourse_cost",
        )
    }
    summary: dict[str, Any] = {
        "nominal_common_scenario": nominal,
        "worst_metrics": worst,
        "tie_rule": "canonical first scenario within absolute tolerance",
        "tie_tolerance": tie_tolerance,
        "improvement_denominator_tolerance": denominator_tolerance,
    }
    if baseline_rows is not None:
        baseline = _metric_summary(
            baseline_rows,
            tie_tolerance=tie_tolerance,
            denominator_tolerance=denominator_tolerance,
        )
        summary["improvement_percent_vs_baseline"] = {
            "nominal_common_scenario": {
                key: improvement_percent(
                    baseline["nominal_common_scenario"][key],
                    nominal[key],
                    denominator_tolerance=denominator_tolerance,
                )
                for key in nominal_keys
            },
            "worst_metrics": {
                key: improvement_percent(
                    baseline["worst_metrics"][key]["value"],
                    worst[key]["value"],
                    denominator_tolerance=denominator_tolerance,
                )
                for key in worst
            },
        }
    return summary


def summarize_partial_policy_metrics(
    rows: list[dict[str, Any]],
    *,
    tie_tolerance: float = 1e-9,
    denominator_tolerance: float = 1e-9,
) -> dict[str, Any]:
    _validate_partial_rows(rows)
    summary = _metric_summary(
        rows,
        tie_tolerance=tie_tolerance,
        denominator_tolerance=denominator_tolerance,
    )
    return {
        "coverage_status": "PARTIAL_SCENARIO_DIAGNOSTIC",
        "scenario_count": len(rows),
        "scenario_ids": [row["scenario_id"] for row in rows],
        "nominal_common_scenario": summary["nominal_common_scenario"],
        "worst_over_observed_subset": summary["worst_metrics"],
        "tie_rule": summary["tie_rule"],
        "tie_tolerance": tie_tolerance,
        "improvement_denominator_tolerance": denominator_tolerance,
    }


def summarize_complete_policy_metrics(
    rows: list[dict[str, Any]],
    scenario_manifest: dict[str, Any],
    case_id: str,
    *,
    tie_tolerance: float = 1e-9,
    baseline_rows: list[dict[str, Any]] | None = None,
    denominator_tolerance: float = 1e-9,
) -> dict[str, Any]:
    expected = frozen_scenario_ids_from_manifest(scenario_manifest, case_id)
    validate_complete_scenario_rows(rows, expected)
    rows_by_id = {row["scenario_id"]: row for row in rows}
    rows = [rows_by_id[identifier] for identifier in expected]
    if baseline_rows is not None:
        validate_complete_scenario_rows(baseline_rows, expected)
        baseline_by_id = {row["scenario_id"]: row for row in baseline_rows}
        baseline_rows = [baseline_by_id[identifier] for identifier in expected]
    summary = _metric_summary(
        rows,
        tie_tolerance=tie_tolerance,
        baseline_rows=baseline_rows,
        denominator_tolerance=denominator_tolerance,
    )
    result = {
        "coverage_status": "COMPLETE_FROZEN_SCENARIO_SET",
        "scenario_count": len(rows),
        "scenario_id_set_sha256": canonical_sha256(sorted(expected)),
        "scenario_id_order_sha256": canonical_sha256(list(expected)),
        "nominal_common_scenario": summary["nominal_common_scenario"],
        "worst_over_frozen_set": summary["worst_metrics"],
        "tie_rule": summary["tie_rule"],
        "tie_tolerance": tie_tolerance,
        "improvement_denominator_tolerance": denominator_tolerance,
    }
    if "improvement_percent_vs_baseline" in summary:
        improvement = summary["improvement_percent_vs_baseline"]
        result["improvement_percent_vs_baseline"] = {
            "nominal_common_scenario": improvement["nominal_common_scenario"],
            "worst_over_frozen_set": improvement["worst_metrics"],
        }
    return result


def validate_complete_evaluation(
    evaluation: dict[str, Any],
    *,
    instance: InventoryInstance,
    policy: FrozenPolicy,
    scenario_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    expected_ids = frozen_scenario_ids_from_manifest(scenario_manifest, policy.case_id)
    rows = evaluation.get("scenarios")
    if not isinstance(rows, list):
        raise ValueError("formal evaluation has no scenario rows")
    validate_complete_scenario_rows(rows, expected_ids)
    if evaluation.get("policy_coordinates_before_sha256") != policy.coordinates_sha256:
        raise ValueError("formal evaluation pre-solve policy identity mismatch")
    if evaluation.get("policy_coordinates_after_sha256") != policy.coordinates_sha256:
        raise ValueError("formal evaluation post-solve policy identity mismatch")

    expected_shocks = scenario_payload(instance, GAMMA)
    rows_by_id = {row["scenario_id"]: row for row in rows}
    product_ids = set(instance.product_ids)
    for index, identifier in enumerate(expected_ids):
        row = rows_by_id[identifier]
        if row.get("shock_set") != expected_shocks[index]:
            raise ValueError(f"scenario shock identity mismatch: {identifier}")
        if row.get("policy_id") != policy.policy_id:
            raise ValueError(f"scenario policy ID mismatch: {identifier}")
        if row.get("policy_hash") != policy.coordinates_sha256:
            raise ValueError(f"scenario policy hash mismatch: {identifier}")
        if row.get("instance_hash") != policy.instance_sha256:
            raise ValueError(f"scenario instance hash mismatch: {identifier}")
        shortage = row.get("shortage_by_product")
        violation = row.get("service_violation_by_product")
        if not isinstance(shortage, dict) or set(shortage) != product_ids:
            raise ValueError(f"scenario shortage product identities mismatch: {identifier}")
        if not isinstance(violation, dict) or set(violation) != product_ids:
            raise ValueError(f"scenario service product identities mismatch: {identifier}")
        numeric = (
            row.get("total_shipment"),
            row.get("total_shortage"),
            row.get("total_service_violation"),
            row.get("transportation_cost"),
            row.get("shortage_penalty_cost"),
            row.get("service_penalty_cost"),
            row.get("recourse_cost"),
            row.get("economic_optimum_recourse_cost"),
            row.get("reporting_tie_break_cost_delta"),
            *shortage.values(),
            *violation.values(),
        )
        if any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in numeric):
            raise ValueError(f"scenario has missing or non-finite metrics: {identifier}")
        nonnegative = (
            row["total_shipment"],
            row["total_shortage"],
            row["total_service_violation"],
            row["transportation_cost"],
            row["shortage_penalty_cost"],
            row["service_penalty_cost"],
            row["recourse_cost"],
            row["economic_optimum_recourse_cost"],
            *shortage.values(),
            *violation.values(),
        )
        if any(float(value) < -1e-7 for value in nonnegative):
            raise ValueError(f"scenario has a materially negative metric: {identifier}")
        if not math.isclose(
            float(row["total_shortage"]),
            sum(map(float, shortage.values())),
            abs_tol=1e-6,
        ):
            raise ValueError(f"scenario shortage total mismatch: {identifier}")
        if not math.isclose(
            float(row["total_service_violation"]),
            sum(map(float, violation.values())),
            abs_tol=1e-6,
        ):
            raise ValueError(f"scenario service total mismatch: {identifier}")
        component_sum = sum(
            float(row[key])
            for key in (
                "transportation_cost",
                "shortage_penalty_cost",
                "service_penalty_cost",
            )
        )
        if not math.isclose(float(row["recourse_cost"]), component_sum, abs_tol=1e-6):
            raise ValueError(f"scenario recourse component mismatch: {identifier}")
        delta = component_sum - float(row["economic_optimum_recourse_cost"])
        if not math.isclose(
            float(row["reporting_tie_break_cost_delta"]), delta, abs_tol=1e-6
        ):
            raise ValueError(f"scenario tie-break delta mismatch: {identifier}")
        if abs(delta) > instance.num_products * REPORTING_TIE_BREAK_TOLERANCE + 1e-6:
            raise ValueError(f"scenario exceeds the frozen tie-break band: {identifier}")
    return rows


def validate_formal_checkpoint(
    checkpoint_path: Path,
    *,
    expected_identity: dict[str, Any],
    instance: InventoryInstance,
    policy: FrozenPolicy,
    scenario_manifest: dict[str, Any],
    baseline_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    digest_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".sha256")
    if not checkpoint_path.exists() or not digest_path.exists():
        raise FileNotFoundError("formal checkpoint or digest is missing")
    if file_sha256(checkpoint_path) != digest_path.read_text(encoding="utf-8").strip():
        raise ValueError("formal checkpoint content hash mismatch")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("classification") != "FORMAL_COMMON_SCENARIO_RESULT":
        raise ValueError("checkpoint is not a formal common-scenario result")
    if checkpoint.get("schema_version") != "1.0":
        raise ValueError("formal checkpoint schema version mismatch")
    if checkpoint.get("experiment_id") != "E2_STOCKOUT_COMMON_SCENARIO_V1":
        raise ValueError("formal checkpoint experiment identity mismatch")
    if checkpoint.get("case_id") != policy.case_id or checkpoint.get("policy_id") != policy.policy_id:
        raise ValueError("formal checkpoint task identity mismatch")
    expected_task_id = (
        f"E2S-{policy.case_id}-"
        f"{'EXISTING' if policy.policy_id.startswith('EXISTING') else 'ROBUST'}"
    )
    if checkpoint.get("task_id") != expected_task_id:
        raise ValueError("formal checkpoint task ID mismatch")
    if checkpoint.get("scenario_count") != FORMAL_SCENARIO_COUNT:
        raise ValueError("formal checkpoint scenario count mismatch")
    runtime = checkpoint.get("runtime_seconds")
    if not isinstance(runtime, (int, float)) or not math.isfinite(runtime) or runtime < 0:
        raise ValueError("formal checkpoint runtime is invalid")
    for key, value in expected_identity.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"formal checkpoint identity mismatch: {key}")
    rows = validate_complete_evaluation(
        checkpoint.get("evaluation", {}),
        instance=instance,
        policy=policy,
        scenario_manifest=scenario_manifest,
    )
    recomputed = summarize_complete_policy_metrics(
        rows,
        scenario_manifest,
        policy.case_id,
        baseline_rows=baseline_rows,
    )
    recorded = checkpoint.get("metric_summary")
    if not isinstance(recorded, dict):
        raise ValueError("formal checkpoint metric summary is missing")
    for key in (
        "coverage_status",
        "scenario_count",
        "scenario_id_set_sha256",
        "scenario_id_order_sha256",
        "nominal_common_scenario",
        "worst_over_frozen_set",
    ):
        if recorded.get(key) != recomputed.get(key):
            raise ValueError(f"formal checkpoint metric summary mismatch: {key}")
    return checkpoint


def build_structural_resource_preflight(
    scenario_manifest: dict[str, Any], pilot_checkpoint: dict[str, Any]
) -> dict[str, Any]:
    validate_manifest_hash(scenario_manifest)
    blocks_per_product = 1 + 12 + len(list(combinations(range(12), 2)))
    blocks_per_task = 8 * blocks_per_product
    cases = []
    for case in scenario_manifest["cases"]:
        depots = int(case["num_depots"])
        cases.append(
            {
                "case_id": case["case_id"],
                "depots": depots,
                "product_local_blocks": blocks_per_task,
                "estimated_model_variables": blocks_per_task * (depots * 12 + 12 + 1),
                "estimated_model_constraints": blocks_per_task * (12 + depots + 1),
                "logical_scenario_rows": FORMAL_SCENARIO_COUNT,
            }
        )
    return {
        "schema_version": "1.0",
        "classification": "STRUCTURAL_PREFLIGHT_ONLY_NO_FULL_SCENARIO_SOLVE",
        "formal_run_authorized": False,
        "independent_policy_count": 2,
        "case_policy_task_count": 16,
        "blocks_per_task": blocks_per_task,
        "logical_scenario_rows_total": 16 * FORMAL_SCENARIO_COUNT,
        "threads": 1,
        "cases": cases,
        "maximum_estimated_model_variables": max(row["estimated_model_variables"] for row in cases),
        "maximum_estimated_model_constraints": max(row["estimated_model_constraints"] for row in cases),
        "pilot_observation": {
            "scenario_count": len(pilot_checkpoint["evaluation"]["scenarios"]),
            "unique_product_local_blocks": pilot_checkpoint["evaluation"]["unique_product_local_blocks"],
            "runtime_seconds": pilot_checkpoint["runtime_seconds"],
            "peak_process_rss_bytes": pilot_checkpoint["peak_process_rss_bytes"],
        },
        "admission_status": "FULL_CASE_RESOURCE_PREFLIGHT_STILL_REQUIRED",
    }


def validate_checkpoint(
    checkpoint_path: Path,
    *,
    instance_sha256: str,
    policy_sha256: str,
    scenario_manifest_sha256_value: str,
    code_sha256: str,
    config_sha256: str,
) -> dict[str, Any]:
    digest_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".sha256")
    if not checkpoint_path.exists() or not digest_path.exists():
        raise FileNotFoundError("checkpoint or checkpoint digest is missing")
    recorded_digest = digest_path.read_text(encoding="utf-8").strip()
    if file_sha256(checkpoint_path) != recorded_digest:
        raise ValueError("checkpoint content hash mismatch")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    expected = {
        "instance_sha256": instance_sha256,
        "policy_sha256": policy_sha256,
        "scenario_manifest_sha256": scenario_manifest_sha256_value,
        "code_sha256": code_sha256,
        "config_sha256": config_sha256,
    }
    for key, value in expected.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"checkpoint identity mismatch: {key}")
    if checkpoint.get("classification") != "PILOT_NON_PUBLISHABLE":
        raise ValueError("checkpoint is not an eligible pilot checkpoint")
    return checkpoint


def write_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    write_json(path, checkpoint)
    path.with_suffix(path.suffix + ".sha256").write_text(
        file_sha256(path) + "\n", encoding="utf-8"
    )


def run_pilot(
    root: Path,
    identity_manifest_path: Path,
    scenario_manifest_path: Path,
    output_dir: Path,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    identity_manifest = json.loads(identity_manifest_path.read_text(encoding="utf-8"))
    scenario_manifest = json.loads(scenario_manifest_path.read_text(encoding="utf-8"))
    validate_manifest_hash(identity_manifest)
    validate_manifest_hash(scenario_manifest)
    if scenario_manifest.get("formal_run_authorized") is not False:
        raise ValueError("pilot requires formal_run_authorized=false")
    case_id = scenario_manifest["pilot_case_id"]
    policy_id = scenario_manifest["pilot_policy_id"]
    selected_ids = list(scenario_manifest["pilot_scenario_ids"])
    if len(selected_ids) > min(PILOT_MAX_SCENARIOS, scenario_manifest["pilot_max_scenarios"]):
        raise ValueError("pilot scenario count exceeds the frozen safety limit")
    policy_row = next(
        row for row in identity_manifest["policies"] if row["policy_id"] == policy_id
    )
    if not policy_row["pilot_authorized"] or policy_row["formal_authorized"]:
        raise PermissionError("policy is not authorized for pilot-only evaluation")
    policy = policy_from_manifest(root, policy_row)
    case_row = next(row for row in scenario_manifest["cases"] if row["case_id"] == case_id)
    instance_path = root / case_row["instance_path"]
    if file_sha256(instance_path) != case_row["instance_sha256"]:
        raise ValueError("pilot instance hash mismatch")
    instance = load_instance(instance_path)
    if scenario_manifest_sha256(instance) != case_row["scenario_order_sha256"]:
        raise ValueError("pilot scenario-order hash mismatch")
    code_path = Path(__file__)
    code_hash = file_sha256(code_path)
    config_hash = scenario_manifest["manifest_payload_sha256"]
    checkpoint_path = output_dir / "checkpoint.json"
    if resume:
        return validate_checkpoint(
            checkpoint_path,
            instance_sha256=case_row["instance_sha256"],
            policy_sha256=policy.coordinates_sha256,
            scenario_manifest_sha256_value=case_row["scenario_order_sha256"],
            code_sha256=code_hash,
            config_sha256=config_hash,
        )
    start = time.perf_counter()
    with _PeakMemoryMonitor() as monitor:
        evaluation = evaluate_fixed_policy_scenarios(
            instance, policy, selected_ids, threads=scenario_manifest["threads"]
        )
    runtime = time.perf_counter() - start
    checkpoint = {
        "schema_version": "1.0",
        "classification": "PILOT_NON_PUBLISHABLE",
        "experiment_id": scenario_manifest["experiment_id"],
        "case_id": case_id,
        "policy_id": policy.policy_id,
        "instance_sha256": case_row["instance_sha256"],
        "policy_sha256": policy.coordinates_sha256,
        "scenario_manifest_sha256": case_row["scenario_order_sha256"],
        "code_sha256": code_hash,
        "config_sha256": config_hash,
        "solver_profile_id": scenario_manifest["solver_profile_id"],
        "solver_version": scenario_manifest["solver_version"],
        "threads": scenario_manifest["threads"],
        "runtime_seconds": runtime,
        "peak_process_rss_bytes": monitor.peak_bytes,
        "evaluation": evaluation,
        "pilot_metric_summary": summarize_partial_policy_metrics(
            evaluation["scenarios"]
        ),
    }
    write_checkpoint(checkpoint_path, checkpoint)
    write_json(
        output_dir / "hashes.json",
        {
            "checkpoint.json": file_sha256(checkpoint_path),
            "checkpoint.json.sha256": file_sha256(checkpoint_path.with_suffix(".json.sha256")),
            "identity_manifest": file_sha256(identity_manifest_path),
            "scenario_manifest": file_sha256(scenario_manifest_path),
        },
    )
    return checkpoint


def static_source_audit(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called_names.add(node.func.attr)
    hits = sorted(set(FORBIDDEN_FIRST_STAGE_CALLS) & called_names)
    return {
        "source_path": path.as_posix(),
        "source_sha256": file_sha256(path),
        "forbidden_first_stage_call_hits": hits,
        "pass": not hits,
    }
