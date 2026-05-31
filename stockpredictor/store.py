"""
Optional SQLite store (stdlib ``sqlite3``, zero infra): a read-through price cache
plus run history. Persisting each run — and keeping article ``publishedAt`` — lets
runs be reproducible, quota-friendly, and (over time) accumulates the aligned
(sentiment → forward return) panel needed to one day *learn* the sentiment tilt.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd

logger = logging.getLogger("stockpredictor.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
    fetched_at TEXT, PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT, run_date TEXT, start TEXT, "end" TEXT,
    horizon INTEGER, seasonal_used INTEGER,
    sentiment_mean REAL, sentiment_effective REAL, sentiment_n INTEGER,
    sentiment_label TEXT, forecast_json TEXT, backtest_json TEXT
);
CREATE TABLE IF NOT EXISTS articles (
    run_id INTEGER, ticker TEXT, url TEXT, title TEXT, source TEXT,
    published_at TEXT, sentiment REAL
);
"""


class Store:
    """Thin wrapper over a SQLite connection."""

    def __init__(self, path: str = "stockpredictor.db") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- price cache ---------------------------------------------------------
    def upsert_prices(self, ticker: str, df: pd.DataFrame) -> None:
        fetched = datetime.now().isoformat(timespec="seconds")
        n = len(df)
        level0 = (
            df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
        )

        def column(name: str) -> list:
            """Per-row list of python floats (or None) for an OHLCV column."""
            if name not in level0:
                return [None] * n
            series = df[name].iloc[:, 0] if isinstance(df.columns, pd.MultiIndex) else df[name]
            return [None if pd.isna(x) else float(x) for x in series]

        if "Close" not in level0:
            return
        dates = [pd.Timestamp(i).strftime("%Y-%m-%d") for i in df.index]
        rows = list(
            zip(
                [ticker] * n,
                dates,
                column("Open"),
                column("High"),
                column("Low"),
                column("Close"),
                column("Volume"),
                [fetched] * n,
            )
        )
        self.conn.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?,?)", rows)
        self.conn.commit()

    def cached_prices(
        self, ticker: str, start: str, end: str, ttl_days: int = 1
    ) -> pd.DataFrame | None:
        cur = self.conn.execute(
            "SELECT * FROM prices WHERE ticker=? AND date BETWEEN ? AND ? ORDER BY date",
            (ticker, start, end),
        )
        rows = cur.fetchall()
        if not rows:
            return None
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        immutable = end_dt < (date.today() - timedelta(days=7))
        if not immutable:
            newest = max(datetime.fromisoformat(r["fetched_at"]) for r in rows)
            if datetime.now() - newest > timedelta(days=ttl_days):
                return None  # stale near-today data; refetch
        idx = pd.to_datetime([r["date"] for r in rows])
        data = {
            "Open": [r["open"] for r in rows],
            "High": [r["high"] for r in rows],
            "Low": [r["low"] for r in rows],
            "Close": [r["close"] for r in rows],
            "Volume": [r["volume"] for r in rows],
        }
        logger.info("%s: price cache hit (%d rows)", ticker, len(rows))
        return pd.DataFrame(data, index=idx)

    # --- run history ---------------------------------------------------------
    def save_run(self, result, run_date: str, cfg) -> int:
        from .pipeline import metrics_payload

        payload = metrics_payload(result)
        cur = self.conn.execute(
            'INSERT INTO runs (ticker, run_date, start, "end", horizon, seasonal_used, '
            "sentiment_mean, sentiment_effective, sentiment_n, sentiment_label, "
            "forecast_json, backtest_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                result.ticker,
                run_date,
                cfg.start,
                cfg.end,
                cfg.horizon,
                int(result.forecast.seasonal_used),
                result.sentiment.mean,
                result.sentiment.effective,
                result.sentiment.n_articles,
                result.sentiment.label(),
                json.dumps(
                    {k: payload[k] for k in ("forecast", "adjusted", "intervals", "horizon_index")}
                ),
                json.dumps(result.backtest),
            ),
        )
        run_id = int(cur.lastrowid or 0)
        self.conn.executemany(
            "INSERT INTO articles VALUES (?,?,?,?,?,?,?)",
            [
                (
                    run_id,
                    result.ticker,
                    a.get("url"),
                    a.get("title"),
                    a.get("source"),
                    a.get("publishedAt"),
                    a.get("sentiment"),
                )
                for a in result.articles
            ],
        )
        self.conn.commit()
        return run_id

    def history(self, ticker: str) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT run_date, sentiment_label, sentiment_mean, sentiment_effective, "
            "sentiment_n, seasonal_used FROM runs WHERE ticker=? ORDER BY run_date",
            self.conn,
            params=(ticker.upper(),),
        )


def make_cached_downloader(store: Store, base_downloader, ttl_days: int = 1):
    """Wrap a downloader so prices are served from SQLite when fresh enough."""

    def _dl(ticker, start=None, end=None, progress=False, auto_adjust=True):
        cached = store.cached_prices(ticker, start, end, ttl_days=ttl_days)
        if cached is not None and len(cached):
            return cached
        df = base_downloader(
            ticker, start=start, end=end, progress=progress, auto_adjust=auto_adjust
        )
        try:
            store.upsert_prices(ticker, df)
        except Exception as exc:  # noqa: BLE001 - caching must never break a run
            logger.warning("%s: could not cache prices: %s", ticker, exc)
        return df

    return _dl
