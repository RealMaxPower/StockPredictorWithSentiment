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

import hashlib
import json
import logging
import math
from collections.abc import Callable
from dataclasses import asdict
from typing import TYPE_CHECKING

import pandas as pd

from . import config
from .signals import Signal, SignalFn, UnavailableSignalError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .portfolio import WeightFn
    from .sentiment import SentimentResult

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
        try:
            signal = signal_fn(history, cfg)
        except UnavailableSignalError as exc:
            logger.warning("Signal unavailable at %s; targeting cash: %s", history.index[-1], exc)
            return 0.0
        conviction = target_weight(signal, cfg)
        if conviction <= 0.0:
            return 0.0
        if sizing_fn is None:
            return conviction
        fraction = sizing_fn(signal, cfg)
        if not math.isfinite(fraction):
            raise ValueError("position sizing must return a finite weight")
        return float(min(max(fraction, 0.0), cfg.max_weight))

    return _fn


def build_weight_fn(
    cfg: config.AppConfig,
    *,
    sentiment: SentimentResult | None = None,
    signal_fn: SignalFn | None = None,
) -> WeightFn:
    """Assemble the production ``WeightFn``: forecast signal → gate → cfg-selected sizing.

    The sizing method (``vol`` | ``kelly``) is chosen inside ``sizing.size_position``
    from ``cfg.sizing_method`` each call, so it stays a logged, swappable variant.
    ``signal_fn`` is overridable for tests; by default it is the point-in-time
    forecast signal from ``signals.make_signal_fn``.
    """
    from . import signals, sizing

    signal_fn = signal_fn or signals.make_signal_fn(cfg, sentiment=sentiment)
    return make_weight_fn(signal_fn, sizing_fn=sizing.size_position)


def variant_config(cfg: config.AppConfig) -> dict[str, object]:
    """Canonical simulation settings, excluding presentation and news options."""
    fields = (
        "start",
        "end",
        "monthly_agg",
        "seasonal_periods",
        "min_months_seasonal",
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
        "sizing_method",
        "holdout_periods",
    )
    cfg_dict = asdict(cfg)
    return {
        **{name: cfg_dict[name] for name in fields},
        "warmup_months": config.SIM_WARMUP_MONTHS,
        "periods_per_year": config.PERIODS_PER_YEAR,
    }


def variant_id(
    cfg: config.AppConfig, *, data_fingerprint: str | None = None, code_version: str | None = None
) -> str:
    """Stable experiment identity including settings and optional data/code identity."""
    payload = {
        "schema": 2,
        "configuration": variant_config(cfg),
        "data_fingerprint": data_fingerprint,
        "code_version": code_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sim-v2-" + hashlib.sha256(canonical.encode()).hexdigest()
