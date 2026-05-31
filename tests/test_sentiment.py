"""Tests for sentiment scoring, aggregation, and the bounded forecast tilt."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stockpredictor import config, sentiment


class FixedScorer:
    """Deterministic scorer mapping a few phrases to fixed scores."""

    def score(self, text: str) -> float:
        if not text:
            return 0.0
        if "good" in text:
            return 0.8
        if "bad" in text:
            return -0.8
        return 0.0


def test_aggregate_empty_is_no_news_not_neutral():
    res = sentiment.aggregate_sentiment([])
    assert res.has_news is False
    assert res.n_articles == 0
    assert res.confidence == 0.0
    assert res.label() == "no news"


def test_aggregate_strong_agreement_high_confidence():
    res = sentiment.aggregate_sentiment([0.8, 0.7, 0.9, 0.6, 0.75, 0.8])
    assert res.mean > 0.6
    assert res.confidence > 0.5
    assert res.label() == "positive"


def test_aggregate_conflicting_articles_low_confidence():
    res = sentiment.aggregate_sentiment([0.9, -0.9, 0.8, -0.8])
    assert abs(res.mean) < 0.1
    assert res.confidence < 0.2  # high dispersion kills confidence
    assert res.effective == res.mean * res.confidence


def test_score_articles_handles_missing_fields():
    arts = [{"title": "good news"}, {"description": None, "title": None}]
    scores = sentiment.score_articles(arts, FixedScorer())
    assert scores == [0.8, 0.0]


def test_tilt_is_bounded_and_decays():
    cfg = config.AppConfig(sentiment_max_adj=0.05, sentiment_k=0.02, sentiment_decay_tau=2.5)
    forecast = pd.Series([100.0] * 12, index=pd.date_range("2025-01-31", periods=12, freq="ME"))
    strong = sentiment.aggregate_sentiment([1.0] * 8)  # max confidence, max mean
    tilted = sentiment.apply_sentiment_tilt(forecast, strong, cfg)
    month1_pct = tilted.iloc[0] / 100 - 1
    month12_pct = tilted.iloc[-1] / 100 - 1
    assert 0 < month1_pct <= cfg.sentiment_max_adj + 1e-9  # capped
    assert month12_pct < month1_pct  # decays over horizon


def test_tilt_no_news_returns_unchanged():
    cfg = config.AppConfig()
    forecast = pd.Series([100.0] * 12, index=pd.date_range("2025-01-31", periods=12, freq="ME"))
    out = sentiment.apply_sentiment_tilt(forecast, sentiment.aggregate_sentiment([]), cfg)
    assert np.allclose(out.values, forecast.values)


def test_tilt_disabled_returns_unchanged():
    cfg = config.AppConfig(sentiment_enabled=False)
    forecast = pd.Series([100.0] * 12, index=pd.date_range("2025-01-31", periods=12, freq="ME"))
    strong = sentiment.aggregate_sentiment([0.9] * 6)
    out = sentiment.apply_sentiment_tilt(forecast, strong, cfg)
    assert np.allclose(out.values, forecast.values)
