"""
Sentiment scoring and integration.

Two responsibilities, kept separate from networking so they are pure and testable:

1. Scoring text → a signed score in [-1, 1] (VADER by default; FinBERT optional).
2. Aggregating per-article scores into a *structured* ``SentimentResult`` that
   distinguishes "no news" from "neutral" and carries a confidence estimate.

The forecast adjustment (``apply_sentiment_tilt``) is bounded and decays over the
horizon, replacing the old unbounded ``forecast * (1 + sentiment)``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from . import config

# Sample size at which we trust the mean fully; dispersion at which we stop.
_CONFIDENCE_FULL_N = 8
_CONFIDENCE_MAX_DISPERSION = 0.5  # ~ std of VADER compound across mixed headlines


class Scorer(Protocol):
    """Anything that turns a piece of text into a signed sentiment in [-1, 1]."""

    def score(self, text: str) -> float:  # pragma: no cover - protocol
        ...


class VaderScorer:
    """Default zero-dependency scorer wrapping vaderSentiment's analyzer."""

    def __init__(self, analyzer=None) -> None:
        if analyzer is None:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            analyzer = SentimentIntensityAnalyzer()
        self._analyzer = analyzer

    def score(self, text: str) -> float:
        if not text:
            return 0.0
        return float(self._analyzer.polarity_scores(text)["compound"])


class FinBertScorer:
    """
    Finance-tuned scorer. Lazy-imports transformers/torch so the dependency stays
    optional. Signed score = P(positive) - P(negative).
    """

    def __init__(self, model_name: str = "ProsusAI/finbert") -> None:
        from transformers import pipeline  # imported lazily on purpose

        self._pipe = pipeline("text-classification", model=model_name, top_k=None)

    def score(self, text: str) -> float:
        if not text:
            return 0.0
        scores = {d["label"].lower(): d["score"] for d in self._pipe(text[:512])[0]}
        return float(scores.get("positive", 0.0) - scores.get("negative", 0.0))


def get_scorer(model: str = "vader", analyzer=None) -> Scorer:
    """Factory: select a scorer by name. Falls back to VADER on any failure."""
    if model == "finbert":
        return FinBertScorer()
    return VaderScorer(analyzer=analyzer)


@dataclass(frozen=True)
class SentimentResult:
    """Aggregated sentiment over a set of articles."""

    mean: float
    n_articles: int
    dispersion: float  # std of per-article scores
    confidence: float  # in [0, 1]

    @property
    def has_news(self) -> bool:
        return self.n_articles > 0

    @property
    def effective(self) -> float:
        """Mean shrunk toward zero by confidence — what actually drives the tilt."""
        return self.mean * self.confidence

    def label(self) -> str:
        if not self.has_news:
            return "no news"
        if self.mean > 0.05:
            return "positive"
        if self.mean < -0.05:
            return "negative"
        return "neutral"


def _confidence(n: int, dispersion: float) -> float:
    """Confidence grows with sample size and shrinks as articles disagree."""
    if n <= 0:
        return 0.0
    size_factor = min(1.0, n / _CONFIDENCE_FULL_N)
    agreement = max(0.0, 1.0 - min(1.0, dispersion / _CONFIDENCE_MAX_DISPERSION))
    return float(size_factor * agreement)


def aggregate_sentiment(scores: Sequence[float]) -> SentimentResult:
    """
    Turn per-article scores into a structured result. An empty sequence is a
    distinct "no news" state (confidence 0), NOT a neutral 0.0 reading.
    """
    arr = np.asarray([s for s in scores if s is not None], dtype=float)
    if arr.size == 0:
        return SentimentResult(mean=0.0, n_articles=0, dispersion=0.0, confidence=0.0)
    mean = float(arr.mean())
    dispersion = float(arr.std(ddof=0))
    return SentimentResult(
        mean=mean,
        n_articles=int(arr.size),
        dispersion=dispersion,
        confidence=_confidence(int(arr.size), dispersion),
    )


def score_articles(articles: Sequence[dict], scorer: Scorer) -> list[float]:
    """Score a list of article dicts (title + description) → list of scores."""
    out: list[float] = []
    for art in articles:
        title = art.get("title") or ""
        desc = art.get("description") or ""
        combined = f"{title}. {desc}".strip(". ")
        out.append(scorer.score(combined))
    return out


def apply_sentiment_tilt(
    forecast: pd.Series,
    sentiment: SentimentResult,
    cfg: config.AppConfig,
) -> pd.Series:
    """
    Nudge the forecast by a bounded, horizon-decaying sentiment tilt.

    factor[h] = 1 + clip(k * effective_sentiment, -max, +max) * exp(-h / tau)

    - Bounded: the month-1 effect is capped at +/- ``sentiment_max_adj``.
    - Decaying: 30-day-old headlines barely touch month 12.
    - Honest: "no news" (or a disabled tilt) returns the forecast unchanged.
    """
    if not cfg.sentiment_enabled or not sentiment.has_news:
        return forecast.copy()

    base = float(
        np.clip(
            cfg.sentiment_k * sentiment.effective,
            -cfg.sentiment_max_adj,
            cfg.sentiment_max_adj,
        )
    )
    if base == 0.0:
        return forecast.copy()

    horizons = np.arange(len(forecast))
    decay = np.exp(-horizons / cfg.sentiment_decay_tau)
    factors = 1.0 + base * decay
    return forecast * factors
