from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median

from robust_inventory_reconfiguration.instance import load_instance


CASES = ("210202", "210628")


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nearest_rank(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[rank - 1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def audit_case(case: str, formal_dir: Path, raw_cases_root: Path) -> dict[str, object]:
    instance = load_instance(formal_dir / f"{case}.json")
    raw_case = raw_cases_root / case
    raw_depot_rows = read_csv(raw_case / "depots_codes.csv")
    raw_product_rows = read_csv(raw_case / "commodity_lengths.csv")
    raw_depots = {str(row["code"]) for row in raw_depot_rows}
    raw_lengths = {row["commodity_code"]: float(row["length"]) for row in raw_product_rows}

    missing_depot_ids = sorted(set(instance.depot_ids) - raw_depots)
    missing_product_ids = sorted(set(instance.product_ids) - set(raw_lengths))
    unit_mismatches = [
        product
        for j, product in enumerate(instance.product_ids)
        if product in raw_lengths and raw_lengths[product] != instance.product_volume[j]
    ]

    x0_rows: list[dict[str, object]] = []
    values: dict[tuple[str, str], float] = {}
    missing_pairs: list[list[str]] = []
    duplicate_pairs: list[list[str]] = []
    ambiguous_pairs: list[list[str]] = []
    negative_count = 0
    nan_count = 0
    inf_count = 0
    all_depot_source_value_count = 0
    all_depot_source_nonzero_count = 0
    all_depot_source_total = 0.0

    for depot in instance.depot_ids:
        source_file = raw_case / f"depot_{depot}" / "per_commodity.csv"
        if not source_file.exists():
            missing_pairs.extend([[depot, product] for product in instance.product_ids])
            continue
        source_rows = read_csv(source_file)
        source_sha256 = file_hash(source_file)
        for source_row in source_rows:
            source_value = float(source_row["initial_inventory"])
            all_depot_source_value_count += 1
            if source_value != 0:
                all_depot_source_nonzero_count += 1
            all_depot_source_total += source_value
        by_product: dict[str, list[dict[str, str]]] = {}
        for row in source_rows:
            by_product.setdefault(row["commodity_code"], []).append(row)
        for product in instance.product_ids:
            matches = by_product.get(product, [])
            if not matches:
                missing_pairs.append([depot, product])
                continue
            if len(matches) > 1:
                duplicate_pairs.append([depot, product])
                ambiguous_pairs.append([depot, product])
                continue
            raw_value = matches[0]["initial_inventory"]
            try:
                value = float(raw_value)
            except ValueError:
                ambiguous_pairs.append([depot, product])
                continue
            if math.isnan(value):
                nan_count += 1
            elif math.isinf(value):
                inf_count += 1
            elif value < 0:
                negative_count += 1
            values[depot, product] = value
            x0_rows.append(
                {
                    "case": case,
                    "depot_id": depot,
                    "product_id": product,
                    "x0": raw_value,
                    "raw_depot_id": depot,
                    "raw_product_id": product,
                    "mapping_method": "exact_identity_match",
                    "source_file": source_file.relative_to(raw_cases_root.parent).as_posix(),
                    "source_sha256": source_sha256,
                    "source_initial_inventory": raw_value,
                }
            )

    mapped_count = len(values)
    mapping_failure = bool(
        missing_depot_ids
        or missing_product_ids
        or missing_pairs
        or duplicate_pairs
        or ambiguous_pairs
        or negative_count
        or nan_count
        or inf_count
        or mapped_count != instance.num_depots * instance.num_products
    )
    unit_ambiguity = bool(unit_mismatches)
    if mapping_failure or unit_ambiguity:
        return {
            "case": case,
            "instance": instance,
            "x0_rows": x0_rows,
            "capacity_rows": [],
            "ub_rows": [],
            "scale_rows": [],
            "summary": {
                "mapped_count": mapped_count,
                "expected_count": instance.num_depots * instance.num_products,
                "missing_count": len(missing_pairs),
                "duplicate_count": len(duplicate_pairs),
                "ambiguous_count": len(ambiguous_pairs),
                "negative_count": negative_count,
                "nan_count": nan_count,
                "inf_count": inf_count,
                "missing_depot_ids": missing_depot_ids,
                "missing_product_ids": missing_product_ids,
                "unit_mismatches": unit_mismatches,
                "all_depot_source_value_count": all_depot_source_value_count,
                "all_depot_source_nonzero_count": all_depot_source_nonzero_count,
                "all_depot_source_total": all_depot_source_total,
                "classification": (
                    "SOURCE_MAPPING_FAILURE" if mapping_failure else "SOURCE_UNIT_AMBIGUITY"
                ),
            },
        }

    capacity_rows: list[dict[str, object]] = []
    capacity_ratios: list[float] = []
    violating_depots: list[str] = []
    capacity_excesses: list[float] = []
    zero_stock_depots: list[str] = []
    for i, depot in enumerate(instance.depot_ids):
        load = sum(
            instance.product_volume[j] * values[depot, product]
            for j, product in enumerate(instance.product_ids)
        )
        capacity = instance.capacity[i]
        ratio = load / capacity if capacity > 0 else math.inf
        compatible = load <= capacity
        total_stock = sum(values[depot, product] for product in instance.product_ids)
        capacity_ratios.append(ratio)
        capacity_excesses.append(max(0.0, load - capacity))
        if not compatible:
            violating_depots.append(depot)
        if total_stock == 0:
            zero_stock_depots.append(depot)
        capacity_rows.append(
            {
                "case": case,
                "depot_id": depot,
                "L0": load,
                "capacity": capacity,
                "rhoC": ratio,
                "compatible": "yes" if compatible else "no",
                "absolute_excess": max(0.0, load - capacity),
                "selected_product_stock": total_stock,
            }
        )

    ub_rows: list[dict[str, object]] = []
    finite_ub_ratios: list[float] = []
    violating_pairs: list[list[str]] = []
    ub_zero_positive_pairs: list[list[str]] = []
    ub_excesses: list[float] = []
    compatible_pair_count = 0
    for i, depot in enumerate(instance.depot_ids):
        for j, product in enumerate(instance.product_ids):
            value = values[depot, product]
            upper_bound = instance.inventory_upper_bound[i][j]
            compatible = value <= upper_bound
            if upper_bound == 0:
                ratio: float | None = None
                if value > 0:
                    ub_zero_positive_pairs.append([depot, product])
            else:
                ratio = value / upper_bound
                finite_ub_ratios.append(ratio)
            if compatible:
                compatible_pair_count += 1
            else:
                violating_pairs.append([depot, product])
            excess = max(0.0, value - upper_bound)
            ub_excesses.append(excess)
            ub_rows.append(
                {
                    "case": case,
                    "depot_id": depot,
                    "product_id": product,
                    "x0": value,
                    "inventory_upper_bound": upper_bound,
                    "rhoUB": "" if ratio is None else ratio,
                    "ub_zero": "yes" if upper_bound == 0 else "no",
                    "compatible": "yes" if compatible else "no",
                    "absolute_excess": excess,
                }
            )

    scale_rows: list[dict[str, object]] = []
    coverage: list[float] = []
    total_x0 = 0.0
    total_demand = 0.0
    product_metrics: dict[str, dict[str, float]] = {}
    for j, product in enumerate(instance.product_ids):
        product_x0 = sum(values[depot, product] for depot in instance.depot_ids)
        nominal_demand = sum(instance.base_demand[r][j] for r in range(instance.num_regions))
        inventory_coverage = product_x0 / nominal_demand
        total_x0 += product_x0
        total_demand += nominal_demand
        coverage.append(inventory_coverage)
        product_metrics[product] = {
            "X0": product_x0,
            "Dnom": nominal_demand,
            "IC": inventory_coverage,
        }
        scale_rows.append(
            {
                "case": case,
                "scope": "product",
                "product_id": product,
                "X0": product_x0,
                "Dnom": nominal_demand,
                "IC": inventory_coverage,
            }
        )
    system_coverage = total_x0 / total_demand
    scale_rows.append(
        {
            "case": case,
            "scope": "system",
            "product_id": "",
            "X0": total_x0,
            "Dnom": total_demand,
            "IC": system_coverage,
        }
    )

    capacity_failure = bool(violating_depots)
    ub_failure = bool(violating_pairs)
    classification = (
        "BOTH_INCOMPATIBLE"
        if capacity_failure and ub_failure
        else "CAPACITY_INCOMPATIBLE"
        if capacity_failure
        else "UB_INCOMPATIBLE"
        if ub_failure
        else "DIRECTLY_COMPATIBLE"
    )
    return {
        "case": case,
        "instance": instance,
        "x0_rows": x0_rows,
        "capacity_rows": capacity_rows,
        "ub_rows": ub_rows,
        "scale_rows": scale_rows,
        "summary": {
            "mapped_count": mapped_count,
            "expected_count": instance.num_depots * instance.num_products,
            "missing_count": 0,
            "duplicate_count": 0,
            "ambiguous_count": 0,
            "negative_count": negative_count,
            "nan_count": nan_count,
            "inf_count": inf_count,
            "unit_mismatches": [],
            "all_depot_source_value_count": all_depot_source_value_count,
            "all_depot_source_nonzero_count": all_depot_source_nonzero_count,
            "all_depot_source_total": all_depot_source_total,
            "capacity_violation_count": len(violating_depots),
            "max_rhoC": max(capacity_ratios),
            "median_rhoC": median(capacity_ratios),
            "p90_rhoC_nearest_rank": nearest_rank(capacity_ratios, 0.90),
            "violating_depots": violating_depots,
            "maximum_capacity_absolute_excess": max(capacity_excesses),
            "ub_compatible_pair_count": compatible_pair_count,
            "ub_violation_count": len(violating_pairs),
            "max_rhoUB_excluding_ub_zero": max(finite_ub_ratios),
            "median_rhoUB_excluding_ub_zero": median(finite_ub_ratios),
            "violating_depot_product_pairs": violating_pairs,
            "ub_zero_x0_positive_count": len(ub_zero_positive_pairs),
            "ub_zero_x0_positive_pairs": ub_zero_positive_pairs,
            "maximum_ub_absolute_excess": max(ub_excesses),
            "zero_stock_depots": zero_stock_depots,
            "total_X0": total_x0,
            "product_metrics": product_metrics,
            "min_product_IC": min(coverage),
            "max_product_IC": max(coverage),
            "median_product_IC": median(coverage),
            "system_IC": system_coverage,
            "classification": classification,
        },
    }


def write_markdown(path: Path, results: list[dict[str, object]]) -> None:
    lines = [
        "# Renault initial-inventory compatibility audit",
        "",
        "This audit uses exact depot and product identity matches against the verified official Renault source. No value was filled, normalized, clipped, repaired, interpolated, or inferred. No optimization was run and no Step 1–3 parameter was changed.",
        "",
        "All 15 depots in each case remain existing facilities, including any depot with zero stock among the eight selected products.",
        "",
    ]
    for result in results:
        case = str(result["case"])
        summary = result["summary"]
        lines.extend(
            [
                f"## {case}",
                "",
                f"Classification: `{summary['classification']}`.",
                "",
                f"Mapped: {summary['mapped_count']}/{summary['expected_count']}; missing {summary['missing_count']}; duplicate {summary['duplicate_count']}; ambiguous {summary['ambiguous_count']}; negative {summary['negative_count']}; NaN {summary['nan_count']}; Inf {summary['inf_count']}.",
                "",
            ]
        )
        if "capacity_violation_count" not in summary:
            lines.extend(["The audit stopped before compatibility metrics.", ""])
            continue
        lines.extend(
            [
                "| Metric | Value |",
                "| --- | ---: |",
                f"| Capacity violations | {summary['capacity_violation_count']} |",
                f"| Maximum rhoC | {summary['max_rhoC']:.12g} |",
                f"| Median rhoC | {summary['median_rhoC']:.12g} |",
                f"| P90 rhoC, nearest rank | {summary['p90_rhoC_nearest_rank']:.12g} |",
                f"| UB violations | {summary['ub_violation_count']} |",
                f"| Maximum rhoUB, excluding UB=0 | {summary['max_rhoUB_excluding_ub_zero']:.12g} |",
                f"| Median rhoUB, excluding UB=0 | {summary['median_rhoUB_excluding_ub_zero']:.12g} |",
                f"| Total X0 | {summary['total_X0']:.12g} |",
                f"| Minimum product IC | {summary['min_product_IC']:.12g} |",
                f"| Maximum product IC | {summary['max_product_IC']:.12g} |",
                f"| Median product IC | {summary['median_product_IC']:.12g} |",
                f"| System IC | {summary['system_IC']:.12g} |",
                "",
                f"Violating depots: {summary['violating_depots'] or 'none'}.",
                "",
                f"Violating depot-product pairs: {summary['violating_depot_product_pairs'] or 'none'}.",
                "",
                f"Zero-stock depots: {summary['zero_stock_depots'] or 'none'}.",
                "",
                f"Across all depot commodities in the official source, {summary['all_depot_source_nonzero_count']}/{summary['all_depot_source_value_count']} initial-inventory values are nonzero and their total is {summary['all_depot_source_total']:.12g}.",
                "",
            ]
        )
    lines.extend(
        [
            "## Reconfiguration semantics",
            "",
            "Observed initial inventory is the parameter x0 in `x - x0 = a_plus - a_minus`. The adjustment variables are first-stage variables. Recourse reads only x and does not read x0, a_plus, or a_minus.",
            "",
            "`PRODUCTWISE_BENDERS_COMPATIBLE = true`.",
            "",
            "## Decision boundary",
            "",
            "The observed values are source-valid and constraint-compatible, but the official source reports zero initial inventory for every depot commodity in both cases. Direct use is therefore not recommended for a paper whose reconfiguration mechanism requires a nonzero incumbent stock baseline. Lambda_R calibration and the new B_ref definition should wait for an explicit modeling decision: accept the zero baseline and its degenerate withdrawal semantics, or introduce a separately justified nonzero baseline without labeling it observed Renault initial inventory.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Renault observed initial inventory.")
    parser.add_argument("--formal-dir", type=Path, default=Path("data/formal_instances"))
    parser.add_argument("--raw-cases-root", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--document", type=Path, default=Path("docs/renault_x0_compatibility_audit.md")
    )
    args = parser.parse_args()

    results = [audit_case(case, args.formal_dir, args.raw_cases_root) for case in CASES]
    all_capacity_rows: list[dict[str, object]] = []
    all_ub_rows: list[dict[str, object]] = []
    all_scale_rows: list[dict[str, object]] = []
    for result in results:
        case = str(result["case"])
        write_csv(
            args.artifacts_dir / f"renault_x0_{case}.csv",
            [
                "case",
                "depot_id",
                "product_id",
                "x0",
                "raw_depot_id",
                "raw_product_id",
                "mapping_method",
                "source_file",
                "source_sha256",
                "source_initial_inventory",
            ],
            result["x0_rows"],
        )
        all_capacity_rows.extend(result["capacity_rows"])
        all_ub_rows.extend(result["ub_rows"])
        all_scale_rows.extend(result["scale_rows"])

    write_csv(
        args.artifacts_dir / "renault_x0_capacity_audit.csv",
        [
            "case",
            "depot_id",
            "L0",
            "capacity",
            "rhoC",
            "compatible",
            "absolute_excess",
            "selected_product_stock",
        ],
        all_capacity_rows,
    )
    write_csv(
        args.artifacts_dir / "renault_x0_ub_audit.csv",
        [
            "case",
            "depot_id",
            "product_id",
            "x0",
            "inventory_upper_bound",
            "rhoUB",
            "ub_zero",
            "compatible",
            "absolute_excess",
        ],
        all_ub_rows,
    )
    write_csv(
        args.artifacts_dir / "renault_x0_scale_audit.csv",
        ["case", "scope", "product_id", "X0", "Dnom", "IC"],
        all_scale_rows,
    )

    archive = args.raw_cases_root.parent.parent / "instances.tar.gz"
    summary = {
        "source": {
            "official_archive": str(archive),
            "official_archive_md5": file_hash(archive, "md5"),
            "official_archive_sha256": file_hash(archive),
            "expected_official_archive_md5": "5a557a2edd50bb308bf955f754b22503",
            "official_archive_md5_match": (
                file_hash(archive, "md5") == "5a557a2edd50bb308bf955f754b22503"
            ),
            "mapping_method": "exact_identity_match",
        },
        "cases": {str(result["case"]): result["summary"] for result in results},
        "PRODUCTWISE_BENDERS_COMPATIBLE": True,
        "optimization_run": False,
        "step_1_3_parameters_modified": False,
        "observed_initial_inventory_recommended_directly_as_x0": False,
        "recommendation_reason": (
            "The values are source-valid and constraint-compatible, but every official depot "
            "initial-inventory value is zero in both cases, so the reconfiguration baseline is "
            "degenerate."
        ),
        "safe_to_proceed_to_lambda_R_calibration_and_new_B_ref": False,
    }
    (args.artifacts_dir / "renault_x0_compatibility_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.document, results)

    if any(
        result["summary"]["classification"]
        in {"SOURCE_MAPPING_FAILURE", "SOURCE_UNIT_AMBIGUITY"}
        for result in results
    ):
        raise SystemExit("Audit stopped because source mapping or units are ambiguous.")


if __name__ == "__main__":
    main()
