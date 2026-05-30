"""Tests for the Phase-5 alternative models and backtest-based selection."""

from __future__ import annotations

import numpy as np
import pytest

from stockpredictor import models


def test_sarimax_forecast_shape(monthly, cfg):
    out = models.sarimax_model_fn(cfg)(monthly, cfg.horizon)
    assert len(out) == cfg.horizon
    assert np.isfinite(out.to_numpy()).all()


def test_make_features_drops_warmup_rows(monthly):
    feat = models.make_features(monthly, n_lags=6)
    assert "target_ret" in feat.columns
    assert feat.isna().sum().sum() == 0  # all warmup rows dropped
    # pct_change NaN + 6-lag shift consume 7 warmup rows.
    assert len(feat) == len(monthly) - 7


@pytest.mark.skipif(not models.sklearn_available(), reason="sklearn not installed")
def test_gbm_forecast_shape(monthly, cfg):
    out = models.gbm_model_fn(cfg)(monthly, cfg.horizon)
    assert len(out) == cfg.horizon
    assert np.isfinite(out.to_numpy()).all()


def test_extended_models_includes_sarimax(monthly, cfg):
    m = models.extended_models(cfg)
    assert "sarimax" in m and "holt_winters" in m


def test_select_best_model_returns_known_name(monthly, cfg):
    best, summary = models.select_best_model(monthly, cfg)
    assert best in summary
    # Every compared model recorded a (possibly NaN) MASE.
    assert all("mase" in v for v in summary.values())
