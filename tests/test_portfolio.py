"""Tests for the paper-trading simulator: leakage, costs, benchmarks, determinism."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockpredictor import config
from stockpredictor.costs import TradingCosts
from stockpredictor.portfolio import (
    InsufficientHistoryError,
    fixed_weight_fn,
    simulate,
    total_return,
)


@pytest.fixture
def random_walk() -> pd.Series:
    """120 months of a driftless geometric random walk (no predictable structure)."""
    idx = pd.date_range("2010-01-31", periods=120, freq="ME")
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0, 0.05, 120)
    return pd.Series(100.0 * np.exp(np.cumsum(rets)), index=idx)


def _momentum_fn(history: pd.Series, _cfg: config.AppConfig) -> float:
    """Go long iff the most recently observed return is positive."""
    if len(history) < 2:
        return 0.0
    return 1.0 if history.iloc[-1] / history.iloc[-2] - 1.0 > 0 else 0.0


def test_benchmarks_share_index_and_start_at_one(random_walk, cfg):
    res = simulate(random_walk, fixed_weight_fn(1.0), cfg)
    assert res.equity.index.equals(res.benchmark_bh.index)
    assert res.equity.index.equals(res.benchmark_rf.index)
    assert res.equity.iloc[0] == pytest.approx(1.0)
    assert res.benchmark_bh.iloc[0] == pytest.approx(1.0)
    assert res.benchmark_rf.iloc[0] == pytest.approx(1.0)


def test_insufficient_history_raises(cfg):
    short = pd.Series(
        np.linspace(10, 12, 5), index=pd.date_range("2024-01-31", periods=5, freq="ME")
    )
    with pytest.raises(InsufficientHistoryError):
        simulate(short, fixed_weight_fn(1.0), cfg, warmup=6)


def test_weight_is_clipped_to_long_only_range(random_walk, cfg):
    over = simulate(random_walk, fixed_weight_fn(5.0), cfg)  # > max_weight
    under = simulate(random_walk, fixed_weight_fn(-2.0), cfg)  # < 0 (no shorting)
    assert (over.weights <= cfg.max_weight + 1e-12).all()
    assert (under.weights >= -1e-12).all()
    assert (under.weights == 0.0).all()


def test_full_invest_costless_matches_buy_and_hold(random_walk):
    """Fully invested with zero costs is exactly buy-and-hold."""
    free = config.AppConfig(commission_bps=0.0, spread_bps=0.0, slippage_bps=0.0)
    res = simulate(random_walk, fixed_weight_fn(1.0), free)
    assert np.allclose(res.equity.values, res.benchmark_bh.values)
    # And buy-and-hold equals the realized price return over the traded window.
    prices = random_walk.to_numpy()
    first = res.warmup
    assert total_return(res.benchmark_bh) == pytest.approx(prices[-1] / prices[first] - 1.0)


def test_all_cash_earns_risk_free(random_walk, cfg):
    """Weight 0 never trades, so the book is all cash compounding at the RF rate."""
    res = simulate(random_walk, fixed_weight_fn(0.0), cfg)
    assert np.allclose(res.equity.values, res.benchmark_rf.values)
    assert res.trades["cost"].sum() == 0.0  # nothing ever traded


def test_risk_free_benchmark_compounds(random_walk, cfg):
    res = simulate(random_walk, fixed_weight_fn(0.5), cfg)
    rf_period = config.periodic_rate(cfg.rf_annual)
    n_steps = len(res.benchmark_rf) - 1
    assert res.benchmark_rf.iloc[-1] == pytest.approx((1.0 + rf_period) ** n_steps)


def test_cost_param_monotonicity(random_walk):
    """Holding the weight path fixed, higher cost params give strictly lower return."""
    fn = fixed_weight_fn(1.0)
    cheap = config.AppConfig(commission_bps=1.0, spread_bps=2.0, slippage_bps=2.0)
    mid = config.AppConfig(commission_bps=5.0, spread_bps=10.0, slippage_bps=10.0)
    pricey = config.AppConfig(commission_bps=20.0, spread_bps=40.0, slippage_bps=40.0)
    r_cheap = total_return(simulate(random_walk, fn, cheap).equity)
    r_mid = total_return(simulate(random_walk, fn, mid).equity)
    r_pricey = total_return(simulate(random_walk, fn, pricey).equity)
    assert r_cheap > r_mid > r_pricey


def test_higher_turnover_pays_more_cost(random_walk, cfg):
    """A strategy that flips every period pays strictly more total cost than holding."""

    flips = {"n": 0}

    def flip_fn(_history: pd.Series, _cfg: config.AppConfig) -> float:
        flips["n"] += 1
        return float(flips["n"] % 2)  # 1, 0, 1, 0, ... -> turnover 1.0 every step

    hold_cost = simulate(random_walk, fixed_weight_fn(1.0), cfg).trades["cost"].sum()
    flip_cost = simulate(random_walk, flip_fn, cfg).trades["cost"].sum()
    assert flip_cost > hold_cost > 0.0


def test_leakage_peek_improves_results(random_walk, cfg):
    """Shifting the signal one period into the future must markedly improve results.

    The production path (peek=0) sees only past returns and has no edge on a random
    walk; peek=1 lets the same momentum rule see the about-to-be-realized return and
    time the market perfectly. If peeking did NOT improve things, the harness would
    be leaking the future on the production path — this test is the leakage tripwire.
    """
    honest = total_return(simulate(random_walk, _momentum_fn, cfg, peek=0).equity)
    peeking = total_return(simulate(random_walk, _momentum_fn, cfg, peek=1).equity)
    bh = total_return(simulate(random_walk, fixed_weight_fn(1.0), cfg).benchmark_bh)
    assert peeking > honest + 0.5  # peeking captures large, obvious gains
    assert peeking > bh  # and trounces buy-and-hold
    # The honest path does NOT clear buy-and-hold by the leakage margin.
    assert honest < peeking - 0.5


def test_determinism(random_walk, cfg):
    a = simulate(random_walk, _momentum_fn, cfg)
    b = simulate(random_walk, _momentum_fn, cfg)
    assert np.array_equal(a.equity.values, b.equity.values)
    assert np.array_equal(a.weights.values, b.weights.values)


def test_disclaimer_in_notes(random_walk, cfg):
    res = simulate(random_walk, fixed_weight_fn(1.0), cfg)
    assert any(config.DISCLAIMER in note for note in res.notes)


def test_custom_costs_override_config(random_walk, cfg):
    """An explicit TradingCosts argument takes precedence over the config."""
    free = TradingCosts(commission_bps=0.0, spread_bps=0.0, slippage_bps=0.0)
    res = simulate(random_walk, fixed_weight_fn(1.0), cfg, costs=free)
    assert res.trades["cost"].sum() == 0.0


def test_equity_plot_renders(random_walk, cfg, tmp_path):
    """The strategy-vs-BH-vs-RF overlay PNG renders to a non-empty file."""
    from stockpredictor import plotting

    res = simulate(random_walk, fixed_weight_fn(1.0), cfg)
    path = plotting.plot_equity_curve(res, "NVDA", str(tmp_path), cfg)
    assert path.endswith("NVDA_SIM_equity.png")
    import os

    assert os.path.getsize(path) > 0
