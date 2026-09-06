from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from robust_inventory_reconfiguration.instance import load_instance
from robust_inventory_reconfiguration.x0_audit import SourceInventoryRow, audit_initial_inventory


def load_source(path: Path) -> list[SourceInventoryRow] | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            SourceInventoryRow(
                depot_id=row["depot_id"],
                product_id=row["product_id"],
                initial_inventory=float(row["initial_inventory"]),
            )
            for row in csv.DictReader(handle)
        ]


def write_mapping(path: Path, instance, rows: list[SourceInventoryRow] | None) -> None:
    values = None if rows is None else {(row.depot_id, row.product_id): row.initial_inventory for row in rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["depot_id", "product_id", "initial_inventory", "mapping_status"],
        )
        writer.writeheader()
        for depot in instance.depot_ids:
            for product in instance.product_ids:
                value = None if values is None else values.get((depot, product))
                writer.writerow(
                    {
                        "depot_id": depot,
                        "product_id": product,
                        "initial_inventory": "" if value is None else value,
                        "mapping_status": "MISSING_SOURCE_FIELD" if value is None else "MAPPED_BY_IDENTITY",
                    }
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Renault observed initial inventory by identity.")
    parser.add_argument("--instances", type=Path, default=Path("data/formal_instances"))
    parser.add_argument("--source", type=Path, default=Path("data/raw/renault_initial_inventory"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/x0_audit"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summary = {}
    for case in ("210202", "210628"):
        instance = load_instance(args.instances / f"{case}.json")
        rows = load_source(args.source / f"{case}.csv")
        result = audit_initial_inventory(instance, rows)
        write_mapping(args.output / f"{case}_x0_mapping.csv", instance, rows)
        (args.output / f"{case}_audit.json").write_text(
            json.dumps(result.to_dict(), indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        summary[case] = result.to_dict()
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
