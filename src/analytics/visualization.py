from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure


def plot_romi_by_channel(df: pd.DataFrame) -> Figure:
    """Plot a horizontal bar chart of ROMI by channel sorted descending."""
    if "channel" not in df.columns or "romi" not in df.columns:
        raise KeyError("DataFrame must contain 'channel' and 'romi' columns")

    plot_df = df[["channel", "romi"]].copy()
    plot_df = plot_df.sort_values("romi", ascending=False).reset_index(drop=True)
    plot_df["channel"] = pd.Categorical(plot_df["channel"], categories=plot_df["channel"], ordered=True)

    fig, ax = plt.subplots(figsize=(8, 0.45 * len(plot_df) + 1.2))
    colors = ["#2ca02c" if value >= 0 else "#d62728" for value in plot_df["romi"]]
    bars = ax.barh(plot_df["channel"], plot_df["romi"], color=colors)

    ax.set_title("ROMI by channel")
    ax.set_xlabel("ROMI")
    ax.invert_yaxis()
    ax.axvline(0, color="black", linewidth=0.8)
    ax.grid(axis="x", linestyle="--", alpha=0.4)

    for bar, value in zip(bars, plot_df["romi"]):
        ax.text(
            value + (0.01 if value >= 0 else -0.01),
            bar.get_y() + bar.get_height() / 2,
            f"{value:.2f}",
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=9,
        )

    fig.tight_layout()
    return fig
