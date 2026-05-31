"""
Position sizing: convert a ``Signal`` into a long-only position *fraction*.

Two pure, fully-tested methods (the strategy gate in ``strategy.py`` has already
decided *whether* to be in the market; sizing decides *how much*):

- **Volatility targeting** (default, more robust): size so the position's expected
  volatility hits ``cfg.target_vol`` (annualized). ``weight = target_vol /
  forecast_vol``, capped at ``max_weight``. It ignores the magnitude of μ — a
  calmer asset gets a bigger position, a wilder one a smaller position — which is
  far less sensitive to noisy return estimates than Kelly.

- **Fractional Kelly**: ``weight = clip(λ · μ_excess / σ², 0, max_weight)`` with
  ``λ = cfg.kelly_fraction`` (default **0.25**). Full Kelly (λ=1) is *never* the
  default: it maximizes long-run log-growth only with known parameters, and with
  *estimated* μ/σ it badly over-bets and courts ruinous drawdowns, so estimation
  error is punished by quartering the bet.

Both take ``μ`` as the expected return *in excess of the risk-free rate* (brief §5)
and are long-only: a non-positive excess returns weight 0, and the result never
goes negative. σ is the per-period return standard deviation from ``signals.py``;
vol targeting annualizes it by √12 to compare against the annual target.

⚠ Educational demo — not financial advice.
"""

from __future__ import annotations

import logging
import math

from . import config
from .signals import Signal

logger = logging.getLogger("stockpredictor.sizing")


def _excess_return(signal: Signal, cfg: config.AppConfig) -> float:
    """Expected return in excess of the per-period risk-free rate."""
    return signal.expected_return - config.periodic_rate(cfg.rf_annual)


def _clip(raw: float, max_weight: float) -> float:
    """Long-only clip into ``[0, max_weight]``."""
    return float(min(max(raw, 0.0), max_weight))


def vol_target_weight(signal: Signal, cfg: config.AppConfig) -> float:
    """Volatility targeting: ``target_vol / forecast_vol``, capped at ``max_weight``.

    As the forecast volatility shrinks the position grows and is capped at
    ``max_weight`` (σ→0 ⇒ full position, never more). A non-positive excess return
    yields weight 0 (long-only).
    """
    if _excess_return(signal, cfg) <= 0.0:
        return 0.0
    forecast_vol = signal.uncertainty * math.sqrt(config.PERIODS_PER_YEAR)
    raw = cfg.target_vol / forecast_vol  # σ>0 (guaranteed by Signal) -> safe divide
    return _clip(raw, cfg.max_weight)


def kelly_weight(signal: Signal, cfg: config.AppConfig) -> float:
    """Fractional Kelly: ``clip(λ · μ_excess / σ², 0, max_weight)``.

    Defaults to a quarter-Kelly bet. A non-positive excess return yields 0, and a
    vanishing σ² (extreme underflow) is treated as maximal conviction and capped at
    ``max_weight`` rather than dividing by zero.
    """
    excess = _excess_return(signal, cfg)
    if excess <= 0.0:
        return 0.0
    sigma2 = signal.uncertainty**2
    if sigma2 == 0.0:  # underflow guard: σ² rounded to 0 -> cap, don't divide
        return cfg.max_weight
    raw = cfg.kelly_fraction * excess / sigma2
    return _clip(raw, cfg.max_weight)


_METHODS = {"vol": vol_target_weight, "kelly": kelly_weight}


def size_position(signal: Signal, cfg: config.AppConfig) -> float:
    """Dispatch to the sizing method named by ``cfg.sizing_method`` ("vol"|"kelly").

    This is the ``SizingFn`` handed to ``strategy.make_weight_fn``; reading the
    method from ``cfg`` each call keeps the choice a logged, swappable variant.
    """
    method = _METHODS.get(cfg.sizing_method)
    if method is None:
        raise ValueError(
            f"unknown sizing_method {cfg.sizing_method!r}; expected one of {sorted(_METHODS)}"
        )
    return method(signal, cfg)
