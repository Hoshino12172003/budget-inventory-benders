from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
AGGREGATE = ARTIFACTS / "e6_table_budget_risk_interaction_aggregate.csv"
CASE_LEVEL = ARTIFACTS / "e6_table_budget_risk_interaction_case_level.csv"
BETAS = (
    ("B080", "Tight, beta=0.8", "#b2182b"),
    ("B100", "Reference, beta=1.0", "#2166ac"),
    ("B120", "Relaxed, beta=1.2", "#4d9221"),
)
GAMMAS = (0, 2, 4)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def finish(fig, stem: str) -> None:
    fig.savefig(ARTIFACTS / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(ARTIFACTS / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style(axis) -> None:
    axis.set_xticks(GAMMAS)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6)


def interaction(rows, metric, ylabel, stem, percent=False) -> None:
    fig, axis = plt.subplots(figsize=(6.5, 4.2), constrained_layout=True)
    for token, label, color in BETAS:
        cell = sorted((row for row in rows if row["beta_token"] == token), key=lambda row: int(row["Gamma"]))
        axis.plot(GAMMAS, [float(row[metric]) for row in cell], marker="o", linewidth=2, color=color, label=label)
    axis.set(xlabel="Demand-risk budget, Gamma", ylabel=ylabel)
    style(axis)
    if percent:
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.legend(frameon=False, fontsize=8)
    finish(fig, stem)


def heatmap(rows, metric, title, stem, *, count=False, percent=False) -> None:
    matrix = [
        [float(next(row[metric] for row in rows if row["beta_token"] == token and int(row["Gamma"]) == gamma)) for gamma in GAMMAS]
        for token, _, _ in BETAS
    ]
    fig, axis = plt.subplots(figsize=(5.6, 3.7), constrained_layout=True)
    image = axis.imshow(matrix, cmap="Blues", aspect="auto")
    axis.set_xticks(range(3), GAMMAS)
    axis.set_yticks(range(3), ["beta=0.8", "beta=1.0", "beta=1.2"])
    axis.set(xlabel="Demand-risk budget, Gamma", ylabel="Financial-capacity level", title=title)
    maximum = max(map(max, matrix))
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            label = f"{value:.1%}" if percent else f"{value:.0f}/8" if count else f"{value:.3f}"
            axis.text(j, i, label, ha="center", va="center", color="white" if maximum and value > maximum * 0.55 else "#222222")
    fig.colorbar(image, ax=axis, shrink=0.82)
    finish(fig, stem)


def case_trajectories(rows) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.8), sharey=True, constrained_layout=True)
    for axis, (token, label, _) in zip(axes, BETAS):
        for case in sorted({row["case"] for row in rows}):
            cell = sorted(
                (row for row in rows if row["beta_token"] == token and row["case"] == case),
                key=lambda row: int(row["Gamma"]),
            )
            axis.plot(GAMMAS, [float(row["RI"]) for row in cell], marker="o", linewidth=1.2, label=case)
        axis.set_title(label)
        axis.set_xlabel("Gamma")
        style(axis)
    axes[0].set_ylabel("Reconfiguration intensity")
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[-1].legend(frameon=False, fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
    finish(fig, "fig_e6_case_level_ri_trajectories")


def main() -> None:
    aggregate = read_csv(AGGREGATE)
    cases = read_csv(CASE_LEVEL)
    interaction(aggregate, "mean_RI", "Mean reconfiguration intensity", "fig_e6_ri_interaction", percent=True)
    interaction(aggregate, "mean_normalized_objective", "Mean normalized objective", "fig_e6_normalized_objective_interaction")
    heatmap(aggregate, "mean_budget_utilization", "Mean budget utilization", "fig_e6_budget_utilization_heatmap", percent=True)
    heatmap(aggregate, "material_case_count", "Material reconfiguration cases", "fig_e6_material_cases_heatmap", count=True)
    heatmap(aggregate, "active_depot_change_case_count", "Cases with y-network change", "fig_e6_active_depot_change_heatmap", count=True)
    case_trajectories(cases)
    print("wrote six E6 figures in PNG and PDF")


if __name__ == "__main__":
    main()
