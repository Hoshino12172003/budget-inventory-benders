from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments/results/prb_large_scale_simulation_v1"
ARTIFACTS = ROOT / "artifacts"
DOC = ROOT / "docs/large_scale_iteration_mechanism_final.md"
SCALES = ("L10", "XL10", "XXL10")
SEEDS = tuple(range(20260921, 20260931))
OBJECTIVE_TOLERANCE = 1e-4


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def load_results() -> dict[tuple[str, int, str], dict]:
    results = {}
    for scale in SCALES:
        for seed in SEEDS:
            for method in ("pure_benders", "aggregate_benders_structured_oracle", "prb_benders"):
                path = RESULTS / scale / str(seed) / method / "result.json"
                if not path.exists():
                    raise RuntimeError(f"MISSING_ALGORITHM_OBSERVATION: {scale} {seed} {method}")
                results[(scale, seed, method)] = read_json(path)
    return results


def certified_pair(left: dict, right: dict) -> bool:
    return (
        left.get("status") == "OPTIMAL"
        and right.get("status") == "OPTIMAL"
        and left.get("exact_certification") is True
        and right.get("exact_certification") is True
        and left.get("objective") is not None
        and right.get("objective") is not None
        and abs(float(left["objective"]) - float(right["objective"])) <= OBJECTIVE_TOLERANCE
    )


def pairs_for(
    results: dict[tuple[str, int, str], dict], left_method: str, scale: str
) -> list[tuple[dict, dict]]:
    pairs = []
    scales = SCALES if scale == "pooled" else (scale,)
    for current_scale in scales:
        for seed in SEEDS:
            left = results[(current_scale, seed, left_method)]
            prb = results[(current_scale, seed, "prb_benders")]
            if certified_pair(left, prb):
                pairs.append((left, prb))
    return pairs


def comparison_counts(left_iterations: list[float], prb_iterations: list[float]) -> tuple[int, int, int]:
    fewer = sum(prb < left for left, prb in zip(left_iterations, prb_iterations, strict=True))
    equal = sum(prb == left for left, prb in zip(left_iterations, prb_iterations, strict=True))
    more = sum(prb > left for left, prb in zip(left_iterations, prb_iterations, strict=True))
    return fewer, equal, more


def build_pure_table(results: dict[tuple[str, int, str], dict]) -> list[dict]:
    rows = []
    for scale in (*SCALES, "pooled"):
        pairs = pairs_for(results, "pure_benders", scale)
        pure = [float(left["iterations"]) for left, _ in pairs]
        prb = [float(right["iterations"]) for _, right in pairs]
        ratios = [right / left for left, right in zip(pure, prb, strict=True)]
        reductions = [(left - right) / left * 100.0 for left, right in zip(pure, prb, strict=True)]
        fewer, equal, more = comparison_counts(pure, prb)
        rows.append({
            "scale": scale,
            "paired_n": len(pairs),
            "pure_median_iterations": statistics.median(pure),
            "pure_q1_iterations": quantile(pure, 0.25),
            "pure_q3_iterations": quantile(pure, 0.75),
            "prb_median_iterations": statistics.median(prb),
            "prb_q1_iterations": quantile(prb, 0.25),
            "prb_q3_iterations": quantile(prb, 0.75),
            "median_prb_over_pure_iteration_ratio": statistics.median(ratios),
            "median_iteration_reduction_percent": statistics.median(reductions),
            "prb_fewer_iterations_count": fewer,
            "equal_iterations_count": equal,
            "prb_more_iterations_count": more,
        })
    return rows


