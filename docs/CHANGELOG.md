# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Complete-request price-cache snapshots with TTL and adjustment-mode isolation.
- Currency-denominated simulation capital and fixed-fee CLI options; rejected
  unaffordable trades are reported without making the portfolio negative.
- Configuration/data/code identities in output JSON and simulation history.
- Offline dashboard interaction coverage in CI and regression tests for temporal
  alignment, self-financing accounting, missing uncertainty, and failed folds.

- Empirical out-of-sample interval coverage (`coverage80` / `coverage95`) in the
  walk-forward backtest, reported in the CLI alongside the live forecast bands.
- Run history records which sentiment scorer produced each run (`sentiment_model`
  in the `runs` table). Existing databases gain the column automatically; their
  earlier rows stay `NULL` because the scorer used for them is unknown.
- CI tests the documented `pip install -r requirements.txt` path on every
  supported Python, and runs the real FinBERT model so bumps to that extra are
  verified.

### Changed

- Study documentation uses UTC acquisition dates without personal timezone metadata.
- Only completed calendar months are analyzed; `--end` is exclusive and missing
  interior months are rejected. Use the first day of the next month to include a
  complete month.
- Final-period performance replaces the unsupported “touched once” holdout claim.
  Repeated runs count as one experiment when configuration, data, and code match.
- Forecasts/signals are reused across interval evaluation and sizing/cost variants;
  dashboard simulations are cached separately from experiment persistence.
- Undefined JSON metrics are `null`; HTML charts embed Plotly for offline viewing.
- Historical trading reports are preserved as superseded archives. All 20 monthly
  studies were regenerated from fresh retained price snapshots; corrected tables,
  JSON evidence, and the equity chart replace their old headline claims.

- `--sentiment-model finbert` without the `finbert` extra now stops before any
  ticker is processed, with the install command, instead of failing per ticker.
  An unknown scorer name raises instead of silently scoring with VADER.
- `requirements.txt` pins numpy per Python band (it was unpinned), since numpy 2.3+
  dropped Python 3.10 and 2.5 needs 3.12.

- Resample to the month-end close (configurable `monthly_agg`, default `"last"`)
  instead of the within-month average, which smoothed the series and inflated the
  skill metrics. Expect lower, more honest numbers.
- Fit Holt-Winters in log space so trend and seasonality scale with the price
  level and the point forecast and interval bounds stay strictly positive.

### Fixed

- NewsAPI diagnostics omit raw provider payloads and client-initialization exception
  text while retaining failure and retry information.
- Numbered coverage-file copies are ignored to avoid committing local source paths.
- Cache expansions fetch the requested history and retain exclusive end semantics;
  historical adjusted prices expire instead of being assumed immutable.
- Historical news never falls back to current articles; publication times must be
  within the requested window.
- GBM volatility features exclude their prediction target and update recursively.
- Backtests report actual successful folds and require comparable model coverage.
- Simulation trades use actual drifted holdings and pay self-financing trade costs.
  Missing or invalid intervals no longer imply negligible risk and maximal exposure.
- Dashboard results survive settings changes, requested simulation failures fail
  the CLI, and invalid configuration is rejected before downloads.
- Setup documentation uses shell exports or Streamlit secrets rather than claiming
  that `.env` files are loaded automatically.

- Interactive Plotly chart: the disclaimer no longer overlaps the date axis,
  prediction-band edges no longer render stray marker dots, and legend colors are
  pinned to match the static PNG.
- FinBERT's model loads once per CLI run instead of once per ticker.

## [0.2.0]

### Added

- 80% and 95% Monte-Carlo prediction intervals around every forecast.
- Baseline models plus a walk-forward, rolling-origin backtest reporting MAE, RMSE,
  MAPE, MASE, and directional accuracy.
- The `stockpredictor` package with a mocked-network pytest suite, ruff (lint +
  format), mypy, GitHub Actions CI, `pyproject.toml`, structured logging, and SQLite
  caching.
- Streamlit dashboard and interactive Plotly HTML output.
- Optional SARIMAX and gradient-boosting models, compared on the same backtest.
- Input sanitization: ticker allow-list validation and markdown/link output escaping.

### Changed

- News sentiment is now a bounded, decaying, confidence-shrunk **tilt** (capped at
  roughly ±5% in month 1) instead of multiplying the entire forecast by
  `(1 + sentiment)`.
- `--no-sentiment` disables the sentiment tilt entirely.
- The news window is anchored to `--end` (not "now"), with a loud free-tier 30-day
  warning when the requested window exceeds the NewsAPI free-tier limit.
- Forecasting now uses adjusted close prices.

### Fixed

- Splits and dividends no longer read as price crashes, thanks to using adjusted close.
- Seasonal fitting now requires at least 24 months of data, with a non-seasonal
  fallback; series shorter than 6 months are skipped with a clear error.

## [0.1.0]

- Initial single-script version that multiplied the forecast by `(1 + sentiment)` with no backtest.

[Unreleased]: https://github.com/RealMaxPower/StockPredictorWithSentiment/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/RealMaxPower/StockPredictorWithSentiment/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/RealMaxPower/StockPredictorWithSentiment/releases/tag/v0.1.0
