"""End-to-end pipeline tests with fully mocked network clients."""

from __future__ import annotations

import json
import os

from stockpredictor import pipeline


def test_run_ticker_without_news(cfg, fake_downloader):
    res = pipeline.run_ticker("NVDA", cfg, price_downloader=fake_downloader, news_client=None)
    assert len(res.forecast.point) == cfg.horizon
    assert res.sentiment.has_news is False
    # No news -> adjusted equals raw forecast.
    assert (res.adjusted.values == res.forecast.point.values).all()


def test_run_ticker_with_news_scores_and_tilts(cfg, fake_downloader, fake_news_client):
    res = pipeline.run_ticker(
        "NVDA", cfg, price_downloader=fake_downloader, news_client=fake_news_client()
    )
    assert res.sentiment.has_news is True
    assert all("sentiment" in a for a in res.articles)
    assert set(res.backtest) == {"holt_winters", "naive", "seasonal_naive", "drift"}


def test_persist_outputs_writes_files(cfg, fake_downloader, fake_news_client, tmp_path):
    res = pipeline.run_ticker(
        "NVDA", cfg, price_downloader=fake_downloader, news_client=fake_news_client()
    )
    paths = pipeline.persist_outputs(res, str(tmp_path), cfg)
    assert os.path.exists(paths["news"])
    assert os.path.exists(paths["metrics"])
    assert os.path.getsize(paths["plot"]) > 0
    payload = json.loads(open(paths["metrics"]).read())
    assert set(payload["intervals"]) == {"80", "95"}
    assert "holt_winters" in payload["backtest"]