def build_aggregate_table(results: dict[tuple[str, int, str], dict]) -> list[dict]:
    rows = []
    for scale in (*SCALES, "pooled"):
        pairs = pairs_for(results, "aggregate_benders_structured_oracle", scale)
        aggregate = [float(left["iterations"]) for left, _ in pairs]
        prb = [float(right["iterations"]) for _, right in pairs]
        ratios = [right / left for left, right in zip(aggregate, prb, strict=True)]
        reductions = [(left - right) / left * 100.0 for left, right in zip(aggregate, prb, strict=True)]
        fewer, equal, more = comparison_counts(aggregate, prb)
        rows.append({
            "scale": scale,
            "paired_n": len(pairs),
            "aggregate_median_iterations": statistics.median(aggregate),
            "prb_median_iterations": statistics.median(prb),
            "median_prb_over_aggregate_iteration_ratio": statistics.median(ratios),
            "median_iteration_reduction_percent": statistics.median(reductions),
            "prb_fewer_iterations_count": fewer,
            "equal_iterations_count": equal,
            "prb_more_iterations_count": more,
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_pure_vs_prb(results: dict[tuple[str, int, str], dict]) -> None:
    fig, axis = plt.subplots(figsize=(7.2, 4.6))
    positions = []
    values = []
    colors = []
    labels = []
    for index, scale in enumerate(SCALES, start=1):
        pairs = pairs_for(results, "pure_benders", scale)
        pure = [float(left["iterations"]) for left, _ in pairs]
        prb = [float(right["iterations"]) for _, right in pairs]
        positions.extend((index - 0.18, index + 0.18))
        values.extend((pure, prb))
        colors.extend(("#8C8C8C", "#2F5597"))
        labels.append(f"{scale}\n(n={len(pairs)}/10)")
    boxes = axis.boxplot(
        values,
        positions=positions,
        widths=0.28,
        patch_artist=True,
        showmeans=False,
        medianprops={"color": "black", "linewidth": 1.4},
        whiskerprops={"linewidth": 1.0},
        capprops={"linewidth": 1.0},
        flierprops={"marker": "o", "markersize": 3, "alpha": 0.7},
    )
    for box, color in zip(boxes["boxes"], colors, strict=True):
        box.set_facecolor(color)
        box.set_alpha(0.82)
    axis.set_xticks(range(1, len(SCALES) + 1), labels)
    axis.set_ylabel("Benders iterations")
    axis.set_title("Benders iteration counts across controlled network scales")
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.7, alpha=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color="#8C8C8C", alpha=0.82),
               plt.Rectangle((0, 0), 1, 1, color="#2F5597", alpha=0.82)]
    axis.legend(handles, ("Pure Benders", "PRB"), frameon=False, loc="upper left")
    fig.tight_layout()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(ARTIFACTS / "fig_pure_vs_prb_iterations.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(ARTIFACTS / "fig_pure_vs_prb_iterations.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_interpretation(pure_rows: list[dict], aggregate_rows: list[dict]) -> None:
    pooled_pure = pure_rows[-1]
    pooled_aggregate = aggregate_rows[-1]
    consistent = pooled_pure["prb_more_iterations_count"] == 0
    conclusion_en = (
        "Across the controlled large-scale instances, PRB consistently requires fewer Benders "
        "iterations than Pure Benders, indicating that retaining product-level risk-budget "
        "information in the master reduces repeated master-subproblem interaction."
        if consistent
        else "The certified paired instances show a mixed iteration response. The results do not "
        "support a claim that PRB consistently reduces Benders iterations relative to Pure Benders."
    )
    conclusion_zh = (
        "在受控的大规模仿真实例中，PRB 相比纯 Benders 整体需要更少的分解迭代轮次，表明在主问题中保留产品—风险预算信息能够减少重复的主从问题交互。"
        if consistent
        else "通过认证的配对实例呈现混合的迭代响应，因此不能声称 PRB 相对纯 Benders 一致减少迭代次数。"
    )
    lines = [
        "# Large-scale iteration mechanism",
        "",
        "## Scientific role",
        "",
        "Pure Benders is used as an iteration-mechanism baseline. It maintains one aggregate "
        "recourse representation. PRB retains product-risk-budget states in the master. The paired "
        "comparison asks whether the finer risk information reduces repeated master-subproblem "
        "interaction.",
        "",
        "The design contains three controlled network scales and ten seeds per scale. A Pure-PRB "
        "pair enters the paper table and figure only when both solutions are exactly certified and "
        "their objectives agree within `1e-4`. The three preserved Pure ERROR observations therefore "
        "remain in completeness reporting but not in the certified paired iteration statistics.",
        "",
        "## Pure Benders versus PRB",
        "",
        "| Scale | Paired n | Pure median | PRB median | Median PRB/Pure | Median reduction | Fewer / equal / more |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in pure_rows:
        lines.append(
            f"| {row['scale']} | {row['paired_n']} | {row['pure_median_iterations']:.3g} | "
            f"{row['prb_median_iterations']:.3g} | {row['median_prb_over_pure_iteration_ratio']:.3f} | "
            f"{row['median_iteration_reduction_percent']:.1f}% | "
            f"{row['prb_fewer_iterations_count']} / {row['equal_iterations_count']} / {row['prb_more_iterations_count']} |"
        )
    lines.extend(["", conclusion_en, "", conclusion_zh, "",
                  "## Aggregate with structured oracle versus PRB", "",
                  f"The pooled certified comparison contains {pooled_aggregate['paired_n']} pairs. "
                  f"The median PRB/Aggregate iteration ratio is "
                  f"{pooled_aggregate['median_prb_over_aggregate_iteration_ratio']:.3f}, with "
                  f"{pooled_aggregate['prb_fewer_iterations_count']} fewer, "
                  f"{pooled_aggregate['equal_iterations_count']} equal, and "
                  f"{pooled_aggregate['prb_more_iterations_count']} more iteration counts.", "",
                  "All non-iteration diagnostics remain available in the complete audit tables and raw "
                  "results. They are outside this paper mechanism statement.", ""])
    DOC.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    results = load_results()
    pure_rows = build_pure_table(results)
    aggregate_rows = build_aggregate_table(results)
    write_csv(ARTIFACTS / "table_pure_vs_prb_iterations_paper.csv", pure_rows)
    write_csv(ARTIFACTS / "table_aggregate_vs_prb_iterations_paper.csv", aggregate_rows)
    plot_pure_vs_prb(results)
    write_interpretation(pure_rows, aggregate_rows)


if __name__ == "__main__":
    main()
