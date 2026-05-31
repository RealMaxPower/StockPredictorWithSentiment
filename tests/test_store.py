"""Tests for the SQLite store: price caching and run history."""

from __future__ import annotations

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
