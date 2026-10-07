from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path

from .instance import InventoryInstance


FORMAL_CASES = (
    "210129", "210202", "210310", "210323",
    "210330", "210428", "210611", "210628",
)
SL_GRID = (0.85, 0.90, 0.95)
PHI_GRID = (1.50, 1.85, 2.50)
BASELINE_SL = 0.90
BASELINE_PHI_MULTIPLIER = 1.85
GAMMA = 2
BETA = 1.0
LAMBDA_R = 0.05


@dataclass(frozen=True)
class ServiceCalibrationCondition:
    case_id: str
    condition_id: str
    physical_result_id: str
    run_type: str
    service_level: float
    phi_multiplier: float
    baseline: bool
    requires_solve: bool


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config(path: str | Path) -> dict:
    # The repository's *.yaml formal configs use the JSON subset of YAML.
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_config(config: dict) -> None:
    checks = {
        "cases": config["case_ids"] == list(FORMAL_CASES),
        "sl_grid": config["sl_grid"] == list(SL_GRID),
        "phi_grid": config["phi_multiplier_grid"] == list(PHI_GRID),
        "baseline_sl": config["baseline"]["SL"] == BASELINE_SL,
        "baseline_phi": config["baseline"]["phi_multiplier"] == BASELINE_PHI_MULTIPLIER,
        "Gamma": config["fixed_parameters"]["Gamma"] == GAMMA,
        "beta": config["fixed_parameters"]["beta"] == BETA,
        "lambda_R": config["fixed_parameters"]["lambda_R"] == LAMBDA_R,
        "ofat": config["design"] == "OFAT",
        "no_interaction": config["full_SL_x_phi_interaction_authorized"] is False,
        "authorization_history": config["authorization_transition"] in ([False], [False, True]),
        "authorization_state": config["authorization_transition"][-1] is config["formal_run_authorized"],
        "solve_count": config["expected_new_optimization_solves"] == 32,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"invalid service-calibration formal config: {','.join(failed)}")


def phi_vector(instance: InventoryInstance, multiplier: float) -> list[float]:
    if multiplier <= 0:
        raise ValueError("phi_multiplier must be positive")
    return [
        multiplier * max(instance.shortage_penalty[r][j] for r in range(instance.num_regions))
        for j in range(instance.num_products)
    ]


def calibrated_instance(
    instance: InventoryInstance,
    *,
    service_level: float,
    phi_multiplier: float,
) -> InventoryInstance:
    if not 0 < service_level < 1:
        raise ValueError("service_level must be strictly between zero and one")
    provenance = dict(instance.provenance)
    provenance["service_calibration"] = {
        "SL": service_level,
        "phi_multiplier": phi_multiplier,
        "phi_definition": "phi_j = phi_multiplier * max_r p_rj",
        "sla_semantics": "soft",
    }
    return replace(
        instance,
        service_level=[service_level] * instance.num_products,
        service_penalty=phi_vector(instance, phi_multiplier),
        provenance=provenance,
    )


def _sl_token(value: float) -> str:
    return f"SL{round(value * 100):02d}"


def _phi_token(value: float) -> str:
    return f"PHI{round(value * 100):03d}"


def enumerate_conditions() -> list[ServiceCalibrationCondition]:
    conditions: list[ServiceCalibrationCondition] = []
    for case_id in FORMAL_CASES:
        for sl in SL_GRID:
            baseline = sl == BASELINE_SL
            conditions.append(ServiceCalibrationCondition(
                case_id=case_id,
                condition_id=f"SC-{case_id}-{_sl_token(sl)}",
                physical_result_id=f"SC-{case_id}-BASELINE" if baseline else f"SC-{case_id}-{_sl_token(sl)}",
                run_type="sl_sensitivity",
                service_level=sl,
                phi_multiplier=BASELINE_PHI_MULTIPLIER,
                baseline=baseline,
                requires_solve=not baseline,
            ))
        for multiplier in PHI_GRID:
            baseline = multiplier == BASELINE_PHI_MULTIPLIER
            conditions.append(ServiceCalibrationCondition(
                case_id=case_id,
                condition_id=f"SC-{case_id}-{_phi_token(multiplier)}",
                physical_result_id=f"SC-{case_id}-BASELINE" if baseline else f"SC-{case_id}-{_phi_token(multiplier)}",
                run_type="phi_sensitivity",
                service_level=BASELINE_SL,
                phi_multiplier=multiplier,
                baseline=baseline,
                requires_solve=not baseline,
            ))
    return conditions


def new_solve_conditions() -> list[ServiceCalibrationCondition]:
    return [condition for condition in enumerate_conditions() if condition.requires_solve]


def dry_run_plan(config: dict) -> dict:
    validate_config(config)
    conditions = enumerate_conditions()
    new_solves = new_solve_conditions()
    return {
        "experiment_id": config["experiment_id"],
        "formal_run_authorized": config["formal_run_authorized"],
        "design": "OFAT",
        "full_SL_x_phi_interaction_authorized": False,
        "sl_sensitivity": {
            "table_conditions": sum(c.run_type == "sl_sensitivity" for c in conditions),
            "potentially_reusable_baseline_conditions": sum(c.run_type == "sl_sensitivity" and c.baseline for c in conditions),
            "new_solves": sum(c.run_type == "sl_sensitivity" for c in new_solves),
        },
        "phi_sensitivity": {
            "table_conditions": sum(c.run_type == "phi_sensitivity" for c in conditions),
            "potentially_reusable_baseline_conditions": sum(c.run_type == "phi_sensitivity" and c.baseline for c in conditions),
            "new_solves": sum(c.run_type == "phi_sensitivity" for c in new_solves),
        },
        "reported_OFAT_conditions": len(conditions),
        "unique_physical_results": len({c.physical_result_id for c in conditions}),
        "unique_physical_baseline_results": len({c.physical_result_id for c in conditions if c.baseline}),
        "new_formal_optimization_solves_if_baseline_reuse_authorized": len(new_solves),
        "conditions": [condition.__dict__ for condition in conditions],
    }


def require_formal_authorization(config: dict) -> None:
    if config.get("formal_run_authorized") is not True:
        raise PermissionError("SERVICE_CALIBRATION_FORMAL_RUN_NOT_AUTHORIZED")
