from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import pandas as pd


RAW = "renault_data_pipeline/data/renault_raw/instances/instances"
PROCESSED = "renault_data_pipeline/data/renault_processed"
FORMAL_CASES = {"210202", "210628"}
SELECTED_PRODUCTS = {
    "BAC---1041", "BAC-O-4312", "BAC-O-4325", "BAC-O-6423",
    "BAC-O-6433", "CON-S-0130", "SLI---0770", "SLI---1200",
}


def read_csv(archive: zipfile.ZipFile, member: str, **kwargs: object) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(archive.read(member)), **kwargs)


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def direct_size(i_count: int, r_count: int, j_count: int, gamma: int = 2) -> tuple[int, int]:
    scenarios = sum(math.comb(r_count, k) for k in range(gamma + 1))
    allocations = math.comb(j_count + gamma, gamma)
    variables = (
        i_count + 3 * i_count * j_count + j_count * (gamma + 1)
        + j_count * scenarios * (i_count * r_count + r_count + 1) + 1
    )
    constraints = (
        i_count + 2 * i_count * j_count + 1
        + j_count * scenarios * (r_count + i_count + 2) + allocations
    )
    return variables, constraints


def component(case: str, missing: str) -> str:
    return "READY_EXISTING_FORMAL_INSTANCE" if case in FORMAL_CASES else missing


