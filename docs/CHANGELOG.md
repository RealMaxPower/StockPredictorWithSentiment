# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Empirical out-of-sample interval coverage (`coverage80` / `coverage95`) in the
  walk-forward backtest, reported in the CLI alongside the live forecast bands.

### Changed

- Resample to the month-end close (configurable `monthly_agg`, default `"last"`)
  instead of the within-month average, which smoothed the series and inflated the
  skill metrics. Expect lower, more honest numbers.
- Fit Holt-Winters in log space so trend and seasonality scale with the price
  level and the point forecast and interval bounds stay strictly positive.

### Fixed

- Interactive Plotly chart: the disclaimer no longer overlaps the date axis,
  prediction-band edges no longer render stray marker dots, and legend colors are
  pinned to match the static PNG.

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
