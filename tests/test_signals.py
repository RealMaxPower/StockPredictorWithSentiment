"""Tests for signal extraction: μ from the point forecast, σ from the intervals."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockpredictor import signals
from stockpredictor.forecast import ForecastResult
from stockpredictor.sentiment import aggregate_sentiment
from stockpredictor.signals import Signal, signal_from_forecast


def _forecast(point0: float, lo80: float, hi80: float, lo95=None, hi95=None) -> ForecastResult:
    idx = pd.date_range("2025-01-31", periods=1, freq="ME")
    intervals = {80: (pd.Series([lo80], index=idx), pd.Series([hi80], index=idx))}
    if lo95 is not None:
        intervals[95] = (pd.Series([lo95], index=idx), pd.Series([hi95], index=idx))
    return ForecastResult(point=pd.Series([point0], index=idx), intervals=intervals)


def test_mu_is_horizon1_return():
    fc = _forecast(point0=110.0, lo80=105.0, hi80=115.0)
    sig = signal_from_forecast(fc, last_price=100.0)
    assert sig.expected_return == pytest.approx(0.10)  # 110/100 - 1


def test_sigma_from_80_band_uses_normal_z():
    # Half-width in price = (115-105)/2 = 5; σ_price = 5/1.2816; σ_ret = σ_price/100.
    fc = _forecast(point0=110.0, lo80=105.0, hi80=115.0)
    sig = signal_from_forecast(fc, last_price=100.0)
    expected = (5.0 / signals._Z80) / 100.0
    assert sig.uncertainty == pytest.approx(expected)


def test_sigma_falls_back_to_95_band_when_80_absent():
    idx = pd.date_range("2025-01-31", periods=1, freq="ME")
    fc = ForecastResult(
        point=pd.Series([110.0], index=idx),
        intervals={95: (pd.Series([100.0], index=idx), pd.Series([120.0], index=idx))},
    )
    sig = signal_from_forecast(fc, last_price=100.0)
    expected = (10.0 / signals._Z95) / 100.0  # half-width 10 over z95
    assert sig.uncertainty == pytest.approx(expected)


def test_sigma_floor_when_no_intervals():
    idx = pd.date_range("2025-01-31", periods=1, freq="ME")
    fc = ForecastResult(point=pd.Series([110.0], index=idx), intervals={})
    sig = signal_from_forecast(fc, last_price=100.0)
    assert sig.uncertainty == pytest.approx(signals._MIN_SIGMA)


def test_confidence_comes_from_sentiment_else_zero():
    fc = _forecast(point0=110.0, lo80=105.0, hi80=115.0)
    assert signal_from_forecast(fc, 100.0).confidence == 0.0  # no sentiment
    sent = aggregate_sentiment([0.3, 0.4, 0.35, 0.5])  # agreeing, positive
    sig = signal_from_forecast(fc, 100.0, sentiment=sent)
    assert sig.confidence == pytest.approx(sent.confidence)
    assert sig.confidence > 0.0


def test_signal_rejects_bad_values():
    ts = pd.Timestamp("2025-01-31")
    with pytest.raises(ValueError):
        Signal(expected_return=0.0, uncertainty=0.0, confidence=0.5, as_of=ts)
    with pytest.raises(ValueError):
        Signal(expected_return=0.0, uncertainty=0.1, confidence=1.5, as_of=ts)


def test_make_signal_fn_runs_real_forecast(monthly, cfg):
    sig_fn = signals.make_signal_fn(cfg)
    sig = sig_fn(monthly, cfg)
    assert isinstance(sig, Signal)
    assert sig.uncertainty > 0.0
    assert sig.as_of == monthly.index[-1]
    assert np.isfinite(sig.expected_return)
