"""Offline smoke test for the CLI entry point."""

from __future__ import annotations

import logging
import os
import sys

import pytest

from stockpredictor import cli, data


def test_news_client_initialization_failure_keeps_key_out_of_logs(monkeypatch, caplog):
    import newsapi

    key = "private-constructor-canary"
    monkeypatch.setenv("NEWSAPI_KEY", key)

    def fail(**kwargs):
        raise RuntimeError(f"client initialization failed: {kwargs!r}")

    monkeypatch.setattr(newsapi, "NewsApiClient", fail)
    assert cli._make_news_client(logging.getLogger("stockpredictor.cli")) is None
    assert "continuing without news" in caplog.text.lower()
    for record in caplog.records:
        assert key not in record.getMessage()
        assert key not in repr(record.args)
        assert record.exc_info is None


def test_news_client_initialization_still_passes_the_configured_key(monkeypatch):
    from unittest.mock import Mock

    import newsapi

    key = "private-constructor-canary"
    monkeypatch.setenv("NEWSAPI_KEY", key)
    constructor = Mock()
    monkeypatch.setattr(newsapi, "NewsApiClient", constructor)
    assert (
        cli._make_news_client(logging.getLogger("stockpredictor.cli")) is constructor.return_value
    )
    constructor.assert_called_once_with(api_key=key)


def test_cli_runs_offline_without_newsapi(fake_downloader, tmp_path, monkeypatch):
    # No NEWSAPI_KEY -> news disabled; force the fake price downloader.
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    monkeypatch.setattr(data, "_default_downloader", fake_downloader)

    code = cli.main(
        [
            "--tickers",
            "NVDA,AAPL",
            "--start",
            "2015-01-01",
            "--end",
            "2024-12-31",
            "--outdir",
            str(tmp_path),
            "--no-backtest",
            "--db",
            str(tmp_path / "cli.db"),
        ]
    )
    assert code == 0
    # A date-stamped subdir with per-ticker outputs should exist.
    subdirs = [d for d in os.listdir(tmp_path) if os.path.isdir(tmp_path / d)]
    assert subdirs
    files = os.listdir(tmp_path / subdirs[0])
    assert any(f.endswith("_forecasts.png") for f in files)
    assert any(f.endswith("_metrics.json") for f in files)


def test_cli_simulate_writes_scorecard_and_artifacts(
    fake_downloader, tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    monkeypatch.setattr(data, "_default_downloader", fake_downloader)

    code = cli.main(
        [
            "--tickers",
            "NVDA",
            "--start",
            "2015-01-01",
            "--end",
            "2024-12-31",
            "--outdir",
            str(tmp_path),
            "--no-backtest",
            "--simulate",
            "--sizing",
            "vol",
            "--rf-rate",
            "0.04",
            "--db",
            str(tmp_path / "cli.db"),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "SCORECARD" in out
    assert ("Beat buy-and-hold?" in out) and ("Beat risk-free?" in out)
    assert "not financial advice" in out
    subdirs = [d for d in os.listdir(tmp_path) if os.path.isdir(tmp_path / d)]
    files = os.listdir(tmp_path / subdirs[0])
    assert any(f.endswith("_SIM_equity.png") for f in files)
    assert any(f.endswith("_SIM_metrics.json") for f in files)


def test_cli_finbert_without_extra_fails_before_any_ticker_work(tmp_path, monkeypatch):
    # News is available, so a scorer is needed — but the FinBERT extra is missing.
    monkeypatch.setattr(cli, "_make_news_client", lambda logger: object())
    monkeypatch.setitem(sys.modules, "transformers", None)

    def must_not_fetch(*args, **kwargs):
        raise AssertionError("price data fetched before the scorer was validated")

    monkeypatch.setattr(data, "_default_downloader", must_not_fetch)

    code = cli.main(
        [
            "--tickers",
            "NVDA,AAPL",
            "--start",
            "2015-01-01",
            "--end",
            "2024-12-31",
            "--sentiment-model",
            "finbert",
            "--outdir",
            str(tmp_path),
            "--db",
            str(tmp_path / "cli.db"),
        ]
    )
    assert code == 2


@pytest.mark.parametrize(
    "extra", [["--commission-bps", "-1"], ["--holdout", "0"], ["--rf-rate", "nan"]]
)
def test_cli_rejects_invalid_settings_before_fetch(extra, tmp_path, monkeypatch):
    def must_not_fetch(*args, **kwargs):
        raise AssertionError("invalid configuration fetched prices")

    monkeypatch.setattr(data, "_default_downloader", must_not_fetch)
    assert (
        cli.main(
            [
                "--tickers",
                "AAPL",
                "--start",
                "2020-01-01",
                "--end",
                "2025-01-01",
                "--outdir",
                str(tmp_path),
                "--simulate",
                *extra,
            ]
        )
        == 2
    )
    assert not list(tmp_path.iterdir())


def test_requested_simulation_failure_fails_cli(fake_downloader, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(cli, "_make_news_client", lambda logger: None)
    monkeypatch.setattr(data, "_default_downloader", fake_downloader)

    def fail(*args, **kwargs):
        raise ValueError("insufficient simulation history")

    monkeypatch.setattr(cli.pipeline, "run_simulation", fail)
    assert (
        cli.main(
            [
                "--tickers",
                "AAPL",
                "--start",
                "2020-01-01",
                "--end",
                "2025-01-01",
                "--outdir",
                str(tmp_path),
                "--simulate",
                "--no-cache",
                "--no-backtest",
            ]
        )
        == 1
    )
    assert "insufficient simulation history" in caplog.text


def test_summary_never_compares_incomplete_folds(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import pandas as pd

    incomplete = {"mase": 0.1, "folds": 1.0, "attempted_folds": 4.0, "mase_folds": 1.0}
    complete = {"mase": 1.0, "folds": 4.0, "attempted_folds": 4.0, "mase_folds": 4.0}
    result = SimpleNamespace(
        ticker="TEST",
        monthly=pd.Series([100.0]),
        forecast=SimpleNamespace(point=pd.Series([101.0]), intervals={}),
        sentiment=SimpleNamespace(label=lambda: "no news", effective=0.0, n_articles=0),
        backtest={"holt_winters": incomplete, "seasonal_naive": complete},
    )
    logger = Mock()
    cli._summarize(result, logger)
    assert "comparison unavailable" in logger.info.call_args_list[0].args[-1]
