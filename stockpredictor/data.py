"""
Price data: fetching (yfinance, injectable), split/dividend-safe adjusted close,
validation, and monthly resampling.

Using the *adjusted* close is critical: the old code used the raw ``Close``, so any
stock split (e.g. NVDA's 10:1 in 2024) showed up as a ~90% one-day crash that
poisoned the Holt-Winters trend/seasonal fit.
"""

from __future__ import annotations

import logging
from typing import Callable

import pandas as pd

from .sanitize import scrub

logger = logging.getLogger("stockpredictor.data")

# Default downloader is yfinance; injected in tests.
Downloader = Callable[..., pd.DataFrame]

# A single-month move beyond this is flagged as a suspected unadjusted action.
_SUSPECT_MONTHLY_MOVE = 0.40


def _default_downloader(*args, **kwargs) -> pd.DataFrame:
    import yfinance as yf

    return yf.download(*args, **kwargs)


def fetch_prices(
    ticker: str,
    start: str,
    end: str,
    downloader: Downloader = _default_downloader,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Download OHLCV for ``ticker``. ``auto_adjust=True`` corrects splits/dividends."""
    df = downloader(ticker, start=start, end=end, progress=False, auto_adjust=auto_adjust)
    if df is None or len(df) == 0:
        raise ValueError(f"No data fetched for ticker '{ticker}' ({start}..{end})")
    return df


def _extract_close(df: pd.DataFrame, ticker: str) -> pd.Series:
    """Pull a 1-D close series, tolerating yfinance's MultiIndex columns."""
    cols = df.columns
    if isinstance(cols, pd.MultiIndex):
        # Prefer adjusted close if present, else close.
        level0 = cols.get_level_values(0)
        field = "Adj Close" if "Adj Close" in level0 else "Close"
        sub = df[field]
        if isinstance(sub, pd.DataFrame):
            return sub[ticker] if ticker in sub.columns else sub.iloc[:, 0]
        return sub
    field = "Adj Close" if "Adj Close" in cols else "Close"
    return df[field]


def validate_close(close: pd.Series) -> tuple[pd.Series, list[str]]:
    """Drop NaNs and non-positive prices; warn on suspected unadjusted actions."""
    warnings_out: list[str] = []
    clean = close.dropna()
    n_dropped = len(close) - len(clean)
    if n_dropped:
        warnings_out.append(f"dropped {n_dropped} NaN price rows")
    nonpos = (clean <= 0).sum()
    if nonpos:
        warnings_out.append(f"dropped {int(nonpos)} non-positive prices")
        clean = clean[clean > 0]
    return clean, warnings_out


def to_monthly(df: pd.DataFrame, ticker: str, agg: str = "last") -> tuple[pd.Series, list[str]]:
    """
    Validated monthly series from a daily OHLCV frame, plus any data-quality
    warnings (suspected splits, dropped rows, sparse months).

    ``agg`` controls month-end aggregation. The default ``"last"`` keeps the
    month-end close — the value a point-in-time forecast can actually be compared
    against. ``"mean"`` averages within the month, which low-pass-filters the
    series and flatters every skill metric (especially directional accuracy); it
    is offered only for diagnostics.
    """
    if agg not in ("last", "mean"):
        raise ValueError(f"monthly agg must be 'last' or 'mean', got {agg!r}")
    close, warns = validate_close(_extract_close(df, ticker))
    resampled = close.resample("ME")
    monthly = (resampled.last() if agg == "last" else resampled.mean()).dropna()

    # Flag suspected unadjusted splits/dividends on the daily series.
    daily_ret = close.pct_change().abs()
    suspect = daily_ret[daily_ret > _SUSPECT_MONTHLY_MOVE]
    if len(suspect):
        warns.append(
            f"{len(suspect)} day(s) move > {_SUSPECT_MONTHLY_MOVE:.0%} — "
            "possible unadjusted split/dividend"
        )
    log_ticker = scrub(ticker)
    for w in warns:
        logger.warning("%s: %s", log_ticker, w)
    return monthly, warns
