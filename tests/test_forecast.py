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


def test_backtest_reports_actual_successful_and_failed_folds(monthly, cfg):
    def intermittent(train, horizon):
        if len(train) != len(monthly) - cfg.backtest_horizon:
            raise ValueError("cannot fit this fold")
        return fc.naive_forecast(train, horizon)

    def broken(_train, _horizon):
        raise ValueError("cannot fit any fold")

    summary = fc.backtest(monthly, cfg, models={"intermittent": intermittent, "broken": broken})
    assert summary["intermittent"]["folds"] == 1
    assert summary["intermittent"]["failed_folds"] == cfg.backtest_folds - 1
    assert summary["intermittent"]["attempted_folds"] == cfg.backtest_folds
    assert summary["broken"]["folds"] == 0
    assert summary["broken"]["failed_folds"] == cfg.backtest_folds
    assert np.isnan(summary["broken"]["mase"])


@pytest.mark.parametrize("bad_values", [[np.nan] * 3, [np.inf] * 3, [1.0] * 2])
def test_invalid_predictions_count_as_failed_folds(monthly, cfg, bad_values):
    summary = fc.backtest(monthly, cfg, models={"bad": lambda train, h: pd.Series(bad_values)})
    assert summary["bad"]["folds"] == 0
    assert summary["bad"]["failed_folds"] == cfg.backtest_folds


def test_backtest_reuses_fit_for_points_and_intervals(monthly, cfg, monkeypatch):
    calls = []
    real_fit = fc._fit_holt_winters

    def counted_fit(train, settings):
        calls.append(len(train))
        return real_fit(train, settings)

    monkeypatch.setattr(fc, "_fit_holt_winters", counted_fit)
    summary = fc.backtest(monthly, cfg)
    assert len(calls) == cfg.backtest_folds
    assert summary["holt_winters"]["folds"] == cfg.backtest_folds
    assert np.isfinite(summary["holt_winters"]["coverage95"])


def test_injected_model_is_not_replaced_based_on_name(monthly, cfg, monkeypatch):
    calls = []

    def injected(train, horizon):
        calls.append(len(train))
        return fc.naive_forecast(train, horizon)

    def unexpected_fit(*args, **kwargs):
        pytest.fail("an injected model must not trigger unrelated Holt-Winters fits")

    monkeypatch.setattr(fc, "forecast_with_intervals", unexpected_fit)
    summary = fc.backtest(monthly, cfg, models={"holt_winters": injected})
    assert len(calls) == cfg.backtest_folds
    assert "coverage95" not in summary["holt_winters"]


def test_nonfinite_simulations_are_unavailable_intervals(monthly, cfg, monkeypatch):
    class Fit:
        def forecast(self, horizon):
            return pd.Series([100.0] * horizon)

        def simulate(self, nsimulations, repetitions, **kwargs):
            return np.full((nsimulations, repetitions), np.nan)

    monkeypatch.setattr(fc, "_fit_holt_winters", lambda *args: (Fit(), False, False))
    result = fc.forecast_with_intervals(monthly, cfg)
    assert np.isfinite(result.point).all()
    assert result.intervals == {}


def test_nonfinite_point_forecast_is_rejected(monthly, cfg, monkeypatch):
    class Fit:
        def forecast(self, horizon):
            return pd.Series([np.nan] * horizon)

    monkeypatch.setattr(fc, "_fit_holt_winters", lambda *args: (Fit(), False, False))
    with pytest.raises(ValueError, match="finite forecast"):
        fc.forecast_with_intervals(monthly, cfg)


@pytest.mark.parametrize("entry_point", [fc.forecast_with_intervals, fc.backtest])
@pytest.mark.parametrize(
    "invalid_history", ["gap", "reversed", "duplicate", "month_start", "nan", "infinity", "zero"]
)
def test_direct_monthly_apis_reject_invalid_history(
    monthly, cfg, monkeypatch, entry_point, invalid_history
):
    monthly = monthly.copy()
    if invalid_history == "gap":
        monthly = monthly.drop(monthly.index[20])
    elif invalid_history == "reversed":
        monthly = monthly.iloc[::-1]
    elif invalid_history == "duplicate":
        monthly.index = monthly.index[:1].append(monthly.index[:-1])
    elif invalid_history == "month_start":
        monthly.index = pd.date_range("2014-01-01", periods=len(monthly), freq="MS")
    else:
        monthly.iloc[20] = {"nan": np.nan, "infinity": np.inf, "zero": 0.0}[invalid_history]

    def unexpected_fit(*args, **kwargs):
        pytest.fail("invalid monthly input must be rejected before fitting")

    monkeypatch.setattr(fc, "_fit_holt_winters", unexpected_fit)
    with pytest.raises(ValueError, match="monthly prices"):
        entry_point(monthly, cfg)


def test_backtest_rejects_predictions_for_the_wrong_months(monthly, cfg):
    def wrong_dates(train, horizon):
        prediction = fc.naive_forecast(train, horizon)
        prediction.index = prediction.index + pd.offsets.MonthEnd()
        return prediction

    summary = fc.backtest(
        monthly, cfg, models={"misaligned": wrong_dates, "aligned": fc.naive_forecast}
    )
    assert summary["misaligned"]["folds"] == 0
    assert summary["misaligned"]["failed_folds"] == cfg.backtest_folds
    assert np.isnan(summary["misaligned"]["mae"])
    assert summary["aligned"]["folds"] == cfg.backtest_folds
