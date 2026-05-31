"""
Strategy: map a ``Signal`` to a *target* position, applying the long-only
constraints and the entry threshold. This is where "should I hold this at all?"
is decided; *how much* to hold (vol-targeting / fractional Kelly) is ``sizing.py``
(Phase 3), which plugs into ``make_weight_fn`` below.

The default rule is deliberately simple and testable:

- If the signal's confidence is below ``cfg.confidence_floor`` → weight 0.
- If the expected return is not above the risk-free rate by at least
  ``cfg.min_excess_return`` → weight 0 (no edge over cash ⇒ no position).
- Otherwise the strategy expresses full conviction (``cfg.max_weight``); long-only,
  so the weight is never negative.

Strategy/parameter choices are captured by ``variant_id`` so every backtested
variant can be logged and counted — the multiple-testing discipline of brief §3.5
(the best-looking of N variants is likely overfit).

⚠ Educational demo — not financial advice.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

import pandas as pd

from . import config
from .signals import Signal, SignalFn

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .portfolio import WeightFn

logger = logging.getLogger("stockpredictor.strategy")

# How sizing converts a Signal into a position fraction (filled in by sizing.py).
SizingFn = Callable[[Signal, config.AppConfig], float]


def target_weight(signal: Signal, cfg: config.AppConfig) -> float:
    """Long-only threshold rule: full conviction when the signal beats cash, else 0.

    Returns a value in ``[0, cfg.max_weight]``. ``sizing.py`` later scales this
    conviction down to a risk-calibrated fraction; on its own (Phase 2) the strategy
    is "all-in when bullish, flat otherwise".
    """
    if signal.confidence < cfg.confidence_floor:
        return 0.0
    rf_period = config.periodic_rate(cfg.rf_annual)
    excess = signal.expected_return - rf_period
    if excess <= cfg.min_excess_return:
        return 0.0
    return float(min(max(cfg.max_weight, 0.0), cfg.max_weight))


def make_weight_fn(
    signal_fn: SignalFn,
    *,
    sizing_fn: SizingFn | None = None,
) -> WeightFn:
    """Compose ``signal → strategy gate → (optional) sizing`` into a ``WeightFn``.

    The returned function is what ``portfolio.simulate`` drives. The strategy gate
    decides whether to be in the market at all; when it is, ``sizing_fn`` (Phase 3)
    sets the magnitude, clipped to ``[0, max_weight]``. Without a ``sizing_fn`` the
    strategy's own conviction is used directly. Point-in-time discipline is the
    simulator's job: ``signal_fn`` only ever sees the history it is handed.
    """

    def _fn(history: pd.Series, cfg: config.AppConfig) -> float:
        signal = signal_fn(history, cfg)
        conviction = target_weight(signal, cfg)
        if conviction <= 0.0:
            return 0.0
        if sizing_fn is None:
            return conviction
        fraction = sizing_fn(signal, cfg)
        return float(min(max(fraction, 0.0), cfg.max_weight))

    return _fn


def variant_id(cfg: config.AppConfig) -> str:
    """A readable, deterministic identity for the full strategy/cost configuration.

    Logged with every simulation run so the reporting layer can count how many
    variants were tried and warn that the best of N is likely overfit (brief §3.5).
    """
    return ";".join(
        (
            f"sizing={cfg.sizing_method}",
            f"floor={cfg.confidence_floor:g}",
            f"minexc={cfg.min_excess_return:g}",
            f"maxw={cfg.max_weight:g}",
            f"tvol={cfg.target_vol:g}",
            f"kelly={cfg.kelly_fraction:g}",
            f"cost={cfg.commission_bps:g}/{cfg.spread_bps:g}/{cfg.slippage_bps:g}",
            f"rf={cfg.rf_annual:g}",
        )
    )
