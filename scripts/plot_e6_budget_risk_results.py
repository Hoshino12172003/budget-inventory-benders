from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "artifacts/e6_table_budget_risk_interaction_aggregate.csv"
OUTPUT = ROOT / "artifacts"
BETAS = (("B080", "Tight, beta=0.8", "#b2182b"), ("B100", "Reference, beta=1.0", "#2166ac"), ("B120", "Relaxed, beta=1.2", "#4d9221"))
GAMMAS = (0, 2, 4)


def load_rows() -> list[dict[str, str]]:
    with TABLE.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def finish(fig, stem: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(OUTPUT / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style_axis(axis) -> None:
    axis.set_xticks(GAMMAS)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)


def interaction_plot(rows: list[dict[str, str]], metric: str, ylabel: str, stem: str, *, percent: bool = False) -> None:
    fig, axis = plt.subplots(figsize=(6.5, 4.2), constrained_layout=True)
    for token, label, color in BETAS:
        cell = sorted((row for row in rows if row["beta_token"] == token), key=lambda row: int(row["Gamma"]))
        axis.plot(GAMMAS, [float(row[metric]) for row in cell], marker="o", linewidth=2, color=color, label=label)
    axis.set(xlabel="Demand-risk budget, Gamma", ylabel=ylabel)
    style_axis(axis)
    if percent:
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.legend(frameon=False, fontsize=8)
    finish(fig, stem)


def heatmap(rows: list[dict[str, str]], metric: str, title: str, stem: str, *, percent: bool = False) -> None:
    matrix = [
        [float(next(row[metric] for row in rows if row["beta_token"] == token and int(row["Gamma"]) == gamma)) for gamma in GAMMAS]
        for token, _, _ in BETAS
    ]
    fig, axis = plt.subplots(figsize=(5.6, 3.7), constrained_layout=True)
    image = axis.imshow(matrix, cmap="Blues", aspect="auto")
    axis.set_xticks(range(3), GAMMAS)
    axis.set_yticks(range(3), ["beta=0.8", "beta=1.0", "beta=1.2"])
    axis.set(xlabel="Demand-risk budget, Gamma", ylabel="Financial-capacity level", title=title)
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            label = f"{value:.1%}" if percent else f"{value:.0f}/8"
            axis.text(j, i, label, ha="center", va="center", color="white" if value > max(map(max, matrix)) * 0.55 else "#222222")
    fig.colorbar(image, ax=axis, shrink=0.82)
    finish(fig, stem)


def main() -> None:
    rows = load_rows()
    interaction_plot(rows, "mean_RI", "Mean reconfiguration intensity", "fig_e6_ri_interaction", percent=True)
    interaction_plot(rows, "mean_normalized_objective", "Mean normalized objective", "fig_e6_normalized_objective_interaction")
    heatmap(rows, "mean_budget_utilization", "Mean budget utilization", "fig_e6_budget_utilization_heatmap", percent=True)
    heatmap(rows, "material_case_count", "Material reconfiguration cases", "fig_e6_material_reconfiguration_heatmap")
    print("wrote four E6 figures in PNG and PDF")


if __name__ == "__main__":
    main()
