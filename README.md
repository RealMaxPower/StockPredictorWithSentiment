# Stock Predictor With Sentiment

[![CI](https://github.com/RealMaxPower/StockPredictorWithSentiment/actions/workflows/ci.yml/badge.svg)](https://github.com/RealMaxPower/StockPredictorWithSentiment/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)

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
  single deterministic line that implied false precision. The fit is done in **log
  space**, so trend/seasonality scale with the price level and the bands stay positive.
- **Baselines + walk-forward backtest** — every run is scored against naive,
  seasonal-naive, and drift via rolling-origin cross-validation, reporting
  MAE/RMSE/MAPE/**MASE**/directional accuracy **and empirical interval coverage**.
- **Month-end forecasts** — the series is resampled to the month-end close, not the
  within-month average, so the metrics reflect a target you could actually trade.
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
Paper-trading simulation (see [below](#simulated-betting--position-sizing-paper-trading)):
`--simulate`, `--sizing {vol,kelly}`, `--rf-rate`, `--commission-bps`, `--spread-bps`,
`--slippage-bps`, `--target-vol`, `--kelly-fraction`, `--holdout`.

Each run writes, per ticker, into `stock_plots/YYYY-MM-DD/`:
`TICKER_forecasts.png`, `TICKER_forecast.html` (interactive), `TICKER_news.json`,
and `TICKER_metrics.json` (forecast, intervals, backtest, sentiment).

### Dashboard

```bash
streamlit run app.py     # needs the `app` extra (streamlit)
```

Pick a ticker (or a preset watchlist), date range, and headline count; see the
interactive chart with its uncertainty band, the sentiment, the backtest table,
and the headlines that informed it. Tick **Paper-trading simulation** to add the
equity-curve overlay and scorecard described below.

## Simulated betting & position sizing (paper trading)

> ⚠️ **Educational demo — not financial advice. Paper trading only.** This layer
> moves *simulated* numbers in memory and SQLite. There is no broker, no order
> execution, and no "buy now" output. Nothing here is a recommendation.

A forecast tells you *where the price might go*. It does **not** tell you whether
*trading on it would have made money after costs* — those are different questions,
and a well-calibrated forecast is not an edge. This optional layer answers the
second question honestly:

```
forecast + intervals  →  signal (μ, σ, confidence)
        signal         →  long-only target weight (threshold over the risk-free rate)
        target weight  →  size (volatility targeting, or fractional Kelly)
        positions      →  simulate the book WITH costs, walk-forward
        equity curve   →  scorecard vs buy-and-hold AND the risk-free rate
```

Run it from the CLI with `--simulate`:

```bash
stock-forecast --tickers AAPL --start 2010-01-01 --end 2024-12-31 \
  --simulate --sizing vol --rf-rate 0.04 \
  --commission-bps 1 --spread-bps 5 --slippage-bps 5
```

Each simulated ticker writes `TICKER_SIM_equity.png` / `.html` (strategy vs
buy-and-hold vs risk-free) and `TICKER_SIM_metrics.json` (all metrics + the cost
assumptions + the variant id), and prints a plain-language scorecard:

```
SCORECARD — AAPL (after costs, out-of-sample)
  Beat buy-and-hold?   NO   (excess CAGR: -2.3%, excess Sharpe: -0.18)
  Beat risk-free?      YES  (excess CAGR: +1.1%)
  Strategy CAGR:       +5.1%  | Sharpe +0.41
  Max drawdown:        -22.4%
  Turnover (ann.):     3.2x
  Variants tried:      4    ⚠ best-of-N is likely overfit; see held-out result below
  Held-out period:     beat BH=NO, beat RF=YES, CAGR +0.8% over 12 mo (touched once)
  ⚠ Educational demo — not financial advice.
```

### What keeps it honest (and why a "NO" is the expected answer)

- **No lookahead.** The weight at month *t* is computed only from prices with
  timestamps ≤ *t*; it then earns the realized *t→t+1* return it never saw. The
  test suite includes a *leakage tripwire* (shifting the signal one period into the
  future must markedly improve results — if it didn't, the harness would be leaking).
- **Costs are always on.** Every simulated trade pays commission + half-spread +
  slippage. There is **no gross-of-costs headline number**, anywhere.
- **Benchmarked against both** buy-and-hold *and* the risk-free rate, out of sample.
  Raw return is never the result; excess over both is.
- **Multiple-testing discipline.** Every variant you run is logged to SQLite; the
  scorecard reports **how many were tried** and warns that the best-looking one is
  likely overfit. A **held-out final slice** is reported separately as the
  once-touched check. Do not present the best of N runs as "the result."
- **No durable edge after costs is the expected, honest outcome** for monthly
  single-name timing — not a bug or a failure of the code. The value of this layer
  is *measuring* that truthfully, including (and especially) when the answer is NO.

### Known limitation: survivorship bias

yfinance serves only **currently-listed** tickers, so any multi-name or
cross-sectional study is biased upward (the delisted losers are invisible). This
layer does not have a point-in-time, delisting-aware universe, so it **does not
present cross-sectional stock-picking results**. Prefer the single-ticker timing
studies it ships with, which are far less exposed to this bias; treat any
multi-ticker comparison as illustrative only. A point-in-time universe (and
deflated-Sharpe multiple-testing correction) is explicit future work.

## How it works

1. **Data** — daily *adjusted* close from yfinance, validated and resampled to the
   **month-end close** (`monthly_agg="last"`; `"mean"` is available for diagnostics
   but smooths the series and flatters the metrics).
2. **Forecast** — Holt-Winters in log space (seasonal when ≥24 months) with simulated
   80%/95% intervals that stay positive.
3. **Backtest** — rolling-origin folds score the model against naive/seasonal-naive/
   drift and report the empirical coverage of the 80%/95% bands.
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
  plotting.py   matplotlib PNG (shaded intervals) + Plotly HTML + equity overlay
  pipeline.py   run_ticker() / run_simulation() — the shared core for CLI + dashboard
  models.py     SARIMAX / gradient-boosting + backtest-based selection
  costs.py      pure transaction-cost model (commission + spread + slippage)
  signals.py    forecast + intervals → normalized trading Signal (μ, σ, confidence)
  strategy.py   long-only threshold rule + signal→weight composition + variant id
  sizing.py     position sizing: volatility targeting / fractional Kelly
  portfolio.py  point-in-time, cost-aware paper-trading simulator + benchmarks
  evaluation.py equity-curve metrics (Sharpe/Sortino/maxDD/…) + honest scorecard
  store.py      optional SQLite price cache + run history + simulation log
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
- **"The metrics look modest"**: by design. Forecasting the month-end close (not the
  within-month *average*) removes a low-pass filter that used to inflate the scores —
  especially directional accuracy. The honest, harder-to-game numbers are the point.
- **Sentiment is not in the backtest**: the tilt is applied only to the live forecast.
  NewsAPI's free tier serves ~30 days, so there is no point-in-time historical news to
  backtest the tilt against — treat it as context, not validated signal. Note also the
  backtest horizon (`backtest_horizon`, default 3) is shorter than the 12-month forecast.

## License

Copyright © 2025–2026 Marshall Cahill

This program is free software: you can redistribute it and/or modify it under the
terms of the **GNU General Public License v3.0 or later** (`GPL-3.0-or-later`) as
published by the Free Software Foundation. It is distributed in the hope that it
will be useful, but **without any warranty**; without even the implied warranty of
merchantability or fitness for a particular purpose. See the full license text in
[LICENSE](LICENSE).
