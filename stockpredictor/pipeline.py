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
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from . import config, data, evaluation, forecast, news, portfolio, sentiment, strategy
from .forecast import ForecastResult
from .reproducibility import code_version, data_fingerprint
from .sanitize import sanitize_ticker
from .sentiment import Scorer, SentimentResult
from .serialization import json_safe

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
    # Which scorer produced ``sentiment`` ("vader"/"finbert"); None when no news was
    # scored or an injected scorer doesn't identify itself. Persisted with the run.
    sentiment_model: str | None = None
    configuration: dict[str, Any] = field(default_factory=dict)
    data_fingerprint: str = ""
    code_version: str = ""


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
    cfg.validate()
    ticker = sanitize_ticker(ticker)
    df = data.fetch_prices(ticker, cfg.start, cfg.end, downloader=price_downloader)
    monthly, warns = data.to_monthly(df, ticker, agg=cfg.monthly_agg, end=cfg.end or None)

    fcast = forecast.forecast_with_intervals(monthly, cfg)
    bt = {}
    if run_backtest:
        bt_models = None
        if compare_models:
            from . import models as _models

            bt_models = _models.extended_models(cfg)
        bt = forecast.backtest(monthly, cfg, models=bt_models)

    articles: list[dict[str, Any]] = []
    sentiment_model: str | None = None
    if news_client is not None:
        articles = news.fetch_articles(news_client, ticker, end_date=cfg.end, cfg=cfg)
        scorer = scorer or sentiment.get_scorer(cfg.sentiment_model)
        sentiment_model = getattr(scorer, "name", None)
        scores = sentiment.score_articles(articles, scorer)
        for art, sc in zip(articles, scores, strict=True):
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
        sentiment_model=sentiment_model,
        configuration=asdict(cfg),
        data_fingerprint=data_fingerprint(monthly),
        code_version=code_version(),
    )


# --- Simulated betting / position-sizing layer -------------------------------
@dataclass
class SimulationReport:
    """Outcome of one paper-trading simulation plus its honest scorecard.

    The strategy uses a *price-only* point-in-time forecast signal. Folding news
    sentiment into the simulated signal is deliberately deferred (brief §8 Phase 5):
    sentiment is only available "now", so applying today's reading across history
    would be lookahead — exactly the discipline this layer exists to protect.
    """

    ticker: str
    monthly: pd.Series
    result: portfolio.SimulationResult
    scorecard: evaluation.Scorecard
    holdout: evaluation.Scorecard | None
    variant_id: str
    variants_tried: int | None
    warnings: list[str] = field(default_factory=list)
    configuration: dict[str, Any] = field(default_factory=dict)
    data_fingerprint: str = ""
    code_version: str = ""

    @property
    def final_period(self) -> evaluation.Scorecard | None:
        """Descriptive tail performance; ``holdout`` remains a compatibility alias."""
        return self.holdout


def _holdout_scorecard(
    sim: portfolio.SimulationResult, cfg: config.AppConfig
) -> evaluation.Scorecard | None:
    """Scorecard on just the final ``cfg.holdout_periods`` of the (single) OOS run.

    The tail is also included in the full scorecard. It is descriptive and repeatedly
    visible, not an independent or protected holdout. Returns None if too short.
    """
    h = cfg.holdout_periods
    if len(sim.equity) < h + 2:
        return None
    eq = sim.equity.iloc[-(h + 1) :]
    bh = sim.benchmark_bh.iloc[-(h + 1) :]
    rf = sim.benchmark_rf.iloc[-(h + 1) :]
    turnover = sim.trades["turnover"].iloc[-h:]
    return evaluation.build_scorecard(eq, bh, rf, turnover, rf_annual=cfg.rf_annual)


def run_simulation(
    ticker: str,
    cfg: config.AppConfig,
    *,
    price_downloader: data.Downloader = data._default_downloader,
    monthly: pd.Series | None = None,
    store: Any | None = None,
) -> SimulationReport:
    """Run the full simulated-betting pipeline for one ticker and score it honestly.

    Fetches (or accepts) the monthly series, builds the production weight function
    (forecast signal → long-only gate → cfg-selected sizing), simulates the book with
    costs against buy-and-hold and risk-free benchmarks, and assembles the scorecard
    plus the held-out slice. When a ``store`` is given, the run is logged and the
    variant count is read back for the multiple-testing warning.
    """
    cfg.validate()
    ticker = sanitize_ticker(ticker)
    warns: list[str] = []
    if monthly is None:
        df = data.fetch_prices(ticker, cfg.start, cfg.end, downloader=price_downloader)
        monthly, warns = data.to_monthly(df, ticker, agg=cfg.monthly_agg, end=cfg.end or None)

    weight_fn = strategy.build_weight_fn(cfg)
    sim = portfolio.simulate(monthly, weight_fn, cfg)
    card = evaluation.build_scorecard(
        sim.equity,
        sim.benchmark_bh,
        sim.benchmark_rf,
        sim.trades["turnover"],
        rf_annual=cfg.rf_annual,
    )
    holdout = _holdout_scorecard(sim, cfg)
    fingerprint = data_fingerprint(monthly)
    version = code_version()
    vid = strategy.variant_id(cfg, data_fingerprint=fingerprint, code_version=version)
    report = SimulationReport(
        ticker=ticker,
        monthly=monthly,
        result=sim,
        scorecard=card,
        holdout=holdout,
        variant_id=vid,
        variants_tried=None,
        warnings=warns + sim.notes,
        configuration=asdict(cfg),
        data_fingerprint=fingerprint,
        code_version=version,
    )
    if store is not None:
        record_simulation(report, cfg, store)
    return report


