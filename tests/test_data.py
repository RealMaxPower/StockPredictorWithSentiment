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
