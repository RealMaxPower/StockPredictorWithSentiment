"""Tests for the SQLite store: price caching and run history."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import numpy as np
import pandas as pd
import pytest

from stockpredictor import config, evaluation, pipeline, store


def _range_downloader(ticker, start, end, progress=False, auto_adjust=True):
    """Honor the provider's exclusive-end contract, unlike the generic fixture."""
    index = pd.bdate_range("2010-01-01", "2025-01-01", name="Date")
    close = np.arange(len(index), dtype=float) + 100.0
    frame = pd.DataFrame({"Close": close, "Volume": 1000}, index=index)
    if auto_adjust:
        frame["Close"] *= 0.5
    else:
        frame["Adj Close"] = frame["Close"] * 0.5
    return frame.loc[(frame.index >= start) & (frame.index < end)]


def test_price_cache_round_trip(tmp_path):
    db = str(tmp_path / "t.db")
    calls = {"n": 0}

    def counting(ticker, **kw):
        calls["n"] += 1
        return _range_downloader(ticker, **kw)

    with store.Store(db) as s:
        cached_dl = store.make_cached_downloader(s, counting, ttl_days=30)
        df1 = cached_dl("NVDA", start="2015-01-01", end="2020-01-01")
        df2 = cached_dl("NVDA", start="2015-01-01", end="2020-01-01")
        assert calls["n"] == 1  # second call served from cache
        pd.testing.assert_frame_equal(df1, df2, check_freq=False)


@pytest.mark.parametrize(
    ("start", "end"),
    [("2015-01-01", "2024-01-01"), ("2023-01-01", "2025-01-01")],
)
def test_cache_overlap_does_not_cover_expanded_request(start, end):
    calls = []

    def download(ticker, **kwargs):
        calls.append((kwargs["start"], kwargs["end"]))
        return _range_downloader(ticker, **kwargs)

    with store.Store(":memory:") as s:
        cached_dl = store.make_cached_downloader(s, download)
        cached_dl("TEST", start="2023-01-01", end="2024-01-01")
        expanded = cached_dl("TEST", start=start, end=end)
        assert calls == [("2023-01-01", "2024-01-01"), (start, end)]
        pd.testing.assert_frame_equal(expanded, _range_downloader("TEST", start, end))


def test_cached_subrange_respects_exclusive_end():
    calls = []

    def download(ticker, **kwargs):
        calls.append(kwargs)
        return _range_downloader(ticker, **kwargs)

    with store.Store(":memory:") as s:
        cached_dl = store.make_cached_downloader(s, download)
        cached_dl("TEST", start="2023-01-01", end="2024-01-01")
        subset = cached_dl("TEST", start="2023-01-01", end="2023-02-01")
        assert len(calls) == 1
        assert subset.index[-1] == pd.Timestamp("2023-01-31")
        pd.testing.assert_frame_equal(
            subset, _range_downloader("TEST", "2023-01-01", "2023-02-01"), check_freq=False
        )


def test_adjustment_modes_are_separate_and_adjusted_close_is_preserved():
    calls = []

    def download(ticker, **kwargs):
        calls.append(kwargs["auto_adjust"])
        return _range_downloader(ticker, **kwargs)

    with store.Store(":memory:") as s:
        cached_dl = store.make_cached_downloader(s, download)
        kwargs = {"start": "2023-01-01", "end": "2024-01-01"}
        adjusted = cached_dl("TEST", **kwargs)
        raw = cached_dl("TEST", auto_adjust=False, **kwargs)
        raw_cached = cached_dl("TEST", auto_adjust=False, **kwargs)
        assert calls == [True, False]
        assert (raw["Close"] == 2 * adjusted["Close"]).all()
        pd.testing.assert_frame_equal(raw, raw_cached, check_freq=False)


