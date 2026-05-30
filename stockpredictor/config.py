"""
Central configuration: named constants (no more magic numbers scattered through
the code) and a single ``AppConfig`` dataclass that the CLI and dashboard share.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

# --- Forecast defaults -------------------------------------------------------
HORIZON_MONTHS = 12
SEASONAL_PERIODS = 12
# Holt-Winters needs at least two full seasonal cycles to estimate seasonality.
MIN_MONTHS_FOR_SEASONAL = 2 * SEASONAL_PERIODS  # 24
# Below this we cannot fit anything meaningful at all.
MIN_MONTHS_FOR_ANY_FIT = 6
# Two-sided prediction-interval coverages to draw (95% and 80%).
INTERVAL_ALPHAS = (0.05, 0.20)

# --- Backtest defaults -------------------------------------------------------
BACKTEST_FOLDS = 4
BACKTEST_HORIZON = 3  # months predicted per fold

# --- Sentiment tilt defaults -------------------------------------------------
# The forecast is nudged by at most SENTIMENT_MAX_ADJ, scaled from the average
# sentiment by SENTIMENT_K, and the effect decays over the horizon with a time
# constant of SENTIMENT_DECAY_TAU months. This replaces the old, unbounded
# ``forecast * (1 + sentiment)`` which let a single headline move every month
# by up to 100%.
SENTIMENT_K = 0.02
SENTIMENT_MAX_ADJ = 0.05  # +/- 5% cap on month 1
SENTIMENT_DECAY_TAU = 2.5  # months

# --- News defaults -----------------------------------------------------------
NEWS_LOOKBACK_DAYS = 30
PAGE_SIZE = 5
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10
INTER_TICKER_SLEEP = 1.0

# --- Plot defaults -----------------------------------------------------------
PLOT_DPI = 150

DISCLAIMER = "Educational demo — not financial advice."


@dataclass
class AppConfig:
    """Runtime configuration shared by the CLI and the dashboard."""

    tickers: list[str] = field(default_factory=list)
    start: str = ""
    end: str = ""
    outdir: str = "stock_plots"

    horizon: int = HORIZON_MONTHS
    seasonal_periods: int = SEASONAL_PERIODS
    min_months_seasonal: int = MIN_MONTHS_FOR_SEASONAL

    page_size: int = PAGE_SIZE
    news_lookback_days: int = NEWS_LOOKBACK_DAYS
    max_retries: int = MAX_RETRIES
    request_timeout: int = REQUEST_TIMEOUT
    inter_ticker_sleep: float = INTER_TICKER_SLEEP

    sentiment_enabled: bool = True
    sentiment_k: float = SENTIMENT_K
    sentiment_max_adj: float = SENTIMENT_MAX_ADJ
    sentiment_decay_tau: float = SENTIMENT_DECAY_TAU
    sentiment_model: str = "vader"  # "vader" | "finbert"

    plot_dpi: int = PLOT_DPI
    backtest_folds: int = BACKTEST_FOLDS
    backtest_horizon: int = BACKTEST_HORIZON

    use_cache: bool = True
    db_path: str = "stockpredictor.db"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logging once and return the package logger."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("stockpredictor")
