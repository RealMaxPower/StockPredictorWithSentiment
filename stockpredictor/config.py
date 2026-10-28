"""
Central configuration: named constants (no more magic numbers scattered through
the code) and a single ``AppConfig`` dataclass that the CLI and dashboard share.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date

# --- Forecast defaults -------------------------------------------------------
HORIZON_MONTHS = 12
SEASONAL_PERIODS = 12
# Holt-Winters needs at least two full seasonal cycles to estimate seasonality.
MIN_MONTHS_FOR_SEASONAL = 2 * SEASONAL_PERIODS  # 24
# Below this we cannot fit anything meaningful at all.
MIN_MONTHS_FOR_ANY_FIT = 6
# Two-sided prediction-interval coverages to draw (95% and 80%).
INTERVAL_ALPHAS = (0.05, 0.20)
# Monthly resampling: "last" keeps the month-end close (the value a point-in-time
# forecast can actually be compared against); "mean" averages within the month,
# which smooths the series and flatters every skill metric (diagnostics only).
MONTHLY_AGG = "last"

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

# --- Simulation / trading-cost defaults --------------------------------------
# Paper-trading only: these drive a *simulated* book, never a real order.
# Defaults are deliberately conservative (retail-realistic) so a backtest is not
# flattered by free, frictionless trading. Costs are ALWAYS applied — there is no
# gross-of-cost headline. See ``costs.py`` and ``portfolio.py``.
PERIODS_PER_YEAR = 12  # monthly rebalance cadence, matching the forecast
COMMISSION_BPS = 1.0  # broker commission per trade leg (bps of notional)
SPREAD_BPS = 5.0  # full bid/ask spread (bps); a trade crosses half of it
SLIPPAGE_BPS = 5.0  # market-impact / slippage (bps of notional)
FIXED_FEE = 0.0  # optional flat fee per (non-zero) trade, in currency
INITIAL_CAPITAL = 10_000.0  # currency units; plots normalize starting wealth to 1
RF_ANNUAL = 0.04  # risk-free rate; a constant default emits a warning
MAX_WEIGHT = 1.0  # long-only, no leverage: weight is clipped to [0, 1]
TARGET_VOL = 0.10  # annualized volatility target for vol-sizing
KELLY_FRACTION = 0.25  # fractional Kelly (full Kelly is never the default)
CONFIDENCE_FLOOR = 0.0  # minimum signal confidence to take any position
MIN_EXCESS_RETURN = 0.0  # per-period excess return (μ−rf) required to go long
SIM_WARMUP_MONTHS = MIN_MONTHS_FOR_ANY_FIT  # history needed before the first trade
HOLDOUT_PERIODS = 12  # descriptive final-period slice, not protected validation
# Below this many rebalances, annualized CAGR/Sharpe are extrapolated from too few
# points to trust; the scorecard says so loudly rather than printing a tidy lie.
MIN_RELIABLE_PERIODS = 24  # ~2 years of monthly rebalances

DISCLAIMER = "Educational demo — not financial advice."


def periodic_rate(annual_rate: float, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Convert an annual rate to the equivalent compounded per-period rate.

    Shared by the simulator (cash/risk-free leg), the strategy threshold (excess
    over RF), and the evaluation metrics so the risk-free convention never
    diverges between them.
    """
    return (1.0 + annual_rate) ** (1.0 / periods_per_year) - 1.0


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
    monthly_agg: str = MONTHLY_AGG  # "last" (month-end close) | "mean" (within-month average)

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

    # --- Simulated betting / position-sizing layer ---------------------------
    # Trading costs (bps of traded notional) — always applied in the simulator.
    commission_bps: float = COMMISSION_BPS
    spread_bps: float = SPREAD_BPS
    slippage_bps: float = SLIPPAGE_BPS
    fixed_fee: float = FIXED_FEE
    initial_capital: float = INITIAL_CAPITAL
    # Risk-free, position limits, and sizing.
    rf_annual: float = RF_ANNUAL
    max_weight: float = MAX_WEIGHT
    target_vol: float = TARGET_VOL
    kelly_fraction: float = KELLY_FRACTION
    confidence_floor: float = CONFIDENCE_FLOOR
    min_excess_return: float = MIN_EXCESS_RETURN  # per-period μ−rf above which we go long
    sizing_method: str = "vol"  # "vol" (volatility targeting) | "kelly"
    holdout_periods: int = HOLDOUT_PERIODS

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Reject invalid settings before network requests or expensive model fits."""
        for name in ("start", "end"):
            value = getattr(self, name)
            if value:
                try:
                    parsed = date.fromisoformat(value)
                    if parsed.isoformat() != value:
                        raise ValueError
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{name} must be YYYY-MM-DD") from exc
        if self.start and self.end and self.start >= self.end:
            raise ValueError("start must be before end (exclusive)")
        for name in (
            "horizon",
            "seasonal_periods",
            "min_months_seasonal",
            "page_size",
            "news_lookback_days",
            "max_retries",
            "plot_dpi",
            "backtest_folds",
            "backtest_horizon",
            "holdout_periods",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.seasonal_periods < 2:
            raise ValueError("seasonal_periods must be at least 2")
        if self.min_months_seasonal < 2 * self.seasonal_periods:
            raise ValueError("min_months_seasonal must cover at least two seasonal cycles")
        if self.page_size > 100:
            raise ValueError("page_size must be at most 100")
        for name in (
            "request_timeout",
            "inter_ticker_sleep",
            "sentiment_k",
            "sentiment_max_adj",
            "sentiment_decay_tau",
            "commission_bps",
            "spread_bps",
            "slippage_bps",
            "fixed_fee",
            "initial_capital",
            "rf_annual",
            "max_weight",
            "target_vol",
            "kelly_fraction",
            "confidence_floor",
            "min_excess_return",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if name != "rf_annual" and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in ("request_timeout", "sentiment_decay_tau", "initial_capital", "target_vol"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.rf_annual <= -1:
            raise ValueError("rf_annual must be greater than -1")
        for name in ("max_weight", "kelly_fraction", "confidence_floor"):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.sentiment_max_adj >= 1:
            raise ValueError("sentiment_max_adj must be below 1")
        if self.monthly_agg not in ("last", "mean"):
            raise ValueError("monthly_agg must be 'last' or 'mean'")
        if self.sentiment_model not in ("vader", "finbert"):
            raise ValueError("sentiment_model must be 'vader' or 'finbert'")
        if self.sizing_method not in ("vol", "kelly"):
            raise ValueError("sizing_method must be 'vol' or 'kelly'")


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logging once and return the package logger."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("stockpredictor")
