# Stock Predictor With Sentiment — contributor guide

**Follow these instructions first; fall back to searching the code only if something here is incomplete or wrong.**

This project forecasts 12 months of monthly stock prices **with prediction intervals**,
benchmarks the forecast against naive baselines via a walk-forward backtest, and applies a
**bounded, confidence-shrunk** news-sentiment tilt. It is a small, tested Python package
(`stockpredictor/`) with a CLI shim, a Streamlit dashboard, and optional SQLite caching.

> The headline rule: never reintroduce the old `forecast * (1 + sentiment)` multiplier, and
> never present a point forecast without its uncertainty band. Credibility is the point.

## Environment

- Python **3.9+**.
- Install for development (add `app` for the dashboard; `finbert` for finance-tuned sentiment):
  ```bash
  pip install -e ".[dev,viz,ml,app]"
  ```
  (core deps live in `pyproject.toml`; `requirements.txt` is kept for the no-install path.)
- `NEWSAPI_KEY` is **optional**. Without it, forecasts still run and sentiment degrades to
  "no news" (the tilt becomes a no-op). Set it via `.env` (see `.env.example`) or the env.

## Running

```bash
# CLI (shim keeps the original invocation working)
python3 stock_forecast_with_sentiment.py --tickers AAPL,NVDA --start 2015-01-01 --end 2024-12-31 --compare-models
# or, after `pip install -e .`
stock-forecast --tickers AAPL --start 2015-01-01 --end 2024-12-31
# dashboard
streamlit run app.py
```

Flags: `--no-sentiment`, `--sentiment-model {vader,finbert}`, `--no-backtest`,
`--compare-models`, `--no-cache`, `--db PATH`, `--log-level`.

## Validation (do this after every change)

```bash
pytest -q --cov=stockpredictor   # the suite mocks yfinance/NewsAPI — NO network needed
ruff check . && ruff format --check .
mypy stockpredictor
```

All three must be green; CI (`.github/workflows/ci.yml`) runs them on 3.9/3.11/3.12 plus
`pip-audit`. Tests inject fake clients (`tests/conftest.py`), so add tests for new logic
the same way rather than hitting the network.

## Architecture (where things live)

| Module | Responsibility |
| --- | --- |
| `config.py` | constants (no magic numbers), `AppConfig`, `setup_logging` |
| `data.py` | price fetch (injectable `downloader`), adjusted close, validation, monthly resample |
| `forecast.py` | Holt-Winters + simulated intervals, baselines, backtest, metrics (`InsufficientDataError`) |
| `sentiment.py` | `Scorer` (VADER/FinBERT), `aggregate_sentiment` → `SentimentResult`, `apply_sentiment_tilt` |
| `news.py` | NewsAPI fetch with retry/date-fallback, window anchored to `--end` |
| `plotting.py` | matplotlib PNG (shaded intervals) + `build_plotly_figure` / HTML |
| `pipeline.py` | `run_ticker()` — shared core for CLI + dashboard; `persist_outputs`, `metrics_payload` |
| `models.py` | SARIMAX / gradient-boosting + `select_best_model` (Phase-5, optional) |
| `store.py` | optional SQLite price cache + run history |
| `cli.py` | argparse entry point |
| `app.py` (root) | Streamlit dashboard |
| `stock_forecast_with_sentiment.py` (root) | backward-compatible shim → `stockpredictor.cli:main` |

## Conventions

- **Inject I/O.** Network clients (yfinance downloader, NewsAPI client, scorer) are passed in
  so logic stays unit-testable. Don't hardwire `yf.download` / `NewsApiClient` into logic.
- **Keep VADER the zero-dependency default.** FinBERT (`transformers`/`torch`) and sklearn
  (GBM) are optional extras, lazy-imported, and must degrade gracefully when absent.
- **Use `logging`, not `print`.** Never log the API key.
- **Modernized typing** (`from __future__ import annotations`, PEP 585/604) — ruff enforces it.
- Outputs per ticker land in `stock_plots/YYYY-MM-DD/`: `*_forecasts.png`, `*_forecast.html`,
  `*_news.json`, `*_metrics.json`.

## Common pitfalls

- NewsAPI free tier serves ~30 days; an older `--end` triggers a loud warning and a no-date
  fallback. That's expected — don't "fix" it by reverting to "last 30 days from now".
- Seasonal Holt-Winters needs ≥24 monthly points; below that the code falls back to
  non-seasonal, and below 6 points raises `InsufficientDataError`.
- `update_readme_date.py` is hardened (script-relative path, error handling, no silent no-op);
  keep it that way.