def audit(archive_path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        unsafe = [
            name for name in names
            if name.startswith("/") or ".." in name.replace("\\", "/").split("/")
            or (len(name) > 1 and name[1] == ":")
        ]
        if unsafe:
            raise ValueError(f"unsafe ZIP members: {unsafe[:3]}")
        cases = sorted({
            name.split("/")[3] for name in names
            if name.startswith(PROCESSED + "/") and len(name.split("/")) > 4
        })
        rows: list[dict[str, object]] = []
        for case in cases:
            processed = f"{PROCESSED}/{case}"
            raw = f"{RAW}/{case}"
            source_audit = json.loads(
                archive.read(f"{processed}/audit.json").decode("utf-8-sig")
            )
            constants = source_audit["constants"]
            counts = source_audit["counts"]
            depots = read_csv(archive, f"{processed}/depots.csv", dtype=str)
            customers = read_csv(archive, f"{processed}/customers.csv", dtype=str)
            products = read_csv(archive, f"{processed}/commodities.csv", dtype=str)
            inventory = read_csv(archive, f"{processed}/depot_commodity.csv", dtype=str)
            customer_cost = read_csv(archive, f"{processed}/customer_commodity.csv", dtype=str)
            demand = read_csv(archive, f"{processed}/demand_daily.csv", dtype=str)
            demand["demand"] = pd.to_numeric(demand["demand"], errors="coerce")
            demand_pairs = demand.groupby(["customer_code", "commodity_code"])["demand"].sum()
            x0 = pd.to_numeric(inventory["initial_inventory"], errors="coerce")
            duplicates = int(inventory.duplicated(["depot_code", "commodity_code"]).sum())
            nonfinite = int(sum(not math.isfinite(float(v)) for v in x0.dropna()))
            x0_errors = int(x0.isna().sum()) + nonfinite
            root_files = (
                "general_constants.csv", "commodity_lengths.csv", "depots_codes.csv",
                "customers_codes.csv", "distances.csv", "transport_durations.csv",
            )
            raw_complete = all(f"{raw}/{name}" in names for name in root_files)
            raw_complete &= all(
                f"{raw}/depot_{depot}/{name}" in names
                for depot in depots["depot_code"]
                for name in ("global.csv", "per_commodity.csv", "maximum_stock.csv", "release.csv")
            )
            raw_complete &= all(
                f"{raw}/customer_{customer}/{name}" in names
                for customer in customers["customer_code"]
                for name in ("global.csv", "per_commodity.csv", "maximum_stock.csv", "demand.csv")
            )
            ready = case in FORMAL_CASES
            variables, constraints = direct_size(15, 12, 8) if ready else (None, None)
            rows.append({
                "case_id": case,
                "source_file_identity": raw + "/",
                "processed_audit_crc32": f"{archive.getinfo(f'{processed}/audit.json').CRC:08x}",
                "customer_count": int(counts["customers"]),
                "depot_count": int(counts["depots"]),
                "product_count": int(counts["commodities"]),
                "planning_days": int(constants["T"]),
                "demand_record_count": int(counts["demand_daily_rows"]),
                "inventory_record_count": len(inventory),
                "nonzero_demand_pairs": int((demand_pairs != 0).sum()),
                "nonzero_inventory_pairs": int((x0 != 0).sum()),
                "demand_pair_density": float((demand_pairs != 0).sum() / (len(customers) * len(products))),
                "inventory_pair_density": float((x0 != 0).sum() / (len(depots) * len(products))),
                "distance_field_available": f"{raw}/distances.csv" in names,
                "km_cost_field_available": "km_cost" in constants,
                "inventory_cost_field_available": "excess_inventory_cost" in inventory,
                "shortage_cost_field_available": "shortage_cost" in customer_cost,
                "x0_reconstructible": (
                    len(inventory) == len(depots) * len(products)
                    and duplicates == 0 and x0_errors == 0
                ),
                "x0_duplicate_pairs": duplicates,
                "x0_missing_or_nonfinite": x0_errors,
                "raw_normalizer_consumable": bool(raw_complete),
                "selected_8_products_present": SELECTED_PRODUCTS.issubset(set(products["commodity_code"])),
                "geographic_mapping_status": component(case, "RAW_COORDINATES_AVAILABLE_FORMAL_MAPPING_RULE_MISSING"),
                "common_region_construction_status": component(case, "FORMAL_RULE_MISSING"),
                "product_selection_status": component(case, "RAW_INPUT_AVAILABLE_FORMAL_RANKING_RULE_MISSING"),
                "demand_aggregation_status": component(case, "RAW_INPUT_AVAILABLE_FORMAL_TRANSFORM_MISSING"),
                "demand_deviation_status": component(case, "RAW_INPUT_AVAILABLE_FORMAL_TRANSFORM_MISSING"),
                "x0_construction_status": (
                    "READY_EXISTING_FROZEN_BASELINE" if ready
                    else "RAW_OBSERVED_VALUE_AVAILABLE_BASELINE_RULE_MISSING"
                ),
                "capacity_proxy_status": component(case, "RAW_INPUT_AVAILABLE_FORMAL_TRANSFORM_MISSING"),
                "inventory_ub_status": component(case, "RAW_INPUT_AVAILABLE_FORMAL_TRANSFORM_MISSING"),
                "inventory_cost_status": component(case, "RAW_INPUT_AVAILABLE_FORMAL_TRANSFORM_MISSING"),
                "shortage_cost_status": component(case, "RAW_INPUT_AVAILABLE_FORMAL_TRANSFORM_MISSING"),
                "transport_cost_status": component(case, "RAW_INPUT_AVAILABLE_FORMAL_TRANSFORM_MISSING"),
                "fixed_cost_status": component(case, "CALIBRATION_RULE_NOT_IN_ARCHIVE"),
                "service_parameters_status": component(case, "CALIBRATION_RULE_NOT_IN_ARCHIVE"),
                "b_ref_inputs_status": (
                    "READY_FROZEN_INCUMBENT_AND_B_REF" if ready
                    else "BLOCKED_BY_MISSING_FORMAL_INSTANCE_AND_INCUMBENT"
                ),
                "formal_pipeline_consumable": ready,
                "compatibility_classification": (
                    "READY_WITH_EXISTING_PIPELINE" if ready
                    else "REQUIRES_NEW_MODELING_ASSUMPTION"
                ),
                "post_I": 15 if ready else None,
                "post_R": 12 if ready else None,
                "post_J": 8 if ready else None,
                "uncertainty_items": 96 if ready else None,
                "expected_direct_variables_gamma2": variables,
                "expected_direct_constraints_gamma2": constraints,
                "post_processing_dimensions_status": "FROZEN" if ready else "NOT_FROZEN",
            })
    return rows, {
        "archive_sha256": archive_sha256(archive_path),
        "zip_entry_count": len(names),
        "raw_case_count": len(rows),
        "case_ids": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Renault raw cases without optimization.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=Path("table_renault_case_inventory.csv"))
    args = parser.parse_args()
    rows, summary = audit(args.archive)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
