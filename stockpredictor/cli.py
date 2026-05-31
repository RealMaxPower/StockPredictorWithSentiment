"""Command-line entry point: argparse, orchestration, and a per-ticker summary."""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime

from . import config, data, forecast, pipeline
from .sanitize import sanitize_ticker


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Forecast prices (with uncertainty) and contextualize with news sentiment.",
    )
    p.add_argument(
        "-t", "--tickers", required=True, help="Comma-separated tickers, e.g. AAPL,MSFT,NVDA"
    )
    p.add_argument("-s", "--start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("-e", "--end", required=True, help="End date YYYY-MM-DD")
    p.add_argument("-o", "--outdir", default="stock_plots", help="Output directory")
    p.add_argument(
        "--pagesize", type=int, default=config.PAGE_SIZE, help="News headlines to fetch per ticker"
    )
    p.add_argument(
        "--no-sentiment", action="store_true", help="Disable the sentiment tilt (raw forecast only)"
    )
    p.add_argument(
        "--sentiment-model",
        choices=["vader", "finbert"],
        default="vader",
        help="Sentiment scorer (finbert needs transformers)",
    )
    p.add_argument("--no-backtest", action="store_true", help="Skip walk-forward backtesting")
    p.add_argument(
        "--compare-models",
        action="store_true",
        help="Also backtest SARIMAX and gradient-boosting against the baselines",
    )
    p.add_argument(
        "--no-cache", action="store_true", help="Disable the SQLite price cache / run history"
    )
    p.add_argument("--db", default="stockpredictor.db", help="SQLite database path")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def _date_dir(base: str) -> str:
    path = os.path.join(base, datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(path, exist_ok=True)
    return path


def _make_news_client(logger) -> object | None:
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        logger.warning("NEWSAPI_KEY not set — running without news (forecasts only).")
        return None
    try:
        from newsapi import NewsApiClient

        return NewsApiClient(api_key=key)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not init NewsAPI client (%s); continuing without news.", exc)
        return None


def _summarize(result: pipeline.TickerResult, logger) -> None:
    change = (result.forecast.point.iloc[-1] / result.monthly.iloc[-1] - 1) * 100
    hw = result.backtest.get("holt_winters", {})
    hw_mase = hw.get("mase", float("nan"))
    sn_mase = result.backtest.get("seasonal_naive", {}).get("mase", float("nan"))
    verdict = ""
    # NaN != NaN, so this is False whenever a backtest value is missing/NaN.
    if hw_mase == hw_mase and sn_mase == sn_mase:
        verdict = "beats seasonal-naive" if hw_mase < sn_mase else "WORSE than seasonal-naive"
    logger.info(
        "%s: %d-mo change %+.1f%% | news=%s (eff %.3f, n=%d) | backtest MASE=%.3f %s",
        result.ticker,
        len(result.forecast.point),
        change,
        result.sentiment.label(),
        result.sentiment.effective,
        result.sentiment.n_articles,
        hw_mase,
        verdict,
    )

    # Out-of-sample interval coverage: does the 80/95% band actually cover that often?
    cov80, cov95 = hw.get("coverage80", float("nan")), hw.get("coverage95", float("nan"))
    if cov80 == cov80 or cov95 == cov95:
        logger.info(
            "%s: backtest interval coverage — 80%%=%.0f%% (target 80), 95%%=%.0f%% (target 95)",
            result.ticker,
            cov80 * 100,
            cov95 * 100,
        )

    # The live forecast's month-by-horizon band (the headline uncertainty).
    band = result.forecast.intervals.get(95)
    if band is not None:
        lo, hi = band
        last = result.forecast.point.index[-1].strftime("%Y-%m")
        logger.info(
            "%s: %s point %.2f, 95%% band [%.2f, %.2f]",
            result.ticker,
            last,
            result.forecast.point.iloc[-1],
            lo.iloc[-1],
            hi.iloc[-1],
        )


def main(argv: list | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logger = config.setup_logging(args.log_level)

    tickers: list[str] = []
    for raw in args.tickers.split(","):
        if not raw.strip():
            continue
        try:
            tickers.append(sanitize_ticker(raw))
        except ValueError as exc:
            logger.error("%s", exc)

    cfg = config.AppConfig(
        tickers=tickers,
        start=args.start,
        end=args.end,
        outdir=args.outdir,
        page_size=args.pagesize,
        sentiment_enabled=not args.no_sentiment,
        sentiment_model=args.sentiment_model,
        use_cache=not args.no_cache,
        db_path=args.db,
    )
    if not cfg.tickers:
        logger.error("No valid tickers provided.")
        return 1

    out_dir = _date_dir(cfg.outdir)
    logger.info("Saving outputs to %s", out_dir)
    news_client = _make_news_client(logger)

    # Optional SQLite store: read-through price cache + run history.
    store = None
    downloader = data._default_downloader
    if cfg.use_cache:
        from .store import Store, make_cached_downloader

        store = Store(cfg.db_path)
        downloader = make_cached_downloader(store, data._default_downloader)

    run_date = datetime.now().strftime("%Y-%m-%d")
    failures = 0
    try:
        for i, ticker in enumerate(cfg.tickers):
            if i > 0:
                time.sleep(cfg.inter_ticker_sleep)
            try:
                result = pipeline.run_ticker(
                    ticker,
                    cfg,
                    price_downloader=downloader,
                    news_client=news_client,
                    run_backtest=not args.no_backtest,
                    compare_models=args.compare_models,
                )
                pipeline.persist_outputs(result, out_dir, cfg)
                if store is not None:
                    store.save_run(result, run_date, cfg)
                _summarize(result, logger)
            except (ValueError, forecast.InsufficientDataError) as exc:
                logger.error("%s: skipped — %s", ticker, exc)
                failures += 1
            except Exception as exc:  # noqa: BLE001 - last-resort guard, logged with trace
                logger.exception("%s: unexpected failure — %s", ticker, exc)
                failures += 1
    finally:
        if store is not None:
            store.close()

    logger.info("Done: %d ok, %d failed.", len(cfg.tickers) - failures, failures)
    return 0 if failures < len(cfg.tickers) else 1


if __name__ == "__main__":
    raise SystemExit(main())