def record_simulation(report: SimulationReport, cfg: config.AppConfig, store: Any) -> None:
    """Record an experiment outside computation caches; failures remain visible."""
    try:
        store.save_simulation(
            report.ticker,
            report.variant_id,
            report.scorecard,
            cfg,
            configuration=report.configuration,
            data_fingerprint=report.data_fingerprint,
            code_version=report.code_version,
        )
        report.variants_tried = store.count_simulations(report.ticker)
    except Exception as exc:  # noqa: BLE001 - an optional store must not discard results
        warning = f"Experiment history unavailable: {exc}"
        report.warnings.append(warning)
        logger.warning("%s: %s", report.ticker, warning)


def simulation_payload(report: SimulationReport, cfg: config.AppConfig) -> dict[str, Any]:
    """Serializable SIM_metrics: scorecard + cost assumptions + variant id + RF rate."""
    sim = report.result
    return json_safe(
        {
            "ticker": report.ticker,
            "configuration": report.configuration,
            "data_fingerprint": report.data_fingerprint,
            "code_version": report.code_version,
            "variant_id": report.variant_id,
            "variants_tried": report.variants_tried,
            "rf_annual": cfg.rf_annual,
            "sizing_method": cfg.sizing_method,
            "costs_bps": {
                "commission": cfg.commission_bps,
                "spread": cfg.spread_bps,
                "slippage": cfg.slippage_bps,
            },
            "fixed_fee": cfg.fixed_fee,
            "initial_capital": cfg.initial_capital,
            "scorecard": report.scorecard.as_dict(),
            "final_period": report.final_period.as_dict()
            if report.final_period is not None
            else None,
            "final_period_note": "Included in the full scorecard; not an independent holdout.",
            # Compatibility for existing JSON consumers; semantics documented above.
            "holdout": report.holdout.as_dict() if report.holdout is not None else None,
            "equity_index": [d.strftime("%Y-%m-%d") for d in sim.equity.index],
            "equity": [round(v, 6) for v in sim.equity.tolist()],
            "benchmark_bh": [round(v, 6) for v in sim.benchmark_bh.tolist()],
            "benchmark_rf": [round(v, 6) for v in sim.benchmark_rf.tolist()],
            "data_quality_warnings": report.warnings,
            "disclaimer": config.DISCLAIMER,
        }
    )


def persist_simulation_outputs(
    report: SimulationReport, out_dir: str, cfg: config.AppConfig
) -> dict[str, str]:
    """Write SIM_metrics.json + the equity-curve PNG and (if plotly) the HTML."""
    from . import plotting

    paths: dict[str, str] = {}
    os.makedirs(out_dir, exist_ok=True)

    metrics_path = os.path.join(out_dir, f"{report.ticker}_SIM_metrics.json")
    try:
        with open(metrics_path, "w", encoding="utf-8") as fh:
            json.dump(simulation_payload(report, cfg), fh, indent=2, allow_nan=False)
        paths["sim_metrics"] = metrics_path
    except OSError as exc:
        logger.error("%s: could not write SIM metrics JSON: %s", report.ticker, exc)

    try:
        paths["sim_plot"] = plotting.plot_equity_curve(report.result, report.ticker, out_dir, cfg)
        html = plotting.write_equity_html(report.result, report.ticker, out_dir)
        if html:
            paths["sim_html"] = html
    except OSError as exc:
        logger.error("%s: could not write equity plot: %s", report.ticker, exc)

    return paths


def _interval_dict(fc: ForecastResult) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for coverage, (lo, hi) in fc.intervals.items():
        out[str(coverage)] = {"lower": lo.round(4).tolist(), "upper": hi.round(4).tolist()}
    return out


def metrics_payload(result: TickerResult) -> dict[str, Any]:
    """Serializable summary: backtest, sentiment, and the forecast with intervals."""
    fc = result.forecast
    return json_safe(
        {
            "ticker": result.ticker,
            "configuration": result.configuration,
            "data_fingerprint": result.data_fingerprint,
            "code_version": result.code_version,
            "sentiment_model": result.sentiment_model,
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
    )


def persist_outputs(result: TickerResult, out_dir: str, cfg: config.AppConfig) -> dict[str, str]:
    """Write news.json, metrics.json, the PNG, and (if plotly is present) the HTML."""
    from . import plotting

    paths: dict[str, str] = {}
    os.makedirs(out_dir, exist_ok=True)

    news_path = os.path.join(out_dir, f"{result.ticker}_news.json")
    try:
        with open(news_path, "w", encoding="utf-8") as fh:
            json.dump(json_safe(result.articles), fh, indent=2, allow_nan=False)
        paths["news"] = news_path
    except OSError as exc:
        logger.error("%s: could not write news JSON: %s", result.ticker, exc)

    metrics_path = os.path.join(out_dir, f"{result.ticker}_metrics.json")
    try:
        with open(metrics_path, "w", encoding="utf-8") as fh:
            json.dump(metrics_payload(result), fh, indent=2, allow_nan=False)
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
