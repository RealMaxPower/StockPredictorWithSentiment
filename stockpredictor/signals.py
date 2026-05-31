"""
Signal extraction: turn a forecast (point path + prediction intervals + sentiment)
into a normalized trading ``Signal``. This module is *translation only* — there is
deliberately no trading logic here (that lives in ``strategy.py`` / ``sizing.py``).

A ``Signal`` carries three numbers and a timestamp:

- ``expected_return`` (μ): the one-rebalance-ahead forecast return, i.e. the
  horizon-1 point forecast expressed as a return off the last observed price.
- ``uncertainty`` (σ): a per-period return standard deviation *derived from the
  existing prediction interval*, not invented. Under a normal approximation an 80%
  two-sided band spans ±1.2816σ, so σ ≈ (upper₈₀ − lower₈₀) / (2 · 1.2816). Wider
  bands ⇒ larger σ ⇒ (downstream) smaller positions. The normal approximation is an
  assumption; the bands themselves come from Monte-Carlo simulation of the fit.
- ``confidence``: the existing sentiment sample-size + agreement score in [0, 1]
  (0 when there is no news). It is reused here unchanged so the strategy can
  optionally gate on it; with the default ``confidence_floor`` of 0 it is non-binding.

The ``SignalFn`` seam mirrors ``portfolio.WeightFn``: given the point-in-time price
history (timestamps ≤ t), produce the Signal valid as-of t. The real implementation
fits the forecast on that history; tests inject cheap synthetic signal functions.

⚠ Educational demo — not financial advice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from . import config, forecast
from .forecast import ForecastResult
from .sentiment import SentimentResult

logger = logging.getLogger("stockpredictor.signals")

# Two-sided normal z-scores: an 80% band is ±1.2816σ, a 95% band ±1.9600σ. Used to
# back out σ from a prediction-interval half-width (norm.ppf(0.90) / norm.ppf(0.975)).
_Z80 = 1.2815515594
_Z95 = 1.9599639845

# Floor on σ so downstream sizing never divides by ~0 (a vanishing band would imply
# infinite conviction, which is never warranted from an estimated model).
_MIN_SIGMA = 1e-6


@dataclass(frozen=True)
class Signal:
    """A normalized, point-in-time trading signal (no position logic attached)."""

    expected_return: float  # μ: one-period-ahead expected return (decimal, e.g. 0.01)
    uncertainty: float  # σ: per-period return standard deviation (> 0)
    confidence: float  # [0, 1]; reused sentiment sample-size + agreement score
    as_of: pd.Timestamp  # the timestamp this signal may be acted on

    def __post_init__(self) -> None:
        if self.uncertainty <= 0:
            raise ValueError(f"uncertainty (σ) must be positive, got {self.uncertainty}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


# A signal function maps (point-in-time price history, config) -> Signal.
SignalFn = Callable[[pd.Series, config.AppConfig], Signal]


def _sigma_from_intervals(fc: ForecastResult, last_price: float) -> float:
    """Back out a per-period return σ from the horizon-1 prediction interval.

    Prefers the 80% band (most points fall inside it, so it is the better-estimated
    half-width), falls back to the 95% band, and finally to a small floor if no band
    is available. The band is in price space around the point forecast; dividing the
    return-space half-width by the normal z-score recovers σ.
    """
    for coverage, z in ((80, _Z80), (95, _Z95)):
        band = fc.intervals.get(coverage)
        if band is None:
            continue
        lower, upper = band
        half_width_price = (float(upper.iloc[0]) - float(lower.iloc[0])) / 2.0
        sigma = (half_width_price / z) / last_price
        if sigma > 0:
            return sigma
    logger.debug("No usable prediction interval for σ; falling back to σ floor.")
    return _MIN_SIGMA


def signal_from_forecast(
    fc: ForecastResult,
    last_price: float,
    *,
    sentiment: SentimentResult | None = None,
    as_of: pd.Timestamp | None = None,
) -> Signal:
    """Translate a ``ForecastResult`` into a ``Signal`` (μ, σ, confidence, as-of).

    μ is the horizon-1 forecast return; σ comes from the interval width; confidence
    is the sentiment score (0 when no news / sentiment unavailable).
    """
    point0 = float(fc.point.iloc[0])
    mu = point0 / last_price - 1.0
    sigma = max(_sigma_from_intervals(fc, last_price), _MIN_SIGMA)
    confidence = sentiment.confidence if (sentiment is not None and sentiment.has_news) else 0.0
    as_of = as_of if as_of is not None else fc.point.index[0]
    return Signal(expected_return=mu, uncertainty=sigma, confidence=float(confidence), as_of=as_of)


def make_signal_fn(
    cfg: config.AppConfig,
    *,
    sentiment: SentimentResult | None = None,
) -> SignalFn:
    """Build the production ``SignalFn`` that fits the forecast on point-in-time data.

    At each rebalance it refits Holt-Winters on the supplied history (timestamps ≤ t),
    takes the one-month-ahead point + intervals, and folds in the (optional) sentiment
    confidence. ``sentiment`` is held fixed across the walk for now; a point-in-time
    sentiment panel is future work (brief §8 Phase 5).
    """

    def _fn(history: pd.Series, cfg_in: config.AppConfig) -> Signal:
        fc = forecast.forecast_with_intervals(history, cfg_in, horizon=1)
        return signal_from_forecast(
            fc,
            last_price=float(history.iloc[-1]),
            sentiment=sentiment,
            as_of=history.index[-1],
        )

    return _fn
