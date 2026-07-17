import pandas as pd
from matplotlib.figure import Figure

from src.analytics.visualization import plot_romi_by_channel


def test_plot_romi_by_channel_returns_figure_with_sorted_labels_and_values():
    df = pd.DataFrame(
        [
            {"channel": "email", "romi": -0.2},
            {"channel": "social_ads", "romi": 0.5},
            {"channel": "seo", "romi": 0.1},
            {"channel": "context_ads", "romi": -0.1},
        ]
    )

    fig = plot_romi_by_channel(df)

    assert isinstance(fig, Figure)
    ax = fig.axes[0]
    expected_labels = ["social_ads", "seo", "context_ads", "email"]
    assert ax.get_title() == "ROMI by channel"
    assert [tick.get_text() for tick in ax.get_yticklabels()] == expected_labels
    assert len(ax.texts) == len(df)
