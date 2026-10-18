"""Plot only persisted, explicitly selected algorithm gap trajectories."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


REQUIRED = {"condition_id", "method", "iteration", "gap", "cumulative_time_seconds"}


def load_rows(path: Path, conditions: set[str]) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"trajectory file is missing fields: {sorted(missing)}")
        rows = [row for row in reader if row["condition_id"] in conditions]
    if not rows:
        raise ValueError("no persisted trajectory rows match --condition-id")
    for row in rows:
        row["iteration"] = int(row["iteration"])
        row["gap"] = float(row["gap"])
        row["cumulative_time_seconds"] = float(row["cumulative_time_seconds"])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory-csv", type=Path, required=True)
    parser.add_argument("--condition-id", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows(args.trajectory_csv, set(args.condition_id))

    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(6.4, 4.0))
    for condition in args.condition_id:
        selected = sorted(
            (row for row in rows if row["condition_id"] == condition),
            key=lambda row: row["cumulative_time_seconds"],
        )
        if selected:
            axis.plot(
                [row["cumulative_time_seconds"] for row in selected],
                [max(row["gap"], 1e-12) for row in selected],
                marker="o",
                linewidth=1.4,
                label=f"{selected[0]['method']} ({condition})",
            )
    axis.set_yscale("log")
    axis.set_xlabel("Cumulative algorithm time (s)")
    axis.set_ylabel("Relative optimality gap")
    axis.grid(True, which="both", color="#D9DDE2", linewidth=0.6, alpha=0.8)
    axis.legend(loc="best", fontsize=7)
    figure.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
