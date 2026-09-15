from __future__ import annotations

import hashlib
import json
from pathlib import Path

from robust_inventory_reconfiguration.e1c_scaling import (
    ScalingDimensions,
    build_renault_calibrated_instance,
    extract_renault_calibration,
    scaling_size,
    validate_generated_instance,
)
from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.renault_empirical import sha256_file


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/e1c_scaling_design.json"
CASES = ("210129", "210202", "210310", "210323", "210330", "210428", "210611", "210628")


def sources():
    return [load_instance(ROOT / f"data/formal_instances_v2/{case}.json") for case in CASES]


def canonical_hash(instance) -> str:
    payload = json.dumps(instance.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def test_design_is_fail_closed_and_balanced() -> None:
    design = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert design["formal_run_authorized"] is False
    assert design["development_solve_authorized"] is False
    assert design["resource_probe_authorized"] is False
    assert design["instance_generation_authorized"] is False
    assert design["baseline_preparation_authorized"] is False
    assert design["Gamma"] == 2
    assert design["replicate_seeds"] == [20260911, 20260912, 20260913, 20260914, 20260915]
    assert design["expected_formal_runs"] == 3 * 5 * 4 == 60
    assert design["timeout_seconds_per_run"] == 900
    assert design["gamma_rule_audit"]["recommended"] == "FIXED_GAMMA_2"
    assert design["gamma_rule_audit"]["proportional_candidate_values"] == {
        "S": 2,
        "M": 4,
        "L": 6,
    }
    assert design["development_resource_probe_proposal"]["status"] == (
        "PROPOSAL_ONLY_NOT_AUTHORIZED"
    )
    assert design["replicate_freeze_rule"]["default"] == 5
    assert sha256_file(ROOT / design["generator"]["path"]) == design["generator"]["sha256"]
    assert design["source_instance_hashes"] == {
        case: sha256_file(ROOT / f"data/formal_instances_v2/{case}.json") for case in CASES
    }


def test_frozen_calibration_statistics_recompute_exactly() -> None:
    design = json.loads(CONFIG.read_text(encoding="utf-8"))
    actual = extract_renault_calibration(sources())
    frozen = design["calibration_statistics"]
    for key in (
        "nominal_demand",
        "deviation_to_nominal_ratio_positive_demand",
        "depot_capacity_to_system_volume_demand",
        "inventory_ub_to_product_nominal_demand",
        "transport_cost_per_product_volume",
        "fixed_cost_per_system_nominal_demand",
        "holding_cost",
        "shortage_penalty",
        "service_penalty",
        "product_volume",
    ):
        assert actual[key] == frozen[key]


def test_static_size_counts_match_known_renault_scale() -> None:
    size = scaling_size(ScalingDimensions("S", 15, 12, 8), gamma=2)
    assert size["first_stage_variables"] == 375
    assert size["pure_binary_variables"] == 96
    assert size["pure_total_variables"] == 512
    assert size["pure_constraints"] == 2113
    assert size["prb_product_risk_blocks"] == 632
    assert size["prb_master_surrogates"] == 25
    assert size["direct_variables"] == 122376
    assert size["direct_constraints"] == 18629


def test_pre_freeze_gamma_and_xl_size_audit_is_reproducible() -> None:
    design = json.loads(CONFIG.read_text(encoding="utf-8"))
    proportional = {"S": 2, "M": 4, "L": 6}
    for dimensions in design["recommended_scale_grid"]:
        scale = dimensions["scale"]
        size = scaling_size(
            ScalingDimensions(scale, dimensions["I"], dimensions["R"], dimensions["J"]),
            gamma=proportional[scale],
        )
        if scale == "M":
            assert size["prb_product_risk_blocks"] == 25170
            assert size["direct_variables"] == 8482961
        if scale == "L":
            assert size["prb_product_risk_blocks"] == 2280612
            assert size["direct_variables"] == 1425383510
    for anchor in design["candidate_XL_search_box"]["anchors"]:
        size = scaling_size(
            ScalingDimensions(
                anchor["name"], anchor["I"], anchor["R"], anchor["J"]
            ),
            gamma=anchor["Gamma"],
        )
        assert size["pure_total_variables"] == anchor["pure_total_variables"]
        assert size["pure_constraints"] == anchor["pure_constraints"]
        assert size["prb_product_risk_blocks"] == anchor["product_risk_blocks"]
        assert size["direct_variables"] == anchor["direct_variables"]
        assert size["direct_constraints"] == anchor["direct_constraints"]


def test_generator_is_deterministic_valid_and_seed_sensitive() -> None:
    source = sources()
    dimensions = ScalingDimensions("S", 15, 12, 8)
    first = build_renault_calibrated_instance(source, dimensions, 20260911)
    repeated = build_renault_calibrated_instance(source, dimensions, 20260911)
    alternate = build_renault_calibrated_instance(source, dimensions, 20260912)
    assert canonical_hash(first) == canonical_hash(repeated)
    assert canonical_hash(first) != canonical_hash(alternate)
    assert (first.num_depots, first.num_regions, first.num_products) == (15, 12, 8)
    assert first.initial_inventory is None
    assert first.provenance["x0_status"] == "REQUIRES_FROZEN_GAMMA0_NOMINAL_BASELINE_PREPARATION"
    assert sorted(first.provenance["product_donors"]) == list(range(8))
    assert validate_generated_instance(first, dimensions, 20260911)["pass"]


def test_generated_economic_values_trace_to_empirical_donors() -> None:
    source = sources()
    generated = build_renault_calibrated_instance(
        source, ScalingDimensions("M", 20, 16, 10), 20260911
    )
    product_donors = generated.provenance["product_donors"]
    demand_donors = generated.provenance["demand_donors"]
    for r, (case, donor_region) in enumerate(demand_donors):
        for j, product in enumerate(product_donors):
            assert generated.base_demand[r][j] == source[case].base_demand[donor_region][product]
            assert generated.demand_deviation[r][j] == source[case].demand_deviation[donor_region][product]
            assert generated.shortage_penalty[r][j] == source[case].shortage_penalty[donor_region][product]
    observed_normalized_transport = {
        round(instance.transport_cost[i][r][j] / instance.product_volume[j], 14)
        for instance in source
        for i in range(instance.num_depots)
        for r in range(instance.num_regions)
        for j in range(instance.num_products)
    }
    assert all(
        round(generated.transport_cost[i][r][j] / generated.product_volume[j], 14)
        in observed_normalized_transport
        for i in range(generated.num_depots)
        for r in range(generated.num_regions)
        for j in range(generated.num_products)
    )
