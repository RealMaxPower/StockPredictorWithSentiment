"""Offline reproducibility, complete reporting, and opt-in I/O for the study script."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from scripts import regenerate_results as study


@pytest.fixture
def prices():
    days = pd.bdate_range("2023-01-01", "2025-01-01", inclusive="left")
    rng = np.random.default_rng(82)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, len(days))))
    return pd.DataFrame({"Close": close}, index=days)


def _read_json(path):
    def reject_constant(value):
        pytest.fail(f"nonstandard JSON constant: {value}")

    return json.loads(path.read_text(), parse_constant=reject_constant)


def test_default_study_universe_and_exclusive_window():
    args = study._parser().parse_args(["--prices-dir", "prices", "--outdir", "output"])
    assert args.tickers == "AAPL,MSFT,KO,JNJ,XOM,JPM,SPY,PG"
    assert args.start == "2005-01-01"
    assert args.end == "2025-01-01"
    assert args.download is False


def test_offline_study_keeps_missing_tickers_and_strict_json(tmp_path, prices):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    snapshot = inputs / "AAPL.csv"
    prices.to_csv(snapshot, index_label="Date", float_format="%.17g")
    out = tmp_path / "study"

    def forbidden_network(*args, **kwargs):
        pytest.fail("CSV replay must never call a downloader")

    status = study.main(
        [
            "--prices-dir",
            str(inputs),
            "--outdir",
            str(out),
            "--tickers",
            "AAPL,MSFT",
            "--start",
            "2023-01-01",
            "--end",
            "2025-01-01",
        ],
        downloader=forbidden_network,
    )
    assert status == 1
    manifest = _read_json(out / "summary.json")
    assert manifest["schema_version"] == 2
    assert manifest["status"] == "complete_with_errors"
    assert (manifest["attempted"], manifest["succeeded"], manifest["failed"]) == (2, 1, 1)
    assert [entry["ticker"] for entry in manifest["results"]] == ["AAPL", "MSFT"]
    good = _read_json(out / "AAPL_SIM_metrics.json")
    missing = _read_json(out / "MSFT_SIM_metrics.json")
    assert good["status"] == "ok"
    assert good["configuration"]["sentiment_enabled"] is False
    assert good["configuration"]["use_cache"] is False
    assert good["variants_tried"] is None  # this run cannot know experiment history
    assert good["data_fingerprint"]
    assert good["source"]["sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert (out / "prices" / "AAPL.csv").read_bytes() == snapshot.read_bytes()
    assert missing["status"] == "error"
    assert missing["error"]["type"] == "FileNotFoundError"
    # Failed tickers still identify the settings that were attempted.
    assert (
        manifest["results"][0]["configuration_identity"]
        == manifest["results"][1]["configuration_identity"]
    )
    assert (
        manifest["results"][0]["configuration_sha256"]
        == manifest["results"][1]["configuration_sha256"]
    )
    assert "not an independent holdout" in manifest["final_period_note"]


def test_malformed_snapshot_is_an_explicit_failure(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "AAPL.csv").write_text("Date,WrongColumn\n2024-01-31,100\n")
    out = tmp_path / "study"
    assert study.main(["--prices-dir", str(inputs), "--outdir", str(out), "--tickers", "AAPL"]) == 1
    summary = _read_json(out / "summary.json")
    assert summary["failed"] == 1
    assert "Date and Close" in summary["results"][0]["error"]["message"]
    assert (out / "prices" / "AAPL.csv").exists()  # the rejected input is retained, too


def test_download_is_explicit_and_snapshot_replays_exactly(tmp_path, prices):
    calls = []

    def download(ticker, **kwargs):
        calls.append((ticker, kwargs))
        return prices.copy()

    downloaded = tmp_path / "downloaded"
    common = ["--tickers", "AAPL", "--start", "2023-01-01", "--end", "2025-01-01"]
    assert (
        study.main(["--download", "--outdir", str(downloaded), *common], downloader=download) == 0
    )
    assert len(calls) == 1
    assert calls[0][1]["auto_adjust"] is True
    assert calls[0][1]["end"] == "2025-01-01"
    replayed = tmp_path / "replayed"
    assert (
        study.main(["--prices-dir", str(downloaded / "prices"), "--outdir", str(replayed), *common])
        == 0
    )
    original = _read_json(downloaded / "AAPL_SIM_metrics.json")
    replay = _read_json(replayed / "AAPL_SIM_metrics.json")
    assert original["data_fingerprint"] == replay["data_fingerprint"]
    assert original["equity"] == replay["equity"]
    assert original["scorecard"] == replay["scorecard"]
    original_manifest = _read_json(downloaded / "summary.json")
    replay_manifest = _read_json(replayed / "summary.json")
    assert original_manifest["configuration"]["outdir"] == str(downloaded)
    assert replay_manifest["configuration"]["outdir"] == str(replayed)
    original_entry = original_manifest["results"][0]
    replay_entry = replay_manifest["results"][0]
    assert original_entry["configuration_sha256"] == replay_entry["configuration_sha256"]
    identity = replay_entry["configuration_identity"]
    assert identity == original_entry["configuration_identity"]
    assert identity["schema"] == "simulation-configuration-v1"
    assert not {"outdir", "db_path", "use_cache"} & identity["settings"].keys()
    # Consumers can reproduce the digest solely from the manifest's stored input.
    assert (
        replay_entry["configuration_sha256"]
        == hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    )


def test_configuration_identity_changes_with_simulation_settings(tmp_path, prices):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    prices.to_csv(inputs / "AAPL.csv", index_label="Date", float_format="%.17g")
    common = [
        "--prices-dir",
        str(inputs),
        "--tickers",
        "AAPL",
        "--start",
        "2023-01-01",
        "--end",
        "2025-01-01",
    ]
    runs = []
    for name, rate in (("baseline", "0.04"), ("different-risk-free-rate", "0.06")):
        output = tmp_path / name
        assert study.main([*common, "--outdir", str(output), "--rf-rate", rate]) == 0
        runs.append(_read_json(output / "summary.json")["results"][0])
    original, changed = runs
    assert original["data_fingerprint"] == changed["data_fingerprint"]
    assert original["configuration_sha256"] != changed["configuration_sha256"]
    assert original["configuration_identity"]["settings"]["rf_annual"] == 0.04
    assert changed["configuration_identity"]["settings"]["rf_annual"] == 0.06
    assert original["scorecard"] != changed["scorecard"]


def test_existing_output_is_never_overwritten(tmp_path):
    out = tmp_path / "old-run"
    out.mkdir()
    marker = out / "summary.json"
    marker.write_text("previous reviewed results")
    with pytest.raises(SystemExit) as exc:
        study.main(["--prices-dir", str(tmp_path), "--outdir", str(out)])
    assert exc.value.code == 2
    assert marker.read_text() == "previous reviewed results"
