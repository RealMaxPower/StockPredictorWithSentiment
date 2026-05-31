"""Offline smoke test for the CLI entry point."""

from __future__ import annotations

import os

from stockpredictor import cli, data


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
