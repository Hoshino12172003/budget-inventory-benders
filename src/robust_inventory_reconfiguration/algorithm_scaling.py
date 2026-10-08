from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import comb
from pathlib import Path
from typing import Iterable

from .e1c_scaling import ScalingDimensions, scaling_size
from .instance import InventoryInstance


METHODS = (
    "pure_benders",
    "aggregate_benders_structured_oracle",
    "prb_benders",
)
SIZES = (
    ScalingDimensions("L10", 25, 24, 12),
    ScalingDimensions("XL10", 30, 30, 14),
    ScalingDimensions("XXL10", 36, 36, 16),
)
SEEDS = tuple(range(20260921, 20260931))
SOURCE_CASES = (
    "210129", "210202", "210310", "210323",
    "210330", "210428", "210611", "210628",
)
GAMMA = 2
BETA = 1.0
LAMBDA_R = 0.05
SERVICE_LEVEL = 0.90
PHI_MULTIPLIER = 1.85


@dataclass(frozen=True)
class ScalingCondition:
    condition_id: str
    method: str
    size: str
    seed: int
    instance_id: str


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity(root: Path, files: Iterable[str]) -> str:
    return canonical_hash([
        {"path": path, "sha256": file_sha256(root / path)}
        for path in files
    ])


def load_config(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_config(config: dict) -> None:
    family = config["instance_family"]
    scientific = config["fixed_scientific_parameters"]
    resource = config["resource_policy"]
    checks = {
        "methods": tuple(config["methods"]) == METHODS,
        "sizes": family["sizes"] == [
            {"label": item.scale, "I": item.depots, "R": item.regions, "J": item.products}
            for item in SIZES
        ],
        "seeds": tuple(family["seeds"]) == SEEDS,
        "sources": tuple(family["source_case_ids"]) == SOURCE_CASES,
        "Gamma": scientific["Gamma"] == GAMMA,
        "beta": scientific["beta"] == BETA,
        "lambda_R": scientific["lambda_R"] == LAMBDA_R,
        "SL": scientific["SL"] == SERVICE_LEVEL,
        "phi_multiplier": scientific["phi_multiplier"] == PHI_MULTIPLIER,
        "soft_service": scientific["service_constraint"] == "soft SLA",
        "no_sensitivity": config["management_sensitivity_dimensions"] == [],
        "authorization": config["authorization_transition"] in ([False], [False, True])
        and config["authorization_transition"][-1] is config["formal_run_authorized"],
        "exact": config["algorithm"]["exact_certification_required"] is True,
        "counts": config["expected_instance_count"] == 30
        and config["expected_physical_runs"] == 90,
        "direct": config["direct_reference"]["enabled"] is False
        and config["expected_direct_runs"] == 0,
        "sequential": resource["execution"] == "sequential"
        and resource["parallel_workers"] == 1,
        "memory": resource["machine_ram_gib"] == 32
        and resource["fail_closed"] is True
        and resource["minimum_available_memory_gib_by_size"] == {
            "L10": 7, "XL10": 10, "XXL10": 16,
        }
        and resource["maximum_process_tree_memory_gib_by_size"] == {
            "L10": 4, "XL10": 7, "XXL10": 13,
        }
        and resource["minimum_system_available_memory_gib"] == 3,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"invalid algorithm-scaling formal config: {','.join(failed)}")


def enumerate_conditions() -> list[ScalingCondition]:
    return [
        ScalingCondition(
            condition_id=f"ASC_{size.scale}_S{seed}_{method.upper()}",
            method=method,
            size=size.scale,
            seed=seed,
            instance_id=f"ASC_INSTANCE_{size.scale}_S{seed}",
        )
        for size in SIZES
        for seed in SEEDS
        for method in METHODS
    ]


def size_by_label(label: str) -> ScalingDimensions:
    try:
        return next(item for item in SIZES if item.scale == label)
    except StopIteration as error:
        raise ValueError(f"unknown scaling size: {label}") from error


def instance_characteristics(dimensions: ScalingDimensions) -> dict[str, int | str]:
    values = scaling_size(dimensions, gamma=GAMMA)
    structured_oracle_variables = values["prb_product_risk_blocks"] * (
        dimensions.depots * dimensions.regions + dimensions.regions + 1
    )
    return {
        "size": dimensions.scale,
        "I": dimensions.depots,
        "R": dimensions.regions,
        "J": dimensions.products,
        "uncertainty_components": dimensions.regions * dimensions.products,
        "scenario_related_dimensions": sum(comb(dimensions.regions, g) for g in range(GAMMA + 1)),
        "estimated_master_variables_pure": values["first_stage_variables"] + 1,
        "estimated_master_variables_structured_aggregate": values["first_stage_variables"] + 1,
        "estimated_master_variables_prb": values["first_stage_variables"] + values["prb_master_surrogates"],
        "estimated_oracle_variables_pure": values["pure_total_variables"],
        "estimated_oracle_product_risk_blocks": values["prb_product_risk_blocks"],
        "actual_master_variables_pure_formula": values["first_stage_variables"] + 1,
        "actual_master_variables_structured_aggregate_formula": values["first_stage_variables"] + 1,
        "actual_master_variables_prb_formula": values["first_stage_variables"] + values["prb_master_surrogates"],
        "actual_oracle_variables_pure_formula": values["pure_total_variables"],
        "actual_oracle_variables_structured_total_formula": structured_oracle_variables,
        **values,
    }


def validate_scientific_parameters(instance: InventoryInstance) -> dict[str, bool]:
    expected_phi = [
        PHI_MULTIPLIER * max(instance.shortage_penalty[r][j] for r in range(instance.num_regions))
        for j in range(instance.num_products)
    ]
    checks = {
        "SL": all(abs(value - SERVICE_LEVEL) <= 1e-12 for value in instance.service_level),
        "phi": all(
            abs(actual - expected) <= 1e-10
            for actual, expected in zip(instance.service_penalty, expected_phi, strict=True)
        ),
        "soft_service_data": len(instance.service_level) == instance.num_products
        and len(instance.service_penalty) == instance.num_products,
    }
    return {**checks, "pass": all(checks.values())}


def resource_dimension_check(config: dict, dimensions: ScalingDimensions) -> dict[str, bool]:
    characteristics = instance_characteristics(dimensions)
    caps = config["dimension_caps"]
    checks = {
        "I": dimensions.depots <= caps["max_I"],
        "R": dimensions.regions <= caps["max_R"],
        "J": dimensions.products <= caps["max_J"],
        "product_risk_blocks": characteristics["prb_product_risk_blocks"]
        <= caps["max_product_risk_blocks"],
        "pure_total_variables": characteristics["pure_total_variables"]
        <= caps["max_pure_total_variables"],
        "pure_constraints": characteristics["pure_constraints"] <= caps["max_pure_constraints"],
    }
    return {**checks, "pass": all(checks.values())}


def resource_thresholds(config: dict, size: str) -> dict[str, float]:
    size_by_label(size)
    policy = config["resource_policy"]
    return {
        "minimum_available_memory_gib": float(
            policy["minimum_available_memory_gib_by_size"][size]
        ),
        "maximum_process_tree_memory_gib": float(
            policy["maximum_process_tree_memory_gib_by_size"][size]
        ),
        "minimum_system_available_memory_gib": float(
            policy["minimum_system_available_memory_gib"]
        ),
    }


def resource_preflight_passes(config: dict, size: str, samples_gib: Iterable[float]) -> bool:
    samples = tuple(float(value) for value in samples_gib)
    if not samples:
        raise ValueError("resource preflight requires at least one memory sample")
    return min(samples) >= resource_thresholds(config, size)["minimum_available_memory_gib"]


def normalized_trajectory(rows: list[dict], final_lower_bound: float) -> list[dict]:
    if final_lower_bound == 0:
        raise ValueError("cannot normalize a zero final lower bound")
    normalized = []
    for row in rows:
        value = dict(row)
        value["LB"] = value.pop("lower_bound")
        value["UB"] = value.pop("upper_bound")
        value["gap"] = value.pop("relative_gap")
        value["normalized_LB"] = value["LB"] / final_lower_bound
        value["cuts_added"] = int(value.get("cuts_added", value.get("cut_added", 0)))
        normalized.append(value)
    return normalized


def dry_run_plan(config: dict) -> dict:
    validate_config(config)
    conditions = enumerate_conditions()
    by_size = {
        size.scale: sum(condition.size == size.scale for condition in conditions)
        for size in SIZES
    }
    by_method = {
        method: sum(condition.method == method for condition in conditions)
        for method in METHODS
    }
    return {
        "experiment_id": config["experiment_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "optimization_calls": 0,
        "sizes": [instance_characteristics(size) for size in SIZES],
        "seeds": list(SEEDS),
        "methods": list(METHODS),
        "instances": len(SIZES) * len(SEEDS),
        "physical_runs": len(conditions),
        "runs_by_size": by_size,
        "runs_by_method": by_method,
        "direct_runs": 0,
        "shared_instance_preparations": len(SIZES) * len(SEEDS),
        "management_sensitivity_dimensions": [],
        "scientific_parameters": config["fixed_scientific_parameters"],
        "sequential_execution": True,
        "resource_thresholds_by_size": {
            size.scale: resource_thresholds(config, size.scale) for size in SIZES
        },
        "conditions": [condition.__dict__ for condition in conditions],
    }


def require_formal_authorization(config: dict) -> None:
    if config.get("formal_run_authorized") is not True:
        raise PermissionError("ALGORITHM_SCALING_FORMAL_RUN_NOT_AUTHORIZED")
