from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
LEVELS = ((0.0025, "Low, $\\lambda_R=0.0025$", "#4d9221"), (0.05, "Baseline, $\\lambda_R=0.05$", "#2166ac"), (0.2, "High, $\\lambda_R=0.20$", "#b2182b"))
GAMMAS = (0, 2, 4)


def read_csv(name: str) -> list[dict]:
    with (ARTIFACTS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def finish(fig, stem: str) -> None:
    fig.savefig(ARTIFACTS / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(ARTIFACTS / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style(axis, ylabel: str) -> None:
    axis.set(xlabel="Demand-risk budget, $\\Gamma$", ylabel=ylabel)
    axis.set_xticks(GAMMAS)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)


def ri_trajectories(case_rows: list[dict], aggregate: list[dict]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.6), sharey=True, constrained_layout=True)
    for axis, (value, label, color) in zip(axes, LEVELS):
        selected = [row for row in case_rows if float(row["lambda_R"]) == value]
        for case in sorted({row["case"] for row in selected}):
            rows = sorted((row for row in selected if row["case"] == case), key=lambda row: int(row["Gamma"]))
            axis.plot(GAMMAS, [float(row["RI"]) for row in rows], color="#a6a6a6", alpha=0.65, linewidth=0.9)
        mean = sorted((row for row in aggregate if float(row["lambda_R"]) == value), key=lambda row: int(row["Gamma"]))
        axis.plot(GAMMAS, [float(row["mean_RI"]) for row in mean], marker="o", color=color, linewidth=2.2, label="Case mean")
        style(axis, "Reconfiguration intensity" if axis is axes[0] else "")
        axis.set_title(label, fontsize=9)
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    finish(fig, "fig_e7_ri_interaction")


def aggregate_lines(aggregate: list[dict], metric: str, ylabel: str, stem: str, percent: bool = False) -> None:
    fig, axis = plt.subplots(figsize=(6.4, 4.0), constrained_layout=True)
    for value, label, color in LEVELS:
        rows = sorted((row for row in aggregate if float(row["lambda_R"]) == value), key=lambda row: int(row["Gamma"]))
        axis.plot(GAMMAS, [float(row[metric]) for row in rows], marker="o", linewidth=2, color=color, label=label)
    style(axis, ylabel)
    if percent:
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.legend(frameon=False, fontsize=8)
    finish(fig, stem)


def composition_plot(aggregate: list[dict]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.8), constrained_layout=True)
    for value, label, color in LEVELS:
        rows = sorted((row for row in aggregate if float(row["lambda_R"]) == value and row["mean_changed_pairs_conditional_on_material"]), key=lambda row: int(row["Gamma"]))
        x = [int(row["Gamma"]) for row in rows]
        axes[0].plot(x, [float(row["mean_changed_pairs_conditional_on_material"]) for row in rows], marker="o", color=color, label=label)
        axes[1].plot(x, [float(row["mean_top_adjustment_share_conditional_on_material"]) for row in rows], marker="o", color=color, label=label)
    style(axes[0], "Changed pairs | material")
    style(axes[1], "Top adjustment share | material")
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[0].legend(frameon=False, fontsize=8)
    finish(fig, "fig_e7_adjustment_concentration_interaction")


def main() -> None:
    case_rows = read_csv("e7_table_risk_friction_case_level.csv")
    aggregate = read_csv("e7_table_risk_friction_aggregate.csv")
    ri_trajectories(case_rows, aggregate)
    aggregate_lines(aggregate, "mean_normalized_objective", "Mean normalized objective", "fig_e7_normalized_objective_interaction")
    aggregate_lines(aggregate, "mean_RS", "Mean reconfiguration spending share", "fig_e7_rs_interaction", True)
    composition_plot(aggregate)


if __name__ == "__main__":
    main()
