"""Tests for the SQLite store: price caching and run history."""

from __future__ import annotations

import sqlite3

from stockpredictor import pipeline, store


def test_price_cache_round_trip(tmp_path, fake_downloader):
    db = str(tmp_path / "t.db")
    calls = {"n": 0}

    def counting(ticker, **kw):
        calls["n"] += 1
        return fake_downloader(ticker, **kw)

    with store.Store(db) as s:
        cached_dl = store.make_cached_downloader(s, counting, ttl_days=30)
        df1 = cached_dl("NVDA", start="2015-01-01", end="2020-01-01")
        df2 = cached_dl("NVDA", start="2015-01-01", end="2020-01-01")
        assert calls["n"] == 1  # second call served from cache
        assert "Close" in df1.columns and len(df2) > 0


def test_save_run_and_history(tmp_path, cfg, fake_downloader, fake_news_client):
    res = pipeline.run_ticker(
        "NVDA", cfg, price_downloader=fake_downloader, news_client=fake_news_client()
    )
    with store.Store(str(tmp_path / "h.db")) as s:
        run_id = s.save_run(res, run_date="2025-01-15", cfg=cfg)
        assert run_id >= 1
        hist = s.history("NVDA")
        assert len(hist) == 1
        assert hist.iloc[0]["sentiment_label"] == res.sentiment.label()


def test_save_run_records_sentiment_model(tmp_path, cfg, fake_downloader, fake_news_client):
    res = pipeline.run_ticker(
        "NVDA", cfg, price_downloader=fake_downloader, news_client=fake_news_client()
    )
    with store.Store(str(tmp_path / "m.db")) as s:
        s.save_run(res, run_date="2025-01-15", cfg=cfg)
        assert s.history("NVDA").iloc[0]["sentiment_model"] == "vader"


def test_existing_database_gains_sentiment_model_column(tmp_path):
    # A runs table as created before sentiment_model existed, with one row in it.
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, run_date TEXT, "
        'start TEXT, "end" TEXT, horizon INTEGER, seasonal_used INTEGER, '
        "sentiment_mean REAL, sentiment_effective REAL, sentiment_n INTEGER, "
        "sentiment_label TEXT, forecast_json TEXT, backtest_json TEXT)"
    )
    conn.execute("INSERT INTO runs (ticker, run_date) VALUES ('NVDA', '2025-01-01')")
    conn.commit()
    conn.close()

    with store.Store(db) as s:
        cols = {r["name"] for r in s.conn.execute("PRAGMA table_info(runs)")}
        assert "sentiment_model" in cols
        old = s.conn.execute("SELECT ticker, sentiment_model FROM runs").fetchone()
        assert old["ticker"] == "NVDA"  # existing row survives the migration
        assert old["sentiment_model"] is None  # and stays honestly unknown

    with store.Store(db):  # reopening an already-migrated database is a no-op
        pass