def test_cache_preserves_multiindex_columns():
    frame = _range_downloader("TEST", "2023-01-01", "2024-01-01")
    frame.columns = pd.MultiIndex.from_tuples(
        [(field, "TEST") for field in frame.columns], names=["Price", "Ticker"]
    )
    with store.Store(":memory:") as s:
        s.upsert_prices("TEST", frame, start="2023-01-01", end="2024-01-01")
        cached = s.cached_prices("TEST", "2023-01-01", "2024-01-01")
        pd.testing.assert_frame_equal(frame, cached, check_freq=False)


def test_cache_preserves_exchange_timezone_across_daylight_saving():
    frame = _range_downloader("TEST", "2023-01-01", "2024-01-01")
    frame.index = frame.index.tz_localize("America/New_York")
    with store.Store(":memory:") as s:
        s.upsert_prices("TEST", frame, start="2023-01-01", end="2024-01-01")
        cached = s.cached_prices("TEST", "2023-01-01", "2024-01-01")
        pd.testing.assert_frame_equal(frame, cached, check_freq=False)


def test_old_historical_snapshot_expires_and_refetches_as_a_whole():
    calls = []

    def download(ticker, **kwargs):
        calls.append(kwargs)
        frame = _range_downloader(ticker, **kwargs)
        # Simulate later corporate-action adjustment of the entire history.
        frame["Close"] /= len(calls)
        return frame

    with store.Store(":memory:") as s:
        cached_dl = store.make_cached_downloader(s, download)
        first = cached_dl("TEST", start="2023-01-01", end="2024-01-01")
        s.conn.execute("UPDATE price_snapshots SET fetched_at='2020-01-01T00:00:00'")
        second = cached_dl("TEST", start="2023-01-01", end="2024-01-01")
        assert len(calls) == 2
        assert (second["Close"] == first["Close"] / 2).all()
        cached = cached_dl("TEST", start="2023-01-01", end="2024-01-01")
        pd.testing.assert_frame_equal(second, cached, check_freq=False)


def test_cache_requires_explicit_coverage_metadata():
    with store.Store(":memory:") as s:
        s.upsert_prices("TEST", _range_downloader("TEST", "2023-01-01", "2024-01-01"))
        assert s.cached_prices("TEST", "2023-01-01", "2024-01-01") is None


def test_save_run_and_history(tmp_path, cfg, fake_downloader, fake_news_client):
    res = pipeline.run_ticker(
        "NVDA", cfg, price_downloader=fake_downloader, news_client=fake_news_client()
    )
    with store.Store(str(tmp_path / "h.db")) as s:
        run_id = s.save_run(res, run_date="2025-01-15", cfg=cfg)
        assert run_id >= 1
        hist = s.history("NVDA")
        assert len(hist) == 1
        assert hist.iloc[0]["sentiment_label"] == res.sentiment.label()


def test_save_run_records_sentiment_model(tmp_path, cfg, fake_downloader, fake_news_client):
    res = pipeline.run_ticker(
        "NVDA", cfg, price_downloader=fake_downloader, news_client=fake_news_client()
    )
    with store.Store(str(tmp_path / "m.db")) as s:
        s.save_run(res, run_date="2025-01-15", cfg=cfg)
        assert s.history("NVDA").iloc[0]["sentiment_model"] == "vader"


def test_existing_database_gains_sentiment_model_column(tmp_path):
    # A runs table as created before sentiment_model existed, with one row in it.
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, run_date TEXT, "
        'start TEXT, "end" TEXT, horizon INTEGER, seasonal_used INTEGER, '
        "sentiment_mean REAL, sentiment_effective REAL, sentiment_n INTEGER, "
        "sentiment_label TEXT, forecast_json TEXT, backtest_json TEXT)"
    )
    conn.execute("INSERT INTO runs (ticker, run_date) VALUES ('NVDA', '2025-01-01')")
    conn.commit()
    conn.close()

    with store.Store(db) as s:
        cols = {r["name"] for r in s.conn.execute("PRAGMA table_info(runs)")}
        assert "sentiment_model" in cols
        old = s.conn.execute("SELECT ticker, sentiment_model FROM runs").fetchone()
        assert old["ticker"] == "NVDA"  # existing row survives the migration
        assert old["sentiment_model"] is None  # and stays honestly unknown

    with store.Store(db):  # reopening an already-migrated database is a no-op
        pass


