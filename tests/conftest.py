"""Shared fixtures: synthetic data and fake network clients (no real I/O)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockpredictor import config


@pytest.fixture
def cfg() -> config.AppConfig:
    return config.AppConfig(start="2015-01-01", end="2024-12-31", page_size=3)


@pytest.fixture
def monthly() -> pd.Series:
    """120 months of trend + 12-month seasonality + mild noise."""
    idx = pd.date_range("2014-01-31", periods=120, freq="ME")
    rng = np.random.default_rng(0)
    trend = np.linspace(50, 150, 120)
    seasonal = 8 * np.sin(2 * np.pi * np.arange(120) / 12)
    return pd.Series(trend + seasonal + rng.normal(0, 3, 120), index=idx)


@pytest.fixture
def fake_downloader():
    def _dl(ticker, start=None, end=None, progress=False, auto_adjust=True):
        days = pd.bdate_range("2015-01-01", "2024-12-31")
        n = len(days)
        base = (
            np.linspace(40, 180, n)
            + 10 * np.sin(2 * np.pi * np.arange(n) / 252)
            + np.random.default_rng(1).normal(0, 1.5, n)
        )
        return pd.DataFrame(
            {"Open": base, "High": base * 1.01, "Low": base * 0.99, "Close": base, "Volume": 1e6},
            index=days,
        )

    return _dl


@pytest.fixture
def fake_news_client():
    class _Client:
        def __init__(self, responses=None):
            self.responses = responses or [
                {
                    "articles": [
                        {
                            "title": "Company beats earnings",
                            "description": "strong guidance",
                            "url": "u1",
                            "source": {"name": "Reuters"},
                            "publishedAt": "2024-12-20T00:00:00Z",
                        },
                        {
                            "title": "Analysts upgrade to buy",
                            "description": "positive outlook",
                            "url": "u2",
                            "source": {"name": "WSJ"},
                            "publishedAt": "2024-12-22T00:00:00Z",
                        },
                    ]
                }
            ]
            self.calls = []

        def get_everything(self, **kw):
            self.calls.append(kw)
            return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]

    return _Client
