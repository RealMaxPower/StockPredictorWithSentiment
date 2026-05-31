"""Tests for the simulation orchestrator, persistence, and multiple-testing count."""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest

from stockpredictor import config, pipeline
from stockpredictor.store import Store


@pytest.fixture
def seasonal_monthly() -> pd.Series:
    idx = pd.date_range("2014-01-31", periods=120, freq="ME")
    rng = np.random.default_rng(0)
    trend = np.linspace(50, 150, 120)
    seasonal = 8 * np.sin(2 * np.pi * np.arange(120) / 12)
    return pd.Series(trend + seasonal + rng.normal(0, 3, 120), index=idx)


def test_run_simulation_produces_scorecard_and_holdout(seasonal_monthly, cfg):
    report = pipeline.run_simulation("NVDA", cfg, monthly=seasonal_monthly)
    assert report.ticker == "NVDA"
    assert report.scorecard.n_periods > 0
    assert isinstance(report.scorecard.beat_buy_and_hold, bool)
    assert report.holdout is not None  # 120 months > holdout + 2
    assert report.variants_tried == 1  # no store -> single run


def test_run_simulation_short_series_has_no_holdout(cfg):
    idx = pd.date_range("2020-01-31", periods=10, freq="ME")
    short = pd.Series(np.linspace(10, 12, 10), index=idx)
    report = pipeline.run_simulation("NVDA", config.AppConfig(holdout_periods=12), monthly=short)
    assert report.holdout is None  # too short to carve out a 12-mo slice


def test_variant_count_increments_in_store(seasonal_monthly, tmp_path):
    with Store(str(tmp_path / "sim.db")) as s:
        r1 = pipeline.run_simulation(
            "NVDA", config.AppConfig(sizing_method="vol"), monthly=seasonal_monthly, store=s
        )
        r2 = pipeline.run_simulation(
            "NVDA", config.AppConfig(sizing_method="kelly"), monthly=seasonal_monthly, store=s
        )
        assert r1.variants_tried == 1
        assert r2.variants_tried == 2  # the overfit-warning trigger
        assert s.count_simulations("NVDA") == 2
        hist = s.simulation_history("NVDA")
        assert len(hist) == 2
        assert set(hist["sizing_method"]) == {"vol", "kelly"}


def test_simulation_payload_is_serializable_with_disclaimer(seasonal_monthly, cfg):
    report = pipeline.run_simulation("NVDA", cfg, monthly=seasonal_monthly)
    payload = pipeline.simulation_payload(report, cfg)
    json.dumps(payload)  # must be JSON-serializable (raises otherwise)
    assert payload["disclaimer"] == config.DISCLAIMER
    assert "scorecard" in payload and "beat_buy_and_hold" in payload["scorecard"]
    assert payload["costs_bps"]["commission"] == cfg.commission_bps


def test_persist_simulation_writes_artifacts(seasonal_monthly, cfg, tmp_path):
    report = pipeline.run_simulation("NVDA", cfg, monthly=seasonal_monthly)
    paths = pipeline.persist_simulation_outputs(report, str(tmp_path), cfg)
    assert os.path.getsize(paths["sim_metrics"]) > 0
    assert os.path.getsize(paths["sim_plot"]) > 0
    payload = json.loads(open(paths["sim_metrics"]).read())
    assert payload["ticker"] == "NVDA"
    assert "gross" not in json.dumps(payload).lower()  # no gross-of-cost headline
