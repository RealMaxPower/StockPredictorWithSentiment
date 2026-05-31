"""Tests for equity-curve metrics and the plain-language scorecard."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from stockpredictor import config, evaluation


def _curve(values) -> pd.Series:
    idx = pd.date_range("2015-01-31", periods=len(values), freq="ME")
    return pd.Series([float(v) for v in values], index=idx)


def test_total_return_and_cagr_on_known_curve():
    # 24 months, exactly doubling -> total return 1.0; CAGR over 2 years = sqrt(2)-1.
    eq = _curve(np.linspace(1.0, 2.0, 25))
    m = evaluation.equity_metrics(eq, rf_annual=0.0)
    assert m.total_return == pytest.approx(1.0)
    assert m.cagr == pytest.approx(math.sqrt(2.0) - 1.0, rel=1e-3)
    assert m.n_periods == 24


def test_max_drawdown_is_worst_peak_to_trough():
    eq = _curve([1.0, 1.5, 0.75, 1.2])  # peak 1.5 -> trough 0.75 = -50%
    m = evaluation.equity_metrics(eq, rf_annual=0.0)
    assert m.max_drawdown == pytest.approx(-0.5)


def test_hit_rate_counts_positive_periods():
    eq = _curve([1.0, 1.1, 1.0, 1.2, 1.25])  # up, down, up, up -> 3/4
    m = evaluation.equity_metrics(eq, rf_annual=0.0)
    assert m.hit_rate == pytest.approx(0.75)


def test_sharpe_positive_for_steady_growth_above_rf():
    eq = _curve([1.0 * (1.02**k) for k in range(13)])  # +2%/mo, zero vol-ish
    m = evaluation.equity_metrics(eq, rf_annual=0.0)
    assert m.sharpe > 0 or math.isnan(m.sharpe)  # constant growth -> sd 0 -> NaN allowed


def test_metrics_nan_safe_on_degenerate_curve():
    m = evaluation.equity_metrics(_curve([1.0]), rf_annual=0.04)
    assert math.isnan(m.cagr)
    assert m.n_periods == 0


def _flat(value: float, n: int = 25) -> pd.Series:
    return _curve([value] * n)


def test_scorecard_yes_when_strategy_dominates():
    strat = _curve(np.linspace(1.0, 2.0, 25))  # doubles
    bh = _curve(np.linspace(1.0, 1.2, 25))  # +20%
    rf = _curve([1.0 * (1.001**k) for k in range(25)])
    turnover = pd.Series([0.1] * 24)
    card = evaluation.build_scorecard(strat, bh, rf, turnover, rf_annual=0.0)
    assert card.beat_buy_and_hold is True
    assert card.beat_risk_free is True
    assert card.excess_cagr_vs_bh > 0
    assert card.skill_vs_bh > 1.0  # ended richer than BH


def test_scorecard_no_when_strategy_lags():
    strat = _curve(np.linspace(1.0, 1.05, 25))  # +5%
    bh = _curve(np.linspace(1.0, 2.0, 25))  # doubles
    rf = _curve(np.linspace(1.0, 1.5, 25))
    turnover = pd.Series([0.2] * 24)
    card = evaluation.build_scorecard(strat, bh, rf, turnover, rf_annual=0.0)
    assert card.beat_buy_and_hold is False
    assert card.beat_risk_free is False
    assert card.skill_vs_bh < 1.0


def test_annualized_turnover():
    # 24 months = 2 years; total turnover 6.0 -> 3.0x per year.
    strat = _curve(np.linspace(1.0, 1.1, 25))
    bh = _curve(np.linspace(1.0, 1.1, 25))
    rf = _curve([1.0] * 25)
    turnover = pd.Series([0.25] * 24)  # sum 6.0
    card = evaluation.build_scorecard(strat, bh, rf, turnover, rf_annual=0.0)
    assert card.turnover_annual == pytest.approx(3.0)


def test_format_scorecard_contains_verdict_warning_and_disclaimer():
    strat = _curve(np.linspace(1.0, 1.05, 25))
    bh = _curve(np.linspace(1.0, 2.0, 25))
    rf = _curve(np.linspace(1.0, 1.1, 25))
    card = evaluation.build_scorecard(strat, bh, rf, pd.Series([0.1] * 24), rf_annual=0.0)
    text = evaluation.format_scorecard(card, ticker="AAPL", variants_tried=4, holdout=card)
    assert "SCORECARD — AAPL" in text
    assert "Beat buy-and-hold?   NO" in text
    assert "Variants tried:      4" in text
    assert "likely overfit" in text
    assert "Held-out period:" in text
    assert config.DISCLAIMER in text
