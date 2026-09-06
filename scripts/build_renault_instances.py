from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from robust_inventory_reconfiguration.instance import InventoryInstance, save_instance


CASES = ("210202", "210628")


def convert_case(source_root: Path, output_root: Path, case: str) -> Path:
    instance_path = source_root / "instances" / f"{case}_B1.00.json"
    metadata_path = source_root / "instances" / f"{case}_index_metadata.json"
    source = json.loads(instance_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    instance = InventoryInstance(
        name=f"renault_{case}",
        depot_ids=[str(value) for value in metadata["depot_order"]],
        region_ids=[str(value) for value in metadata["region_order"]],
        product_ids=[str(value) for value in metadata["product_order"]],
        base_demand=source["base_demand"],
        demand_deviation=source["demand_deviation"],
        transport_cost=source["transport_cost"],
        shortage_penalty=source["shortage_penalty"],
        service_level=source["service_level"],
        service_penalty=source["service_penalty"],
        capacity=source["capacity"],
        inventory_upper_bound=source["inventory_ub"],
        fixed_depot_cost=source["fixed_cost"],
        inventory_cost=source["inventory_cost"],
        product_volume=source["volume"],
        initial_inventory=None,
        reconfiguration_cost_multiplier=None,
        provenance={
            "legacy_repository": "Hoshino12172003/robust-inventory-benders",
            "legacy_source_files": [
                f"real_data_studies/renault_formal_instances_v6/instances/{instance_path.name}",
                f"real_data_studies/renault_formal_instances_v6/instances/{metadata_path.name}",
            ],
            "legacy_instance_sha256": hashlib.sha256(instance_path.read_bytes()).hexdigest(),
            "legacy_metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
            "source_case": case,
            "data_positioning": metadata["data_positioning"],
            "parameter_classes": metadata["parameter_classes"],
            "selection": "15 canonical depots, 12 regions, 8 canonical products",
            "budget_removed": "New B_ref has not been defined.",
            "initial_inventory_status": "Source field unavailable; identity audit must stop.",
            "parameter_changes": "none",
        },
    )
    output_path = output_root / f"{case}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_instance(instance, output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Selectively convert Renault Step 3 instances.")
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    for case in CASES:
        print(convert_case(args.source_root, args.output_root, case))


if __name__ == "__main__":
    main()
