"""
Rendering: a static matplotlib PNG with shaded prediction intervals (so the chart
no longer implies false precision) and an optional self-contained interactive
Plotly HTML for CLI users who want hover/zoom.
"""

from __future__ import annotations

import logging
import os

import pandas as pd

from . import config
from .forecast import ForecastResult

logger = logging.getLogger("stockpredictor.plotting")


def plot_forecast(
    monthly: pd.Series,
    result: ForecastResult,
    adjusted: pd.Series | None,
    ticker: str,
    out_dir: str,
    cfg: config.AppConfig,
    sentiment_label: str = "",
) -> str:
    """Save a PNG: history, forecast, shaded intervals, and sentiment-adjusted line."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(monthly.index, monthly.values, label="Historical", color="#1f77b4")
    ax.plot(result.point.index, result.point.values, label="Forecast", color="#ff7f0e", linewidth=2)

    # Shaded prediction intervals (widest first so narrower draws on top).
    shades = {95: 0.12, 80: 0.20}
    for coverage in sorted(result.intervals, reverse=True):
        lower, upper = result.intervals[coverage]
        ax.fill_between(
            lower.index,
            lower.values,
            upper.values,
            color="#ff7f0e",
            alpha=shades.get(coverage, 0.15),
            label=f"{coverage}% interval",
        )

    if adjusted is not None:
        ax.plot(
            adjusted.index,
            adjusted.values,
            label="Sentiment-adjusted",
            color="#2ca02c",
            linestyle="--",
        )

    seasonal = "seasonal" if result.seasonal_used else "non-seasonal"
    title = f"{ticker}: {cfg.horizon}-month forecast ({seasonal})"
    if sentiment_label:
        title += f" — news: {sentiment_label}"
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.legend(loc="upper left", fontsize=8)
    fig.text(
        0.99,
        0.01,
        config.DISCLAIMER,
        ha="right",
        va="bottom",
        fontsize=7,
        color="gray",
        style="italic",
    )
    fig.tight_layout()

    path = os.path.join(out_dir, f"{ticker}_forecasts.png")
    fig.savefig(path, dpi=cfg.plot_dpi)
    plt.close(fig)
    logger.info("%s: saved plot %s", ticker, path)
    return path


def write_interactive_html(
    monthly: pd.Series,
    result: ForecastResult,
    adjusted: pd.Series | None,
    ticker: str,
    out_dir: str,
    sentiment_label: str = "",
) -> str | None:
    """Write a self-contained interactive Plotly HTML. No-op if plotly is missing."""
    try:
        fig = build_plotly_figure(monthly, result, adjusted, ticker, sentiment_label)
    except ImportError:
        logger.info("%s: plotly not installed; skipping interactive HTML", ticker)
        return None
    path = os.path.join(out_dir, f"{ticker}_forecast.html")
    fig.write_html(path, include_plotlyjs="cdn")
    logger.info("%s: saved interactive chart %s", ticker, path)
    return path


def build_plotly_figure(
    monthly: pd.Series,
    result: ForecastResult,
    adjusted: pd.Series | None,
    ticker: str,
    sentiment_label: str = "",
):
    """Build a Plotly figure with the shaded 95% band (shared by HTML export + app)."""
    import plotly.graph_objects as go

    # Pin colors so the legend is deterministic and matches the matplotlib PNG.
    # (Plotly's auto color-cycle would otherwise be consumed by the invisible band
    # boundary traces, leaving the visible lines with arbitrary leftover colors.)
    hist_color, fcast_color, adj_color = "#1f77b4", "#ff7f0e", "#2ca02c"

    fig = go.Figure()
    fig.add_scatter(
        x=monthly.index, y=monthly.values, name="Historical", line=dict(color=hist_color)
    )
    if 95 in result.intervals:
        lo, hi = result.intervals[95]
        # mode="lines" is required: Plotly defaults to lines+markers for short
        # series (the horizon is only 12 points), so width=0 alone would still
        # draw the band edges as stray marker dots over the shaded fill.
        fig.add_scatter(
            x=hi.index,
            y=hi.values,
            name="95% upper",
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
        fig.add_scatter(
            x=lo.index,
            y=lo.values,
            name="95% interval",
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(255,127,14,0.15)",
            line=dict(width=0),
            hoverinfo="skip",
        )
    fig.add_scatter(
        x=result.point.index, y=result.point.values, name="Forecast", line=dict(color=fcast_color)
    )
    if adjusted is not None:
        fig.add_scatter(
            x=adjusted.index,
            y=adjusted.values,
            name="Sentiment-adjusted",
            line=dict(color=adj_color, dash="dash"),
        )
    title = f"{ticker}: forecast with uncertainty"
    if sentiment_label:
        title += f" — news: {sentiment_label}"
    # Disclaimer rides in the title as a subtitle so it never collides with the
    # x-axis date labels / rangeslider at the bottom of the figure.
    title += f"<br><sup>{config.DISCLAIMER}</sup>"
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=True,
    )
    return fig
