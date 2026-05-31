"""
The shared analysis core. ``run_ticker`` is the single function the CLI and the
Streamlit dashboard both call, so behavior never diverges between them. All
network dependencies are injected (price downloader, news client, scorer) so the
pipeline runs in tests and in a key-less "demo" mode without touching the network.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from . import config, data, forecast, news, sentiment
from .forecast import ForecastResult
from .sanitize import sanitize_ticker
from .sentiment import Scorer, SentimentResult

logger = logging.getLogger("stockpredictor.pipeline")


@dataclass
class TickerResult:
    ticker: str
    monthly: pd.Series
    forecast: ForecastResult
    adjusted: pd.Series
    sentiment: SentimentResult
    articles: list[dict[str, Any]] = field(default_factory=list)
    backtest: dict[str, dict[str, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def run_ticker(
    ticker: str,
    cfg: config.AppConfig,
    *,
    price_downloader: data.Downloader = data._default_downloader,
    news_client: Any | None = None,
    scorer: Scorer | None = None,
    run_backtest: bool = True,
    compare_models: bool = False,
) -> TickerResult:
    """Fetch, forecast (with intervals + backtest), score news, and apply the tilt."""
    # Validate before the symbol becomes a file name in persist_outputs/plotting.
    ticker = sanitize_ticker(ticker)
    df = data.fetch_prices(ticker, cfg.start, cfg.end, downloader=price_downloader)
    monthly, warns = data.to_monthly(df, ticker)

    fcast = forecast.forecast_with_intervals(monthly, cfg)
    bt = {}
    if run_backtest:
        bt_models = None
        if compare_models:
            from . import models as _models

            bt_models = _models.extended_models(cfg)
        bt = forecast.backtest(monthly, cfg, models=bt_models)

    articles: list[dict[str, Any]] = []
    if news_client is not None:
        articles = news.fetch_articles(news_client, ticker, end_date=cfg.end, cfg=cfg)
        scorer = scorer or sentiment.get_scorer(cfg.sentiment_model)
        scores = sentiment.score_articles(articles, scorer)
        for art, sc in zip(articles, scores):
            art["sentiment"] = sc
        sent = sentiment.aggregate_sentiment(scores)
    else:
        sent = sentiment.aggregate_sentiment([])

    adjusted = sentiment.apply_sentiment_tilt(fcast.point, sent, cfg)

    return TickerResult(
        ticker=ticker,
        monthly=monthly,
        forecast=fcast,
        adjusted=adjusted,
        sentiment=sent,
        articles=articles,
        backtest=bt,
        warnings=warns,
    )


def _interval_dict(fc: ForecastResult) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for coverage, (lo, hi) in fc.intervals.items():
        out[str(coverage)] = {"lower": lo.round(4).tolist(), "upper": hi.round(4).tolist()}
    return out


def metrics_payload(result: TickerResult) -> dict[str, Any]:
    """Serializable summary: backtest, sentiment, and the forecast with intervals."""
    fc = result.forecast
    return {
        "ticker": result.ticker,
        "horizon_index": [d.strftime("%Y-%m-%d") for d in fc.point.index],
        "forecast": fc.point.round(4).tolist(),
        "adjusted": result.adjusted.round(4).tolist(),
        "intervals": _interval_dict(fc),
        "seasonal_used": fc.seasonal_used,
        "backtest": result.backtest,
        "sentiment": {
            "mean": round(result.sentiment.mean, 4),
            "effective": round(result.sentiment.effective, 4),
            "n_articles": result.sentiment.n_articles,
            "dispersion": round(result.sentiment.dispersion, 4),
            "confidence": round(result.sentiment.confidence, 4),
            "label": result.sentiment.label(),
        },
        "data_quality_warnings": result.warnings,
    }


def persist_outputs(result: TickerResult, out_dir: str, cfg: config.AppConfig) -> dict[str, str]:
    """Write news.json, metrics.json, the PNG, and (if plotly is present) the HTML."""
    from . import plotting

    paths: dict[str, str] = {}
    os.makedirs(out_dir, exist_ok=True)

    news_path = os.path.join(out_dir, f"{result.ticker}_news.json")
    try:
        with open(news_path, "w", encoding="utf-8") as fh:
            json.dump(result.articles, fh, indent=2)
        paths["news"] = news_path
    except OSError as exc:
        logger.error("%s: could not write news JSON: %s", result.ticker, exc)

    metrics_path = os.path.join(out_dir, f"{result.ticker}_metrics.json")
    try:
        with open(metrics_path, "w", encoding="utf-8") as fh:
            json.dump(metrics_payload(result), fh, indent=2)
        paths["metrics"] = metrics_path
    except OSError as exc:
        logger.error("%s: could not write metrics JSON: %s", result.ticker, exc)

    try:
        paths["plot"] = plotting.plot_forecast(
            result.monthly,
            result.forecast,
            result.adjusted,
            result.ticker,
            out_dir,
            cfg,
            sentiment_label=result.sentiment.label(),
        )
        html = plotting.write_interactive_html(
            result.monthly,
            result.forecast,
            result.adjusted,
            result.ticker,
            out_dir,
            sentiment_label=result.sentiment.label(),
        )
        if html:
            paths["html"] = html
    except OSError as exc:
        logger.error("%s: could not write plot: %s", result.ticker, exc)

    return paths
