# Stock Predictor With Sentiment

Forecasts the next 12 months of a stock's price from its history **with prediction
intervals**, contextualizes it with recent news sentiment, and — crucially —
**measures whether the forecast actually beats naive baselines** before you trust it.

> ⚠️ **Educational demo — not financial advice.** Monthly price forecasting is hard;
> the honest takeaway from the built-in backtest is usually "treat the wide
> uncertainty band seriously." This tool is for learning, not trading.

## What changed (v0.2)

The original script multiplied the whole forecast by `(1 + sentiment)` — a single
positive headline could inflate every forecast month by 50%, and nothing ever
checked if the forecast was any good. v0.2 fixes the methodology and turns the
script into a small, tested package:

- **Bounded, decaying sentiment tilt** — the news effect is capped (±~5% in month 1)
  and decays over the horizon, shrunk by a confidence score (sample size + agreement).
  "No news" is distinct from "neutral"; `--no-sentiment` disables it entirely.
- **Prediction intervals** — 80%/95% bands (Monte-Carlo simulation) instead of a
  single deterministic line that implied false precision.
- **Baselines + walk-forward backtest** — every run is scored against naive,
  seasonal-naive, and drift via rolling-origin cross-validation, reporting
  MAE/RMSE/MAPE/**MASE**/directional accuracy.
- **Adjusted close + data guards** — splits/dividends no longer read as crashes;
  seasonal fits require ≥24 months (else a non-seasonal fallback).
- **Time-aligned news** — the news window is anchored to `--end` (not "now"), and
  the free-tier 30-day limit is surfaced with a loud warning.
- **Engineering** — a `stockpredictor/` package, a pytest suite (mocked network),
  `ruff`/`mypy`, GitHub Actions CI, `pyproject.toml`, logging, and SQLite caching.
- **Interfaces** — a Streamlit dashboard, interactive Plotly HTML, and optional
  SARIMAX / gradient-boosting models compared on the same backtest.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,viz,ml,app]"   # core + dev tools + plotly + scikit-learn + streamlit
```

Pick fewer extras if you don't need everything: `viz` (interactive Plotly/HTML),
`ml` (SARIMAX/gradient-boosting via scikit-learn), `app` (the Streamlit dashboard),
`finbert` (finance-tuned sentiment), `dev` (pytest/ruff/mypy).

Or run from a checkout without installing the package (core CLI only — no
dashboard/Plotly/scikit-learn):

```bash
pip install -r requirements.txt
python3 stock_forecast_with_sentiment.py --help
```

Set a (free) NewsAPI key to enable sentiment — **optional**; forecasts run without it:

```bash
cp .env.example .env   # then edit, or:
export NEWSAPI_KEY="YOUR_KEY"     # get one at https://newsapi.org
```

## Usage

### CLI

```bash
python3 stock_forecast_with_sentiment.py \
  --tickers AAPL,NVDA,MSFT \
  --start 2015-01-01 \
  --end   2025-08-29 \
  --outdir ./stock_plots \
  --compare-models          # also backtest SARIMAX + gradient boosting
```

After `pip install -e .` the console entry point `stock-forecast ...` works too.

Useful flags: `--no-sentiment`, `--sentiment-model {vader,finbert}`, `--no-backtest`,
`--compare-models`, `--no-cache`, `--db PATH`, `--log-level {DEBUG,INFO,WARNING,ERROR}`.

Each run writes, per ticker, into `stock_plots/YYYY-MM-DD/`:
`TICKER_forecasts.png`, `TICKER_forecast.html` (interactive), `TICKER_news.json`,
and `TICKER_metrics.json` (forecast, intervals, backtest, sentiment).

### Dashboard

```bash
streamlit run app.py     # needs the `app` extra (streamlit)
```

Pick a ticker (or a preset watchlist), date range, and headline count; see the
interactive chart with its uncertainty band, the sentiment, the backtest table,
and the headlines that informed it.

## How it works

1. **Data** — daily *adjusted* close from yfinance, validated and resampled to monthly.
2. **Forecast** — Holt-Winters (seasonal when ≥24 months) with simulated 80%/95% intervals.
3. **Backtest** — rolling-origin folds score the model against naive/seasonal-naive/drift.
4. **News** — NewsAPI articles in the window ending at `--end`, scored with VADER (or FinBERT).
5. **Sentiment tilt** — a bounded, decaying, confidence-shrunk nudge — not a raw multiplier.
6. **Output** — PNG + interactive HTML + JSON; optionally cached/recorded in SQLite.

## Architecture

```
stockpredictor/
  config.py     constants + AppConfig + logging
  data.py       price fetch (injectable) + validation + monthly resample
  forecast.py   Holt-Winters + intervals + baselines + backtest + metrics
  sentiment.py  scoring (VADER/FinBERT) + structured aggregation + bounded tilt
  news.py       NewsAPI fetch with retry/backoff, window anchored to --end
  plotting.py   matplotlib PNG (shaded intervals) + Plotly HTML
  pipeline.py   run_ticker() — the shared core used by CLI and dashboard
  models.py     SARIMAX / gradient-boosting + backtest-based selection
  store.py      optional SQLite price cache + run history
  cli.py        argparse entry point
app.py          Streamlit dashboard
stock_forecast_with_sentiment.py   backward-compatible shim
```

## Development

```bash
pytest -q --cov=stockpredictor    # tests (no network — clients are mocked)
ruff check . && ruff format --check .
mypy stockpredictor
```

CI runs lint + types + tests across Python 3.9/3.11/3.12, plus a `pip-audit` job.

## Automatic Date Updates

`python3 update_readme_date.py` updates the example command's `--end` to the most
recent Friday (now hardened against a missing/unwritable README and silent no-ops).

## Troubleshooting

- **News window too old**: NewsAPI's free tier only serves ~30 days. If `--end` is
  older, the run warns and falls back; the sentiment tilt stays bounded and small.
- **Short history**: tickers with <24 monthly points fall back to a non-seasonal fit;
  <6 points are skipped with a clear error.
- **No NewsAPI key**: forecasts still run (sentiment is simply disabled).
