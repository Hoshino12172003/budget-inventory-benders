from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path


CASES = ("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
RAW_PREFIX = "renault_data_pipeline/data/renault_raw/instances/instances"
PROCESSED_PREFIX = "renault_data_pipeline/data/renault_processed"
PRODUCTS = (
    "BAC---1041", "BAC-O-4312", "BAC-O-4325", "BAC-O-6423",
    "BAC-O-6433", "CON-S-0130", "SLI---0770", "SLI---1200",
)
EXPECTED_DEPOTS = {
    "210202": 15, "210628": 15, "210129": 15, "210310": 16,
    "210330": 11, "210323": 13, "210428": 18, "210611": 19,
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_csv(archive: zipfile.ZipFile, member: str) -> list[dict[str, str]]:
    text = io.TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="")
    try:
        return list(csv.DictReader(text))
    finally:
        text.close()


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    value = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, value)))


def distance_matrix(points: list[tuple[float, float]]) -> list[list[float]]:
    return [[haversine(left, right) for right in points] for left in points]


def stable_common_medoids(
    locations: dict[str, tuple[float, float]], count: int = 12
) -> tuple[list[str], int]:
    ids = sorted(locations)
    points = [locations[value] for value in ids]
    distances = distance_matrix(points)
    medoids = [min(range(len(ids)), key=lambda i: (sum(distances[i]), ids[i]))]
    while len(medoids) < count:
        nearest = [min(distances[i][m] for m in medoids) for i in range(len(ids))]
        medoids.append(max(range(len(ids)), key=lambda i: (nearest[i], -i)))
    for iteration in range(100):
        labels = [min(range(count), key=lambda k: (distances[i][medoids[k]], k)) for i in range(len(ids))]
        updated = []
        for cluster in range(count):
            members = [i for i, label in enumerate(labels) if label == cluster]
            updated.append(
                min(members, key=lambda i: (sum(distances[i][j] for j in members), ids[i]))
            )
        if updated == medoids:
            break
        medoids = updated
    else:
        raise RuntimeError("deterministic medoid update did not converge")
    selected = [ids[index] for index in medoids]
    selected.sort(key=lambda value: (locations[value][1], locations[value][0], value))
    return selected, iteration + 1


def nearest_region(
    point: tuple[float, float], centers: list[tuple[float, float]]
) -> int:
    return min(range(len(centers)), key=lambda index: (haversine(point, centers[index]), index)) + 1


