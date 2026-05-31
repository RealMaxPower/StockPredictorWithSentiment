"""Tests for forecasting, intervals, baselines, metrics, and backtesting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockpredictor import forecast as fc


def test_forecast_shape_and_intervals(monthly, cfg):
    res = fc.forecast_with_intervals(monthly, cfg)
    assert len(res.point) == cfg.horizon
    assert res.seasonal_used is True
    assert set(res.intervals) == {80, 95}
    lo95, hi95 = res.intervals[95]
    assert (lo95.values <= res.point.values).all()
    assert (res.point.values <= hi95.values).all()
    # Intervals widen with the horizon.
    width = (hi95 - lo95).values
    assert width[-1] > width[0]


def test_insufficient_data_raises(cfg):
    short = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-31", periods=3, freq="ME"))
    with pytest.raises(fc.InsufficientDataError):
        fc.forecast_with_intervals(short, cfg)


def test_non_seasonal_fallback_below_24_months(cfg):
    idx = pd.date_range("2023-01-31", periods=12, freq="ME")
    s = pd.Series(np.linspace(10, 20, 12), index=idx)
    res = fc.forecast_with_intervals(s, cfg)
    assert res.seasonal_used is False
    assert len(res.point) == cfg.horizon


def test_baselines_shapes(monthly, cfg):
    for fn in (fc.naive_forecast, fc.drift_forecast):
        out = fn(monthly, cfg.horizon)
        assert len(out) == cfg.horizon
    sn = fc.seasonal_naive_forecast(monthly, cfg.horizon, 12)
    assert len(sn) == cfg.horizon
    # naive repeats the last value
    assert np.allclose(fc.naive_forecast(monthly, 5).values, monthly.iloc[-1])


def test_metrics_basic():
    y = np.array([10.0, 12.0, 11.0])
    p = np.array([10.0, 12.0, 11.0])
    assert fc.mae(y, p) == 0
    assert fc.rmse(y, p) == 0
    assert fc.mape(y, p) == 0
    # directional accuracy: perfect prediction matches all directions
    assert fc.directional_accuracy(y, p, anchor=9.0) == 1.0


def test_mase_below_one_when_better_than_naive():
    train = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    y = np.array([7.0, 8.0])
    good = np.array([7.0, 8.0])  # perfect
    assert fc.mase(y, good, train, m=1) == 0.0


def test_backtest_runs_all_models(monthly, cfg):
    bt = fc.backtest(monthly, cfg)
    assert set(bt) == {"holt_winters", "naive", "seasonal_naive", "drift"}
    for metrics in bt.values():
        assert metrics["folds"] >= 1
        assert "mase" in metrics and "directional" in metrics


def test_log_space_keeps_bands_positive_for_cheap_volatile_series(cfg):
    # A sub-$5, highly volatile name where additive-on-level bands could go negative.
    idx = pd.date_range("2014-01-31", periods=48, freq="ME")
    rng = np.random.default_rng(7)
    prices = 3.0 * np.exp(np.cumsum(rng.normal(0, 0.25, 48)))
    series = pd.Series(prices, index=idx)
    res = fc.forecast_with_intervals(series, cfg)
    assert (res.point > 0).all()
    lo80, hi80 = res.intervals[80]
    lo95, hi95 = res.intervals[95]
    assert (lo95 > 0).all()  # log space -> strictly positive lower bound
    assert (lo95.values <= lo80.values).all() and (hi80.values <= hi95.values).all()
    assert (res.point.values >= lo80.values).all() and (res.point.values <= hi80.values).all()


def test_backtest_reports_interval_coverage(monthly, cfg):
    summary = fc.backtest(monthly, cfg)
    hw = summary["holt_winters"]
    assert "coverage80" in hw and "coverage95" in hw
    for key in ("coverage80", "coverage95"):
        v = hw[key]
        assert v != v or 0.0 <= v <= 1.0  # NaN allowed; otherwise a valid fraction


def test_interval_coverage_fraction():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    lo = np.zeros(4)
    assert fc.interval_coverage(y, lo, np.full(4, 5.0)) == 1.0
    assert fc.interval_coverage(y, lo, np.full(4, 0.5)) == 0.0
    # Covers points 1, 3, 4 but not 2 -> 0.75.
    assert fc.interval_coverage(y, lo, np.array([1.5, 1.5, 5.0, 5.0])) == 0.75
