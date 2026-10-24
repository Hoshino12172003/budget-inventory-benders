from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "artifacts/e4_table_gamma_sensitivity_case_level.csv"
OUTPUT = ROOT / "artifacts"
GAMMAS = (0, 1, 2, 3, 4)
COLORS = ("#1f4e79", "#c55a11", "#548235", "#7030a0", "#a61c00", "#008c95", "#7f6000", "#5b6573")


def load_rows(path: Path = INPUT) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def values_by_case(rows: list[dict[str, str]], metric: str) -> dict[str, list[float]]:
    return {
        case: [float(next(row[metric] for row in rows if row["case"] == case and int(row["Gamma"]) == gamma)) for gamma in GAMMAS]
        for case in sorted({row["case"] for row in rows})
    }


def finish(fig, stem: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(output / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def aggregate_trajectory(rows: list[dict[str, str]], metric: str, ylabel: str, stem: str, output: Path) -> None:
    trajectories = values_by_case(rows, metric)
    fig, axis = plt.subplots(figsize=(6.4, 4.2), constrained_layout=True)
    for values in trajectories.values():
        axis.plot(GAMMAS, values, color="#a7acb1", linewidth=0.9, alpha=0.65)
    mean = [statistics.mean(values[index] for values in trajectories.values()) for index in range(len(GAMMAS))]
    axis.plot(GAMMAS, mean, color="#1f4e79", marker="o", linewidth=2.4, label="Mean")
    axis.axhline(1.0, color="#777777", linewidth=0.8, linestyle="--")
    axis.set(xlabel=r"Uncertainty budget, $\Gamma$", ylabel=ylabel, xticks=GAMMAS)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, fontsize=8)
    finish(fig, stem, output)


def ri_figure(rows: list[dict[str, str]], output: Path) -> None:
    trajectories = values_by_case(rows, "RI")
    fig, axis = plt.subplots(figsize=(7.2, 4.6), constrained_layout=True)
    for (case, values), color in zip(trajectories.items(), COLORS):
        axis.plot(GAMMAS, values, marker="o", markersize=3.8, linewidth=1.5, color=color, label=case)
    mean = [statistics.mean(values[index] for values in trajectories.values()) for index in range(len(GAMMAS))]
    axis.plot(GAMMAS, mean, color="#111111", linewidth=2.5, linestyle="--", marker="s", label="Mean")
    axis.set(xlabel=r"Uncertainty budget, $\Gamma$", ylabel="Reconfiguration intensity (RI)", xticks=GAMMAS)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, fontsize=7.5, ncol=3, loc="upper left")
    finish(fig, "fig_e4_ri_vs_gamma", output)


def material_case_figure(rows: list[dict[str, str]], output: Path) -> None:
    counts = [sum(int(row["Gamma"]) == gamma and float(row["RI"]) > 1e-6 for row in rows) for gamma in GAMMAS]
    fig, axis = plt.subplots(figsize=(6.4, 4.2), constrained_layout=True)
    axis.bar(GAMMAS, counts, color="#1f4e79", width=0.62)
    axis.plot(GAMMAS, counts, color="#111111", marker="o", linewidth=1.2)
    axis.set(xlabel=r"Uncertainty budget, $\Gamma$", ylabel="Cases with material reconfiguration", xticks=GAMMAS, yticks=range(0, 9))
    axis.set_ylim(0, 8.5)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)
    axis.spines[["top", "right"]].set_visible(False)
    finish(fig, "fig_e4_material_reconfiguration_cases_vs_gamma", output)


def generate_figures(rows: list[dict[str, str]], output: Path = OUTPUT) -> None:
    aggregate_trajectory(rows, "normalized_objective", r"Objective relative to $\Gamma=0$", "fig_e4_normalized_objective_vs_gamma", output)
    ri_figure(rows, output)
    material_case_figure(rows, output)
    aggregate_trajectory(rows, "normalized_robust_recourse", r"Robust recourse relative to $\Gamma=0$", "fig_e4_normalized_recourse_vs_gamma", output)


if __name__ == "__main__":
    generate_figures(load_rows())
    print("wrote 4 E4 figures in PNG and PDF")
