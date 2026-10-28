"""
Price data: fetching (yfinance, injectable), split/dividend-safe adjusted close,
validation, and monthly resampling.

Using the *adjusted* close is critical: the old code used the raw ``Close``, so any
stock split (e.g. NVDA's 10:1 in 2024) showed up as a ~90% one-day crash that
poisoned the Holt-Winters trend/seasonal fit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np
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
    """Drop missing, infinite, and non-positive prices before fitting in log space."""
    warnings_out: list[str] = []
    clean = close.dropna()
    n_dropped = len(close) - len(clean)
    if n_dropped:
        warnings_out.append(f"dropped {n_dropped} NaN price rows")
    nonfinite = ~np.isfinite(clean)
    if nonfinite.any():
        warnings_out.append(f"dropped {int(nonfinite.sum())} non-finite price rows")
        clean = clean[~nonfinite]
    nonpos = (clean <= 0).sum()
    if nonpos:
        warnings_out.append(f"dropped {int(nonpos)} non-positive prices")
        clean = clean[clean > 0]
    return clean, warnings_out


def validate_monthly(monthly: pd.Series) -> None:
    """Require a finite positive price on each consecutive calendar month-end.

    Public forecast/simulation callers can supply a monthly series directly,
    bypassing daily-data conversion. Never silently sort or fill those inputs:
    their temporal ordering determines what was known at each forecast origin.
    """
    if monthly.empty:
        raise ValueError("monthly prices must not be empty")
    prices = monthly.to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("monthly prices must be finite and positive")
    dates = monthly.index
    if not isinstance(dates, pd.DatetimeIndex) or dates.hasnans:
        raise ValueError("monthly prices require a DatetimeIndex without missing dates")
    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("monthly prices require sorted unique dates")
    expected = pd.date_range(dates[0].normalize(), periods=len(monthly), freq="ME")
    if not dates.equals(expected):
        raise ValueError("monthly prices require consecutive month-end dates")


def to_monthly(
    df: pd.DataFrame, ticker: str, agg: str = "last", *, end: str | None = None
) -> tuple[pd.Series, list[str]]:
    """
    Validated monthly series from a daily OHLCV frame, plus any data-quality
    warnings (suspected splits, dropped rows, incomplete trailing months).

    ``end`` is the exclusive daily-data boundary, matching yfinance. A month is
    complete only after its calendar end: request the first day of the next month
    to include all of it, including when its final trading day is a Friday or a
    holiday. Without ``end``, completeness is conservatively inferred from the
    day after the final supplied observation. Missing interior months are errors;
    dropping them would turn multi-month returns into single-month returns.

    ``agg`` controls month-end aggregation. The default ``"last"`` keeps the
    month-end close — the value a point-in-time forecast can actually be compared
    against. ``"mean"`` averages within the month, which low-pass-filters the
    series and flatters every skill metric (especially directional accuracy); it
    is offered only for diagnostics.
    """
    if agg not in ("last", "mean"):
        raise ValueError(f"monthly agg must be 'last' or 'mean', got {agg!r}")
    if df.empty:
        raise ValueError("daily prices must not be empty")
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.hasnans:
        raise ValueError("prices must have a DatetimeIndex without missing dates")
    if df.index.has_duplicates:
        raise ValueError("prices contain duplicate dates")
    df = df.sort_index()
    # Daily timestamps denote exchange-local calendar dates, not UTC instants.
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    boundary = pd.Timestamp(end) if end else df.index.max().normalize() + pd.Timedelta(days=1)
    df = df.loc[df.index < boundary]
    close, warns = validate_close(_extract_close(df, ticker))
    if close.empty:
        raise ValueError("no finite positive prices before the exclusive end date")
    resampled = close.resample("ME")
    monthly = resampled.last() if agg == "last" else resampled.mean()
    incomplete = monthly.index >= boundary
    if incomplete.any():
        labels = ", ".join(monthly.index[incomplete].strftime("%Y-%m"))
        warns.append(f"excluded incomplete month(s): {labels}")
        monthly = monthly.loc[~incomplete]
    if not monthly.empty:
        # A truncated download may omit complete months at the end as well.
        final_complete = boundary.normalize() - pd.offsets.MonthEnd()
        monthly = monthly.reindex(pd.date_range(monthly.index[0], final_complete, freq="ME"))
    missing = monthly.index[monthly.isna()]
    if len(missing):
        labels = ", ".join(missing.strftime("%Y-%m"))
        raise ValueError(f"missing monthly prices for {labels}; cannot compress calendar time")

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
