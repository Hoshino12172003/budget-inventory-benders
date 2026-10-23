from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "experiments/analysis/xxl10_four_method_final"
RECORDS = ANALYSIS / "xxl10_four_method_records.csv"
OUTPUT = ANALYSIS / "xxl10_certified_core_time_by_seed"
COLORS = {
    "Direct": "#405B73",
    "EF-BD": "#6F8FA8",
    "Aggregate-BD": "#9CB3C7",
    "PRB-BD": "#B7C1CA",
}


def build() -> None:
    with RECORDS.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fig, ax = plt.subplots(figsize=(7.2, 3.9), facecolor="white")
    ax.set_facecolor("white")
    seeds = list(range(20260921, 20260931))
    labels = [str(seed)[-2:] for seed in seeds]
    for method, color in COLORS.items():
        method_rows = {int(row["seed"]): row for row in rows if row["method"] == method}
        values = [
            float(method_rows[seed]["core_time_seconds"])
            if method_rows[seed]["exact_certification"] == "True" else float("nan")
            for seed in seeds
        ]
        ax.plot(labels, values, marker="o", linewidth=1.5, markersize=4.5, color=color, label=method)
    ax.set_xlabel("Seed (202609xx)")
    ax.set_ylabel("Exact-certified core time (s)")
    ax.grid(axis="y", color="#D9DDE2", linewidth=0.7, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors="#333333")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=4, frameon=False)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(OUTPUT.with_suffix(".png"), dpi=320, bbox_inches="tight", facecolor="white")
    fig.savefig(OUTPUT.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    build()
