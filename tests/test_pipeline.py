"""End-to-end pipeline tests with fully mocked network clients."""

from __future__ import annotations

import json
import os
from dataclasses import replace

import numpy as np
import pandas as pd

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


def test_run_ticker_records_which_scorer_ran(cfg, fake_downloader, fake_news_client):
    with_news = pipeline.run_ticker(
        "NVDA", cfg, price_downloader=fake_downloader, news_client=fake_news_client()
    )
    assert with_news.sentiment_model == "vader"

    no_news = pipeline.run_ticker("NVDA", cfg, price_downloader=fake_downloader)
    assert no_news.sentiment_model is None  # nothing was scored

    class Anonymous:
        def score(self, text: str) -> float:
            return 0.0

    injected = pipeline.run_ticker(
        "NVDA",
        cfg,
        price_downloader=fake_downloader,
        news_client=fake_news_client(),
        scorer=Anonymous(),
    )
    assert injected.sentiment_model is None  # unknown, so not guessed from cfg


def test_short_series_metrics_are_strict_json(cfg):
    cfg = replace(cfg, start="2020-01-01", end="2020-07-01")
    frame = pd.DataFrame(
        {"Close": np.arange(100.0, 106.0)}, index=pd.date_range("2020-01-31", periods=6, freq="ME")
    )
    result = pipeline.run_ticker("TEST", cfg, price_downloader=lambda *a, **kw: frame)
    payload = pipeline.metrics_payload(result)
    json.dumps(payload, allow_nan=False)
    assert payload["backtest"]["holt_winters"]["mase"] is None
    assert payload["configuration"]["end"] == cfg.end
    assert payload["data_fingerprint"]
    assert payload["code_version"].startswith("sha256:")