def test_simulation_metadata_and_distinct_variant_count():
    cfg = config.AppConfig(start="2023-01-01", end="2024-01-01")
    curve = pd.Series([1.0, 1.1, 1.2], index=pd.date_range("2023-01-31", periods=3, freq="ME"))
    card = evaluation.build_scorecard(curve, curve, curve, pd.Series([1.0, 0.0]), rf_annual=0.0)
    with store.Store(":memory:") as s:
        for _ in range(2):
            s.save_simulation(
                "TEST",
                "same-variant",
                card,
                cfg,
                configuration={"sizing_method": "vol", "fixed_fee": 0.0},
                data_fingerprint="data-sha256",
                code_version="test-commit",
            )
        assert s.count_simulations("TEST") == 1
        assert s.count_simulation_runs("TEST") == 2
        row = s.conn.execute("SELECT * FROM simulations LIMIT 1").fetchone()
        assert json.loads(row["configuration_json"]) == {"sizing_method": "vol", "fixed_fee": 0.0}
        assert row["start"] == cfg.start and row["end"] == cfg.end
        assert row["data_fingerprint"] == "data-sha256"
        assert row["code_version"] == "test-commit"
        assert "NaN" not in row["scorecard_json"]


def test_existing_simulation_table_gains_metadata_columns(tmp_path):
    path = str(tmp_path / "old-sim.db")
    with sqlite3.connect(path) as connection:
        connection.executescript(store._SCHEMA)
        connection.execute("INSERT INTO simulations (ticker, variant_id) VALUES ('TEST', 'old')")
        connection.execute("INSERT INTO simulations (ticker, variant_id) VALUES ('TEST', 'old')")
    with store.Store(path) as s:
        row = s.conn.execute("SELECT * FROM simulations").fetchone()
        assert row["variant_id"] == "old"
        assert row["configuration_json"] is None
        assert row["data_fingerprint"] is None
        assert row["execution_id"] is None
        assert s.count_simulation_runs("TEST") == 2
        assert s.count_simulations("TEST") == 1

    with store.Store(path) as s:
        assert s.count_simulation_runs("TEST") == 2


def test_cached_execution_is_idempotent_across_connections(tmp_path, cfg):
    path = str(tmp_path / "executions.db")
    with store.Store(path):
        pass
    curve = pd.Series([1.0, 1.1, 1.2], index=pd.date_range("2023-01-31", periods=3, freq="ME"))
    card = evaluation.build_scorecard(curve, curve, curve, pd.Series([1.0, 0.0]), rf_annual=0.0)
    ready = Barrier(2)

    def save_from_session():
        with store.Store(path) as s:
            ready.wait(timeout=5)
            return s.save_simulation("TEST", "same-variant", card, cfg, execution_id="cached-run")

    with ThreadPoolExecutor(max_workers=2) as workers:
        sessions = [workers.submit(save_from_session) for _ in range(2)]
        first, second = (session.result(timeout=10) for session in sessions)
    assert first == second
    with store.Store(path) as s:
        assert s.count_simulation_runs("TEST") == 1
        assert s.count_simulations("TEST") == 1
        # A retry after reconnecting returns the existing row, even if another
        # execution has since become the most recently inserted row.
        fresh = s.save_simulation("TEST", "same-variant", card, cfg, execution_id="new-run")
        assert fresh != first
        assert (
            s.save_simulation("TEST", "same-variant", card, cfg, execution_id="cached-run") == first
        )
        assert s.count_simulation_runs("TEST") == 2
        assert s.count_simulations("TEST") == 1
