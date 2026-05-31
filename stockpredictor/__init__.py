"""
stockpredictor — historical price forecasting with news-sentiment context.

A small, testable package split into focused modules:

- config:    defaults, the AppConfig dataclass, and logging setup
- data:      price fetching (yfinance) + validation + data-sufficiency guards
- forecast:  Holt-Winters fit, prediction intervals, baselines, backtesting, metrics
- sentiment: text scoring (VADER) + structured aggregation + the bounded forecast tilt
- news:      NewsAPI fetching with retry/backoff, window anchored to the forecast origin
- plotting:  matplotlib (with shaded intervals) and optional interactive HTML
- pipeline:  run_ticker() — the shared core used by both the CLI and the dashboard
- store:     optional SQLite read-through cache / run history
- cli:       argparse entry point and orchestration

The package is intentionally dependency-injected: network clients (yfinance,
NewsAPI, the sentiment analyzer) are passed in, so the logic is unit-testable
without touching the network.
"""

from __future__ import annotations

__version__ = "0.2.0"

__all__ = ["__version__"]
