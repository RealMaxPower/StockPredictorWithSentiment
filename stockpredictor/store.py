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
from dataclasses import asdict
from datetime import datetime, timedelta

import pandas as pd

from .sanitize import scrub
from .serialization import json_safe

logger = logging.getLogger("stockpredictor.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
    fetched_at TEXT, PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS price_snapshots (
    ticker TEXT, start TEXT, "end" TEXT, auto_adjust INTEGER,
    fetched_at TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (ticker, start, "end", auto_adjust)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT, run_date TEXT, start TEXT, "end" TEXT,
    horizon INTEGER, seasonal_used INTEGER,
    sentiment_mean REAL, sentiment_effective REAL, sentiment_n INTEGER,
    sentiment_label TEXT, forecast_json TEXT, backtest_json TEXT,
    sentiment_model TEXT
);
CREATE TABLE IF NOT EXISTS articles (
    run_id INTEGER, ticker TEXT, url TEXT, title TEXT, source TEXT,
    published_at TEXT, sentiment REAL
);
CREATE TABLE IF NOT EXISTS simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT, run_date TEXT, variant_id TEXT, sizing_method TEXT,
    rf_annual REAL, beat_bh INTEGER, beat_rf INTEGER,
    excess_cagr_vs_bh REAL, excess_sharpe_vs_bh REAL, strategy_cagr REAL,
    max_drawdown REAL, turnover_annual REAL, scorecard_json TEXT
);
"""


class Store:
    """Thin wrapper over a SQLite connection."""

    def __init__(self, path: str = "stockpredictor.db") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a database was created (additive only)."""
        cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(runs)")}
        if "sentiment_model" not in cols:
            # Pre-existing rows stay NULL: which scorer produced them is unknown.
            self.conn.execute("ALTER TABLE runs ADD COLUMN sentiment_model TEXT")
        sim_cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(simulations)")}
        for name in ("configuration_json", "start", "end", "data_fingerprint", "code_version"):
            if name not in sim_cols:
                self.conn.execute(f'ALTER TABLE simulations ADD COLUMN "{name}" TEXT')

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- price cache ---------------------------------------------------------
    def upsert_prices(
        self,
        ticker: str,
        df: pd.DataFrame,
        *,
        start: str | None = None,
        end: str | None = None,
        auto_adjust: bool = True,
    ) -> None:
        """Store one complete download, never merging different adjustment vintages.

        Coverage comes from the requested interval, not the first/last trading day
        (weekends, holidays and IPOs make those misleading). Old row-only caches
        cannot establish coverage and are deliberately not used as cache hits.
        """
        if start is None or end is None or df is None or df.empty:
            return
        fetched = datetime.now().isoformat(timespec="microseconds")
        # Do not promise coverage of future days that have not been downloaded.
        covered_end = min(end, datetime.now().date().isoformat())
        if covered_end <= start:
            return
        payload = {
            "columns": df.columns.tolist(),
            "column_names": list(df.columns.names),
            "multiindex": isinstance(df.columns, pd.MultiIndex),
            "index": [pd.Timestamp(i).isoformat() for i in df.index],
            "index_name": df.index.name,
            "index_tz": str(df.index.tz) if df.index.tz is not None else None,
            "data": df.to_dict(orient="split")["data"],
        }
        self.conn.execute(
            "INSERT OR REPLACE INTO price_snapshots VALUES (?,?,?,?,?,?)",
            (
                ticker.upper(),
                start,
                covered_end,
                int(auto_adjust),
                fetched,
                json.dumps(json_safe(payload), allow_nan=False),
            ),
        )
        self.conn.commit()

    def cached_prices(
        self, ticker: str, start: str, end: str, ttl_days: int = 1, *, auto_adjust: bool = True
    ) -> pd.DataFrame | None:
        """Return a fresh, fully covering snapshot sliced to ``[start, end)``.

        All snapshots expire, including historical prices: later corporate actions
        can revise adjusted history. Expanded ranges are downloaded together rather
        than spliced to older cached prices.
        """
        cur = self.conn.execute(
            'SELECT * FROM price_snapshots WHERE ticker=? AND start<=? AND "end">=? '
            "AND auto_adjust=? ORDER BY fetched_at DESC",
            (ticker.upper(), start, end, int(auto_adjust)),
        )
        snapshot = cur.fetchone()
        if snapshot is None:
            return None
        if datetime.now() - datetime.fromisoformat(snapshot["fetched_at"]) > timedelta(
            days=ttl_days
        ):
            return None
        payload = json.loads(snapshot["payload"])
        columns = (
            pd.MultiIndex.from_tuples(payload["columns"], names=payload["column_names"])
            if payload["multiindex"]
            else pd.Index(payload["columns"], name=payload["column_names"][0])
        )
        idx = (
            pd.to_datetime(payload["index"], utc=True).tz_convert(payload["index_tz"])
            if payload.get("index_tz")
            else pd.DatetimeIndex(payload["index"])
        )
        idx.name = payload["index_name"]
        frame = pd.DataFrame(payload["data"], columns=columns, index=idx)
        # Compare exchange-local dates, also handling timezone-aware daily frames.
        dates = frame.index.strftime("%Y-%m-%d")
        frame = frame.loc[(dates >= start) & (dates < end)]
        logger.info("%s: price cache hit (%d rows)", scrub(ticker), len(frame))
        return frame

    # --- run history ---------------------------------------------------------
    def save_run(self, result, run_date: str, cfg) -> int:
        from .pipeline import metrics_payload

        payload = metrics_payload(result)
        cur = self.conn.execute(
            'INSERT INTO runs (ticker, run_date, start, "end", horizon, seasonal_used, '
            "sentiment_mean, sentiment_effective, sentiment_n, sentiment_label, "
            "forecast_json, backtest_json, sentiment_model) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    json_safe(
                        {
                            k: payload[k]
                            for k in ("forecast", "adjusted", "intervals", "horizon_index")
                        }
                    ),
                    allow_nan=False,
                ),
                json.dumps(json_safe(result.backtest), allow_nan=False),
                getattr(result, "sentiment_model", None),
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
            "sentiment_n, sentiment_model, seasonal_used FROM runs WHERE ticker=? "
            "ORDER BY run_date",
            self.conn,
            params=(ticker.upper(),),
        )

    # --- simulation history (multiple-testing accounting) --------------------
    def save_simulation(
        self,
        ticker: str,
        variant_id: str,
        scorecard,
        cfg,
        *,
        configuration: dict | None = None,
        data_fingerprint: str | None = None,
        code_version: str | None = None,
    ) -> int:
        """Log one paper-trading run so the best-of-N overfit warning can be honest.

        Every strategy/parameter variant tried accumulates a row here; ``count_
        simulations`` reads them back so the reporting layer can say how many were
        attempted (brief §3.5).
        """
        run_date = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute(
            "INSERT INTO simulations (ticker, run_date, variant_id, sizing_method, "
            "rf_annual, beat_bh, beat_rf, excess_cagr_vs_bh, excess_sharpe_vs_bh, "
            "strategy_cagr, max_drawdown, turnover_annual, scorecard_json, "
            'configuration_json, start, "end", data_fingerprint, code_version) '
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ticker.upper(),
                run_date,
                variant_id,
                cfg.sizing_method,
                cfg.rf_annual,
                int(scorecard.beat_buy_and_hold),
                int(scorecard.beat_risk_free),
                scorecard.excess_cagr_vs_bh,
                scorecard.excess_sharpe_vs_bh,
                scorecard.strategy.cagr,
                scorecard.max_drawdown,
                scorecard.turnover_annual,
                json.dumps(json_safe(scorecard.as_dict()), allow_nan=False),
                json.dumps(
                    json_safe(configuration if configuration is not None else asdict(cfg)),
                    sort_keys=True,
                    allow_nan=False,
                ),
                cfg.start,
                cfg.end,
                data_fingerprint,
                code_version,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def count_simulations(self, ticker: str) -> int:
        """Number of distinct experiment identities, not repeated executions."""
        cur = self.conn.execute(
            "SELECT COUNT(DISTINCT variant_id) AS n FROM simulations WHERE ticker=?",
            (ticker.upper(),),
        )
        row = cur.fetchone()
        return int(row["n"]) if row else 0

    def count_simulation_runs(self, ticker: str) -> int:
        """Number of executions, including repeated runs of the same variant."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM simulations WHERE ticker=?", (ticker.upper(),)
        ).fetchone()
        return int(row["n"])

    def simulation_history(self, ticker: str) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT run_date, variant_id, sizing_method, beat_bh, beat_rf, "
            "excess_cagr_vs_bh, strategy_cagr, max_drawdown, turnover_annual "
            "FROM simulations WHERE ticker=? ORDER BY run_date",
            self.conn,
            params=(ticker.upper(),),
        )


def make_cached_downloader(store: Store, base_downloader, ttl_days: int = 1):
    """Wrap a downloader so prices are served from SQLite when fresh enough."""

    def _dl(ticker, start=None, end=None, progress=False, auto_adjust=True):
        if start is not None and end is not None:
            try:
                cached = store.cached_prices(
                    ticker, start, end, ttl_days=ttl_days, auto_adjust=auto_adjust
                )
                if cached is not None and len(cached):
                    return cached
            except Exception as exc:  # noqa: BLE001 - cache failure must not block a download
                logger.warning("%s: could not read cached prices: %s", scrub(ticker), scrub(exc))
        df = base_downloader(
            ticker, start=start, end=end, progress=progress, auto_adjust=auto_adjust
        )
        try:
            store.upsert_prices(ticker, df, start=start, end=end, auto_adjust=auto_adjust)
        except Exception as exc:  # noqa: BLE001 - caching must never break a run
            logger.warning("%s: could not cache prices: %s", scrub(ticker), scrub(exc))
        return df

    return _dl