def minimum_row_permutation_l1(
    candidate: list[list[float]], target: list[list[float]]
) -> tuple[float, float, int]:
    costs = [[sum(abs(a - b) for a, b in zip(left, right)) for right in target] for left in candidate]
    states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, ())}
    for left in range(len(candidate)):
        updated: dict[int, tuple[float, tuple[int, ...]]] = {}
        for mask, (value, order) in states.items():
            for right in range(len(target)):
                if mask & (1 << right):
                    continue
                new_mask = mask | (1 << right)
                proposal = (value + costs[left][right], order + (right,))
                if new_mask not in updated or proposal < updated[new_mask]:
                    updated[new_mask] = proposal
        states = updated
    total, order = states[(1 << len(target)) - 1]
    differences = [
        abs(candidate[left][product] - target[order[left]][product])
        for left in range(len(candidate)) for product in range(len(PRODUCTS))
    ]
    return total, max(differences), sum(value <= 1e-10 for value in differences)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze the pre-solve empirical Renault case set.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repository_root.resolve()
    inventory_rows = {
        row["case_id"]: row
        for row in csv.DictReader(
            (root / "table_renault_case_inventory.csv").open(encoding="utf-8", newline="")
        )
    }
    with zipfile.ZipFile(args.archive) as archive:
        customers_by_case: dict[str, list[dict[str, str]]] = {}
        location_by_id: dict[str, tuple[float, float]] = {}
        for case in CASES:
            depots = read_csv(archive, f"{PROCESSED_PREFIX}/{case}/depots.csv")
            commodities = read_csv(archive, f"{PROCESSED_PREFIX}/{case}/commodities.csv")
            if len(depots) != EXPECTED_DEPOTS[case]:
                raise ValueError(f"depot identity count changed for {case}: {len(depots)}")
            commodity_ids = {row["commodity_code"] for row in commodities}
            if not set(PRODUCTS).issubset(commodity_ids):
                raise ValueError(f"frozen products are incomplete for {case}")
            rows = read_csv(archive, f"{PROCESSED_PREFIX}/{case}/customers.csv")
            customers_by_case[case] = rows
            for row in rows:
                location = (float(row["latitude"]), float(row["longitude"]))
                prior = location_by_id.setdefault(row["customer_code"], location)
                if prior != location:
                    raise ValueError(f"customer location changed: {row['customer_code']}")
        common_ids = set.intersection(
            *(set(row["customer_code"] for row in rows) for rows in customers_by_case.values())
        )
        common_locations = {value: location_by_id[value] for value in common_ids}
        medoid_ids, iterations = stable_common_medoids(common_locations)
        centers = [common_locations[value] for value in medoid_ids]
        assignments: dict[str, dict[str, int]] = {}
        audit_rows: list[dict[str, object]] = []
        legacy_checks: dict[str, dict[str, object]] = {}
        for case in CASES:
            case_assignments = {
                row["customer_code"]: nearest_region(
                    (float(row["latitude"]), float(row["longitude"])), centers
                )
                for row in customers_by_case[case]
            }
            assignments[case] = dict(sorted(case_assignments.items()))
            counts = {region: 0 for region in range(1, 13)}
            for region in case_assignments.values():
                counts[region] += 1
            for region, medoid_id in enumerate(medoid_ids, 1):
                audit_rows.append(
                    {
                        "case_id": case,
                        "customer_count": len(case_assignments),
                        "covered_customers": len(case_assignments),
                        "coverage_ratio": 1.0,
                        "common_reference_customers": len(common_ids),
                        "nearest_center_assignments": len(case_assignments) - len(common_ids),
                        "region_id": region,
                        "customers_in_region": counts[region],
                        "empty_region": counts[region] == 0,
                        "center_customer_id": medoid_id,
                        "center_latitude": centers[region - 1][0],
                        "center_longitude": centers[region - 1][1],
                    }
                )
            if case in {"210202", "210628"}:
                demand_rows = read_csv(archive, f"{PROCESSED_PREFIX}/{case}/demand_daily.csv")
                selected = [row for row in demand_rows if row["commodity_code"] in PRODUCTS]
                weekdays = sorted(
                    {
                        row["day"] for row in selected
                        if datetime.strptime(row["day"], "%d/%m/%Y").weekday() < 5
                    }
                )
                totals = {(region, product): 0.0 for region in range(1, 13) for product in PRODUCTS}
                for row in selected:
                    if row["day"] in weekdays:
                        totals[(case_assignments[row["customer_code"]], row["commodity_code"])] += float(row["demand"])
                candidate = [
                    [totals[(region, product)] / len(weekdays) for product in PRODUCTS]
                    for region in range(1, 13)
                ]
                target = json.loads((root / "data" / "formal_instances" / f"{case}.json").read_text())["base_demand"]
                l1, maximum, exact_cells = minimum_row_permutation_l1(candidate, target)
                legacy_checks[case] = {
                    "minimum_l1_difference_allowing_region_permutation": l1,
                    "maximum_cell_difference_under_best_permutation": maximum,
                    "exact_cells_under_best_permutation": exact_cells,
                    "total_cells": 96,
                    "compatible_with_existing_formal_instance": maximum <= 1e-10,
                }

        mapping_core = {
            "schema": "e1_empirical_region_mapping_v1",
            "rule": "12 deterministic haversine k-medoids from the 8-case common customer identity intersection; unweighted locations only; deterministic central-medoid plus farthest-first initialization; medoid update; centers ordered west-to-east",
            "selected_cases": list(CASES),
            "common_customer_identity_count": len(common_ids),
            "iterations": iterations,
            "centers": [
                {
                    "region_id": index,
                    "customer_id": customer_id,
                    "latitude": centers[index - 1][0],
                    "longitude": centers[index - 1][1],
                }
                for index, customer_id in enumerate(medoid_ids, 1)
            ],
            "assignments_by_case": assignments,
        }
        mapping_hash = sha256_bytes(canonical_bytes(mapping_core))
        mapping = {
            **mapping_core,
            "mapping_sha256": mapping_hash,
            "coverage_complete": True,
            "empty_region_count": sum(row["empty_region"] for row in audit_rows),
            "legacy_formal_compatibility": legacy_checks,
            "status": "BLOCK_E1_EMPIRICAL_REGION_MAPPING",
            "block_reason": "The case-invariant location-only mapping is complete but changes the frozen 210202 and 210628 formal demand arrays, so their existing E1 results cannot be reused under the common-mapping contract.",
        }
        (root / "artifacts" / "e1_empirical_region_mapping_v1.json").write_text(
            json.dumps(mapping, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
        )
        for row in audit_rows:
            row["mapping_sha256"] = mapping_hash
        write_csv(root / "table_e1_empirical_region_mapping_audit.csv", audit_rows)

        selection = {
            "210202": "existing formal anchor; high demand density",
            "210628": "existing formal anchor; later date and lower demand density",
            "210129": "highest audited demand density among all raw cases",
            "210310": "minimum audited customer count",
            "210330": "maximum customer count, minimum demand density, and minimum depot count",
            "210323": "high-customer intermediate case with 13 depots",
            "210428": "18-depot high-dimensional case",
            "210611": "maximum demand-record count and 19 depots",
        }
        characteristic_rows = []
        freeze_cases = []
        for case in CASES:
            source = inventory_rows[case]
            row = {
                "case_id": case,
                "raw_source_identity": source["source_file_identity"],
                "raw_audit_crc32": source["processed_audit_crc32"],
                "customer_count": int(source["customer_count"]),
                "depot_count": int(source["depot_count"]),
                "product_count": int(source["product_count"]),
                "planning_days": int(source["planning_days"]),
                "demand_record_count": int(source["demand_record_count"]),
                "demand_pair_density": float(source["demand_pair_density"]),
                "selection_rationale": selection[case],
                "final_I": int(source["depot_count"]),
                "target_R": 12,
                "target_J": 8,
                "construction_status": "EXISTING_FORMAL_RESULT_PRESERVED" if case in {"210202", "210628"} else "BLOCKED_BEFORE_FORMAL_CONSTRUCTION",
            }
            characteristic_rows.append(row)
            freeze_cases.append(dict(row))
        write_csv(root / "table_e1_empirical_case_characteristics.csv", characteristic_rows)
        freeze = {
            "schema": "E1_EMPIRICAL_CASES_V1",
            "status": "E1_EMPIRICAL_DATASET_PARTIAL",
            "selected_case_order": list(CASES),
            "selection_basis": "pre-solve empirical stratification from the Renault raw archive audit; no optimization result used",
            "cases": freeze_cases,
            "products": list(PRODUCTS),
            "region_mapping_path": "artifacts/e1_empirical_region_mapping_v1.json",
            "region_mapping_sha256": mapping_hash,
            "blocker": mapping["block_reason"],
            "new_gamma2_e1_benchmark_solves": 0,
            "baseline_preparation_solves": 0,
            "synthetic_execution": 0,
            "e2_e7_authorization": False,
        }
        freeze_path = root / "experiments" / "configs" / "formal" / "e1_empirical_case_freeze.json"
        freeze_path.write_text(json.dumps(freeze, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    baseline = json.loads((root / "artifacts" / "nominal_baseline_summary.json").read_text())
    x0_rows, bref_rows, identity_rows = [], [], []
    for case in CASES:
        existing = case in {"210202", "210628"}
        item = baseline["cases"].get(case, {})
        x0_path = root / "artifacts" / f"nominal_baseline_{case}.csv"
        instance_path = root / "data" / "formal_instances" / f"{case}.json"
        x0_rows.append({
            "case_id": case,
            "status": "FROZEN_EXISTING" if existing else "NOT_RUN_BLOCKED_BY_REGION_MAPPING",
            "total_x0": item.get("total_inventory"),
            "positive_x0_pairs": item.get("positive_x0_pair_count"),
            "active_depots": item.get("active_depot_count"),
            "nominal_objective": item.get("candidate_a", {}).get("objective"),
            "first_stage_spending": item.get("candidate_a", {}).get("first_stage_spending"),
            "nominal_recourse": item.get("candidate_a", {}).get("nominal_recourse"),
            "structurally_stable": item.get("degeneracy", {}).get("baseline_structurally_stable"),
            "capacity_compatible": item.get("feasibility", {}).get("capacity_compatible"),
            "ub_compatible": item.get("feasibility", {}).get("ub_compatible"),
            "x0_sha256": sha256_file(x0_path) if x0_path.exists() else None,
        })
        bref_rows.append({
            "case_id": case,
            "status": "FROZEN_EXISTING" if existing else "NOT_RUN_BLOCKED_BY_REGION_MAPPING",
            "B_ref": item.get("candidate_a", {}).get("first_stage_spending"),
            "definition": "first-stage expenditure of the frozen nominal incumbent",
        })
        identity_rows.append({
            "case_id": case,
            "status": "FROZEN_EXISTING" if existing else "NOT_GENERATED_BLOCKED_BY_REGION_MAPPING",
            "I": len(json.loads(instance_path.read_text())["depot_ids"]) if instance_path.exists() else None,
            "R": len(json.loads(instance_path.read_text())["region_ids"]) if instance_path.exists() else None,
            "J": len(json.loads(instance_path.read_text())["product_ids"]) if instance_path.exists() else None,
            "instance_sha256": sha256_file(instance_path) if instance_path.exists() else None,
            "x0_sha256": sha256_file(x0_path) if x0_path.exists() else None,
            "mapping_sha256": mapping_hash if existing else None,
            "mapping_compatible_with_instance": False if existing else None,
        })
    write_csv(root / "table_e1_empirical_x0_summary.csv", x0_rows)
    write_csv(root / "table_e1_empirical_bref_summary.csv", bref_rows)
    write_csv(root / "table_e1_empirical_instance_identity.csv", identity_rows)
    print(json.dumps({"status": freeze["status"], "mapping_sha256": mapping_hash}, indent=2))


if __name__ == "__main__":
    main()
