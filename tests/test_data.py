"""Tests for price extraction, validation, and monthly resampling."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockpredictor import data


def test_fetch_prices_empty_raises():
    with pytest.raises(ValueError):
        data.fetch_prices(
            "AAPL", "2020-01-01", "2020-02-01", downloader=lambda *a, **k: pd.DataFrame()
        )


def test_extract_close_multiindex():
    days = pd.date_range("2020-01-01", periods=5, freq="D")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], ["AAPL"]])
    df = pd.DataFrame(np.arange(10.0).reshape(5, 2), index=days, columns=cols)
    s = data._extract_close(df, "AAPL")
    assert isinstance(s, pd.Series)
    assert len(s) == 5


def test_validate_close_drops_nan_and_nonpositive():
    s = pd.Series([10.0, np.nan, -5.0, 12.0])
    clean, warns = data.validate_close(s)
    assert list(clean) == [10.0, 12.0]
    assert len(warns) == 2


def test_to_monthly_resamples_and_flags_split():
    days = pd.bdate_range("2020-01-01", "2021-12-31")
    vals = np.linspace(100, 120, len(days))
    vals[200] = vals[200] * 0.4  # fake 60% one-day drop (suspected split)
    df = pd.DataFrame({"Close": vals}, index=days)
    monthly, warns = data.to_monthly(df, "TST")
    assert monthly.index.freqstr in ("ME", "M")
    assert any("split" in w for w in warns)
    assert len(monthly) == 24


def test_to_monthly_last_uses_month_end_close():
    days = pd.date_range("2020-01-01", "2020-03-31", freq="D")
    s = pd.Series(np.arange(1.0, len(days) + 1), index=days)
    df = pd.DataFrame({"Close": s})
    monthly, _ = data.to_monthly(df, "TST")  # default agg="last"
    assert monthly.iloc[0] == s.loc["2020-01-31"]
    assert monthly.iloc[1] == s.loc["2020-02-29"]


def test_to_monthly_mean_smooths_below_last_for_rising_series():
    days = pd.date_range("2020-01-01", "2020-03-31", freq="D")
    s = pd.Series(np.arange(1.0, len(days) + 1), index=days)
    df = pd.DataFrame({"Close": s})
    last, _ = data.to_monthly(df, "TST", agg="last")
    mean, _ = data.to_monthly(df, "TST", agg="mean")
    # A monotonically rising series has month-end close above its within-month mean.
    assert (last > mean).all()


def test_to_monthly_invalid_agg_raises():
    df = pd.DataFrame({"Close": [1.0, 2.0]}, index=pd.date_range("2020-01-01", periods=2))
    with pytest.raises(ValueError):
        data.to_monthly(df, "TST", agg="median")
