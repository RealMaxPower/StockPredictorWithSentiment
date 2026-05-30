#!/usr/bin/env python3
"""
stock_forecast_with_sentiment.py

Backward-compatible entry point. The implementation now lives in the
``stockpredictor`` package (data / forecast / sentiment / news / plotting /
pipeline / cli); this shim keeps the original ``python3
stock_forecast_with_sentiment.py ...`` invocation working without installation.

Install as a console script instead with:  pip install -e .  →  stock-forecast ...
"""

import os
import sys

# Allow running directly from a checkout without `pip install`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stockpredictor.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
