"""Tests for the long-only threshold strategy and the signal→weight composition.

Includes the brief's zero-edge and known-edge synthetic checks: the strategy must
not manufacture an edge from noise, and must capture a real, lagged one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockpredictor import config, strategy
from stockpredictor.portfolio import simulate, total_return
from stockpredictor.signals import Signal


def _signal(mu: float, confidence: float = 1.0, sigma: float = 0.05) -> Signal:
    return Signal(
        expected_return=mu,
        uncertainty=sigma,
        confidence=confidence,
        as_of=pd.Timestamp("2025-01-31"),
    )


def test_long_when_excess_return_positive():
    cfg = config.AppConfig()
    rf_period = config.periodic_rate(cfg.rf_annual)
    assert strategy.target_weight(_signal(rf_period + 0.05), cfg) == cfg.max_weight


def test_flat_when_no_excess_over_cash():
    cfg = config.AppConfig()
    rf_period = config.periodic_rate(cfg.rf_annual)
    assert strategy.target_weight(_signal(rf_period), cfg) == 0.0  # exactly rf -> no edge
    assert strategy.target_weight(_signal(-0.10), cfg) == 0.0  # bearish


def test_long_only_never_negative():
    cfg = config.AppConfig()
    for mu in (-0.5, -0.01, 0.0, 0.2):
        assert strategy.target_weight(_signal(mu), cfg) >= 0.0


def test_confidence_floor_gates_position():
    cfg = config.AppConfig(confidence_floor=0.5)
    bullish = _signal(0.05, confidence=0.2)  # would be long but confidence too low
    assert strategy.target_weight(bullish, cfg) == 0.0
    assert strategy.target_weight(_signal(0.05, confidence=0.9), cfg) == cfg.max_weight


def test_min_excess_return_raises_the_bar():
    cfg = config.AppConfig(min_excess_return=0.02)
    rf_period = config.periodic_rate(cfg.rf_annual)
    assert strategy.target_weight(_signal(rf_period + 0.01), cfg) == 0.0  # below the bar
    assert strategy.target_weight(_signal(rf_period + 0.03), cfg) == cfg.max_weight


def test_make_weight_fn_without_sizing_is_full_conviction():
    cfg = config.AppConfig()
    bullish = lambda _h, _c: _signal(0.05)  # noqa: E731
    bearish = lambda _h, _c: _signal(-0.05)  # noqa: E731
    hist = pd.Series([1.0, 2.0])
    assert strategy.make_weight_fn(bullish)(hist, cfg) == cfg.max_weight
    assert strategy.make_weight_fn(bearish)(hist, cfg) == 0.0


def test_make_weight_fn_applies_and_clips_sizing():
    cfg = config.AppConfig(max_weight=0.8)
    bullish = lambda _h, _c: _signal(0.05)  # noqa: E731
    hist = pd.Series([1.0, 2.0])
    # Sizing over the cap is clipped to max_weight; a gated-out signal stays 0.
    over = strategy.make_weight_fn(bullish, sizing_fn=lambda _s, _c: 5.0)
    half = strategy.make_weight_fn(bullish, sizing_fn=lambda _s, _c: 0.3)
    neg = strategy.make_weight_fn(bullish, sizing_fn=lambda _s, _c: -1.0)
    assert over(hist, cfg) == 0.8
    assert half(hist, cfg) == pytest.approx(0.3)
    assert neg(hist, cfg) == 0.0


def test_variant_id_is_deterministic_and_sensitive():
    a = strategy.variant_id(config.AppConfig())
    b = strategy.variant_id(config.AppConfig())
    c = strategy.variant_id(config.AppConfig(kelly_fraction=0.5))
    assert a == b
    assert a != c


def test_build_weight_fn_applies_cfg_sizing():
    """The assembled WeightFn runs gate → sizing: a bullish signal is sized < cap."""
    from stockpredictor import sizing

    cfg = config.AppConfig(sizing_method="vol", target_vol=0.10, max_weight=1.0)
    bullish = lambda _h, _c: _signal(0.05, sigma=0.10)  # noqa: E731
    wf = strategy.build_weight_fn(cfg, signal_fn=bullish)
    expected = sizing.size_position(_signal(0.05, sigma=0.10), cfg)
    assert wf(pd.Series([1.0, 2.0]), cfg) == pytest.approx(expected)
    assert 0.0 < expected < cfg.max_weight  # genuinely sized, not just the cap


def test_build_weight_fn_real_forecast_path_runs(monthly, cfg):
    """Default path (real forecast signal + cfg sizing) drives the simulator cleanly."""
    res = simulate(monthly, strategy.build_weight_fn(cfg), cfg)
    assert (res.weights >= 0.0).all()
    assert (res.weights <= cfg.max_weight + 1e-12).all()


# --- Synthetic zero-edge / known-edge checks ---------------------------------
def _momentum_signal(history: pd.Series, _cfg: config.AppConfig) -> Signal:
    """Naive predictor: next return ≈ last observed return. Only works if returns
    are serially correlated; on i.i.d. data it is pure noise."""
    rets = history.pct_change().dropna()
    mu = float(rets.iloc[-1])
    sigma = max(float(rets.std()), 0.01)
    return Signal(expected_return=mu, uncertainty=sigma, confidence=1.0, as_of=history.index[-1])


def _ar1_prices(seed: int, phi: float, *, sigma: float = 0.05, drift: float = 0.0067, n: int = 160):
    """Geometric series whose returns follow AR(1): r_t = drift + φ·r_{t-1} + ε.

    ``drift`` (~8%/yr) makes buy-and-hold a *fair, strong* benchmark, so beating it
    requires real timing skill — not just parking in cash to dodge volatility drag.
    """
    rng = np.random.default_rng(seed)
    eps = rng.normal(0.0, sigma, n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = drift + phi * r[t - 1] + eps[t]
    idx = pd.date_range("2008-01-31", periods=n, freq="ME")
    return pd.Series(100.0 * np.exp(np.cumsum(r)), index=idx)


def _wins_vs_buy_and_hold(phi: float, seeds: range) -> int:
    cfg = config.AppConfig()
    weight_fn = strategy.make_weight_fn(_momentum_signal)
    wins = 0
    for s in seeds:
        res = simulate(_ar1_prices(s, phi), weight_fn, cfg)
        if total_return(res.equity) > total_return(res.benchmark_bh):
            wins += 1
    return wins


def test_zero_edge_does_not_reliably_beat_buy_and_hold():
    """No serial structure (φ=0): the momentum strategy must NOT reliably beat BH
    after costs. If it did, the harness would be flattering noise."""
    seeds = range(20)
    wins = _wins_vs_buy_and_hold(phi=0.0, seeds=seeds)
    assert wins < len(seeds) * 0.4  # a minority — no durable edge


def test_known_edge_is_captured():
    """A real, lagged predictability (φ=0.4): the strategy should capture it and
    beat BH in a strong majority of seeds. Guards against a sim/sizing bug that
    destroys genuine signal."""
    seeds = range(20)
    wins = _wins_vs_buy_and_hold(phi=0.4, seeds=seeds)
    assert wins >= len(seeds) * 0.75
