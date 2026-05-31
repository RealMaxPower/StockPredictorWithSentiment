# Contributing to Stock Predictor With Sentiment

Thanks for your interest in improving this project! It's a small, educational
forecasting tool, and contributions of all sizes — bug reports, docs, tests, or
features — are welcome.

> ⚠️ Please keep the project's framing intact: this is an **educational demo, not
> financial advice**. Contributions should not present forecasts as trading
> signals or imply guaranteed returns.

## Getting started

```bash
git clone https://github.com/RealMaxPower/StockPredictorWithSentiment.git
cd StockPredictorWithSentiment
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,viz,ml]"   # core + dev tools + plotly + scikit-learn
```

Optionally set a NewsAPI key to exercise the sentiment path (everything works
without it — sentiment is simply disabled):

```bash
cp .env.example .env   # then add your key, or:
export NEWSAPI_KEY="YOUR_KEY"
```

## Development workflow

1. Create a branch off `main`: `git checkout -b my-change`.
2. Make your change, keeping functions small, typed, and readable.
3. Add or update tests under `tests/` (network is mocked — keep it that way).
4. Run the full local check suite below; it must pass before you open a PR.
5. Update [docs/CHANGELOG.md](docs/CHANGELOG.md) under **Unreleased** for any
   user-facing change.
6. Open a pull request using the template, explaining **what** and **why**.

## Local checks

These mirror CI (which runs on Python 3.9 / 3.11 / 3.12):

```bash
ruff check .                 # lint
ruff format --check .        # formatting
mypy stockpredictor          # type checking
pytest -q --cov=stockpredictor   # tests (no network — clients are mocked)
```

Auto-fix formatting and many lint issues with:

```bash
ruff format .
ruff check . --fix
```

## Guidelines

- **No network in tests.** Inject/patch the price and news clients (see
  `tests/conftest.py` for fixtures and the existing mocked tests).
- **Keep the methodology honest.** Bounded sentiment tilt, prediction intervals,
  and backtesting against baselines are core to the project — don't reintroduce
  unbounded multipliers or single-point "predictions" that imply false precision.
- **Don't commit secrets.** `NEWSAPI_KEY` belongs in your local `.env`
  (gitignored). See [SECURITY.md](SECURITY.md).
- **Type hints + docstrings** on public functions; `mypy` must stay clean.

## Reporting bugs / requesting features

Use the GitHub issue templates. For security issues, **do not** open a public
issue — follow [SECURITY.md](SECURITY.md) instead.

## License of contributions

This project is licensed under **GPL-3.0-or-later**. By contributing, you agree
that your contributions are licensed under the same terms. See [LICENSE](LICENSE).
