from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "artifacts/e5_table_friction_sensitivity_case_level.csv"
OUTPUT = ROOT / "artifacts"
LAMBDAS = (0.0, 0.0025, 0.01, 0.05, 0.2)
POSITIONS = tuple(range(len(LAMBDAS)))
COLORS = ("#1f4e79", "#c55a11", "#548235", "#7030a0", "#a61c00", "#008c95", "#7f6000", "#5b6573")


def load_rows(path: Path = INPUT) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def trajectories(rows: list[dict[str, str]], metric: str) -> dict[str, list[float]]:
    cases = sorted({row["case"] for row in rows})
    return {
        case: [
            float(next(row[metric] for row in rows if row["case"] == case and float(row["lambda_R"]) == value))
            for value in LAMBDAS
        ]
        for case in cases
    }


def finish(fig, stem: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(output / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style_axis(axis, *, percent: bool = False) -> None:
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)
    axis.spines[["top", "right"]].set_visible(False)
    axis.set_xticks(POSITIONS, ("0", "0.0025", "0.01", "0.05", "0.20"))
    if percent:
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))


def aggregate_figure(rows: list[dict[str, str]], metric: str, ylabel: str, stem: str) -> None:
    values = trajectories(rows, metric)
    fig, axis = plt.subplots(figsize=(6.5, 4.2), constrained_layout=True)
    for trajectory in values.values():
        axis.plot(POSITIONS, trajectory, color="#a7acb1", linewidth=0.9, alpha=0.65)
    mean = [statistics.mean(trajectory[index] for trajectory in values.values()) for index in range(len(LAMBDAS))]
    axis.plot(POSITIONS, mean, color="#1f4e79", marker="o", linewidth=2.4, label="Mean")
    axis.axhline(1.0, color="#777777", linewidth=0.8, linestyle="--")
    axis.set(xlabel=r"Reconfiguration friction, $\lambda_R$", ylabel=ylabel)
    style_axis(axis)
    axis.legend(frameon=False, fontsize=8)
    finish(fig, stem, OUTPUT)


def individual_figure(rows: list[dict[str, str]], metric: str, ylabel: str, stem: str, *, percent: bool) -> None:
    values = trajectories(rows, metric)
    fig, axis = plt.subplots(figsize=(7.3, 5.2), constrained_layout=True)
    for (case, trajectory), color in zip(values.items(), COLORS):
        axis.plot(POSITIONS, trajectory, marker="o", markersize=3.8, linewidth=1.5, color=color, label=case)
    mean = [statistics.mean(trajectory[index] for trajectory in values.values()) for index in range(len(LAMBDAS))]
    axis.plot(POSITIONS, mean, color="#111111", linewidth=2.4, linestyle="--", marker="s", label="Mean")
    axis.set(xlabel=r"Reconfiguration friction, $\lambda_R$", ylabel=ylabel)
    style_axis(axis, percent=percent)
    axis.legend(frameon=False, fontsize=7.5, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.01))
    finish(fig, stem, OUTPUT)


def generate_figures(rows: list[dict[str, str]]) -> None:
    aggregate_figure(
        rows,
        "normalized_objective_vs_L0500",
        r"Objective relative to $\lambda_R=0.05$",
        "fig_e5_normalized_objective_vs_lambda",
    )
    individual_figure(rows, "RI", "Reconfiguration intensity (RI)", "fig_e5_ri_vs_lambda", percent=True)
    individual_figure(rows, "RS", "Reconfiguration cost as a share of budget", "fig_e5_rs_vs_lambda", percent=True)
    aggregate_figure(
        rows,
        "normalized_robust_recourse_vs_L0500",
        r"Robust recourse relative to $\lambda_R=0.05$",
        "fig_e5_recourse_vs_lambda",
    )


if __name__ == "__main__":
    generate_figures(load_rows())
    print("wrote 4 E5 figures in PNG and PDF")
