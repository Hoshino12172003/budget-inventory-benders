from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "artifacts/e3_table_budget_sensitivity_case_level.csv"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts"
BETA = (0.8, 0.9, 1.0, 1.1, 1.2)
COLOR_MEAN = "#1f4e79"
COLOR_MEDIAN = "#c55a11"
COLOR_CASE = "#9aa0a6"


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def values_by_case(rows: list[dict], metric: str) -> dict[str, list[float]]:
    cases = sorted({row["case"] for row in rows})
    return {
        case: [float(next(row[metric] for row in rows if row["case"] == case and float(row["beta"]) == beta)) for beta in BETA]
        for case in cases
    }


def save_figure(fig, output_dir: Path, stem: str) -> None:
    fig.savefig(output_dir / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def line_figure(rows: list[dict], metric: str, ylabel: str, stem: str, output_dir: Path, *, median: bool = False, percent: bool = False, horizontal_reference: float | None = None) -> None:
    trajectories = values_by_case(rows, metric)
    fig, axis = plt.subplots(figsize=(6.4, 4.2), constrained_layout=True)
    for values in trajectories.values():
        plotted = [100.0 * value for value in values] if percent else values
        axis.plot(BETA, plotted, color=COLOR_CASE, linewidth=0.9, alpha=0.65)
    means = [statistics.mean(values[index] for values in trajectories.values()) for index in range(len(BETA))]
    if percent:
        means = [100.0 * value for value in means]
    axis.plot(BETA, means, color=COLOR_MEAN, marker="o", linewidth=2.4, label="Mean")
    if median:
        medians = [statistics.median(values[index] for values in trajectories.values()) for index in range(len(BETA))]
        if percent:
            medians = [100.0 * value for value in medians]
        axis.plot(BETA, medians, color=COLOR_MEDIAN, marker="s", linewidth=1.8, linestyle="--", label="Median")
    axis.axvline(1.0, color="#555555", linewidth=0.8, linestyle=":", label="B100 reference")
    if horizontal_reference is not None:
        axis.axhline(horizontal_reference, color="#777777", linewidth=0.8, linestyle="--")
    axis.set_xlabel(r"Budget multiplier, $\beta = B/B_{ref}$")
    axis.set_ylabel(ylabel)
    axis.set_xticks(BETA)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, fontsize=8)
    save_figure(fig, output_dir, stem)


def generate_figures(rows: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    line_figure(rows, "normalized_objective", "Normalized robust objective", "fig_e3_normalized_objective_vs_budget", output_dir, horizontal_reference=1.0)
    line_figure(rows, "RI", "Reconfiguration intensity (RI)", "fig_e3_ri_vs_budget", output_dir, median=True)
    line_figure(rows, "budget_utilization", "Budget utilization (%)", "fig_e3_budget_utilization_vs_budget", output_dir, median=True, percent=True, horizontal_reference=100.0)
    line_figure(rows, "normalized_robust_recourse", "Robust recourse relative to B100", "fig_e3_recourse_vs_budget", output_dir, horizontal_reference=1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    generate_figures(load_rows(args.input), args.output_dir)
    print("wrote 4 E3 figures in PNG and PDF")


if __name__ == "__main__":
    main()
