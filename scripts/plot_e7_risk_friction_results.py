from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "artifacts/e7_table_risk_friction_aggregate.csv"
OUTPUT = ROOT / "artifacts"
GAMMAS = (0, 2, 4)
LEVELS = ((0.0025, "Low, lambda=0.0025", "#4d9221"), (0.05, "Baseline, lambda=0.05", "#2166ac"), (0.2, "High, lambda=0.20", "#b2182b"))


def finish(fig, stem: str) -> None:
    fig.savefig(OUTPUT / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(OUTPUT / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot(rows, metric: str, ylabel: str, stem: str, percent: bool = False) -> None:
    fig, axis = plt.subplots(figsize=(6.5, 4.2), constrained_layout=True)
    for value, label, color in LEVELS:
        cell = sorted((row for row in rows if float(row["lambda_R"]) == value), key=lambda row: int(row["Gamma"]))
        axis.plot(GAMMAS, [float(row[metric]) for row in cell], marker="o", linewidth=2, label=label, color=color)
    axis.set(xlabel="Demand-risk budget, Gamma", ylabel=ylabel)
    axis.set_xticks(GAMMAS)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)
    if percent:
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.legend(frameon=False, fontsize=8)
    finish(fig, stem)


def main() -> None:
    with TABLE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    plot(rows, "mean_RI", "Mean reconfiguration intensity", "fig_e7_ri_interaction", True)
    plot(rows, "mean_normalized_objective", "Mean normalized objective", "fig_e7_normalized_objective_interaction")
    plot(rows, "mean_RS", "Mean reconfiguration spending share", "fig_e7_rs_interaction", True)
    plot(rows, "mean_top_adjustment_share", "Mean top-adjustment share", "fig_e7_adjustment_concentration_interaction", True)


if __name__ == "__main__":
    main()
