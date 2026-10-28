"""Tests for the Phase-5 alternative models and backtest-based selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
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


def test_target_return_cannot_change_its_features(monthly):
    original = models.make_features(monthly)
    changed = monthly.copy()
    changed.iloc[-1] *= 3
    perturbed = models.make_features(changed)
    features = [name for name in original if name != "target_ret"]
    pd.testing.assert_series_equal(original.iloc[-1][features], perturbed.iloc[-1][features])
    assert original.iloc[-1]["target_ret"] != perturbed.iloc[-1]["target_ret"]


@pytest.mark.skipif(not models.sklearn_available(), reason="sklearn not installed")
def test_recursive_volatility_uses_updated_past_returns(monthly, cfg, monkeypatch):
    import sklearn.ensemble

    rows = []
    predictions = [0.2, -0.1, 0.05]

    class RecordingModel:
        def __init__(self, **kwargs):
            pass

        def fit(self, features, target):
            return self

        def predict(self, row):
            rows.append(row[0].copy())
            return [predictions[len(rows) - 1]]

    monkeypatch.setattr(sklearn.ensemble, "HistGradientBoostingRegressor", RecordingModel)
    result = models.gbm_model_fn(cfg)(monthly, 3)
    returns = monthly.pct_change().dropna()
    assert rows[0][-1] == pytest.approx(returns.iloc[-3:].std())
    assert rows[1][-1] == pytest.approx(np.std([*returns.iloc[-2:], 0.2], ddof=1))
    assert rows[2][-1] == pytest.approx(np.std([returns.iloc[-1], 0.2, -0.1], ddof=1))
    assert rows[1][0] == pytest.approx(0.2)
    assert result.iloc[-1] == pytest.approx(monthly.iloc[-1] * 1.2 * 0.9 * 1.05)


def test_model_selection_excludes_perfect_but_incomplete_model(monthly, cfg, monkeypatch):
    def partial(train, horizon):
        if len(train) != len(monthly) - cfg.backtest_horizon:
            raise ValueError("failed on other folds")
        # Deliberately perfect on its only completed fold; still not eligible.
        return monthly.iloc[len(train) : len(train) + horizon]

    monkeypatch.setattr(
        models,
        "extended_models",
        lambda cfg: {"partial": partial, "naive": models.forecast.naive_forecast},
    )
    best, summary = models.select_best_model(monthly, cfg)
    assert best == "naive"
    assert summary["partial"]["mase"] == 0
    assert summary["partial"]["folds"] == 1


@pytest.mark.parametrize("case", ["no_folds", "undefined_mase", "failed_folds"])
def test_model_selection_rejects_no_valid_candidate(monthly, cfg, monkeypatch, case):
    candidate = models.forecast.naive_forecast
    if case == "no_folds":
        monthly = monthly.iloc[:6]
    elif case == "undefined_mase":
        monthly = pd.Series(100.0, index=monthly.index)
    else:
        candidate = lambda train, h: pd.Series([np.nan] * h)  # noqa: E731
    monkeypatch.setattr(models, "extended_models", lambda cfg: {"candidate": candidate})
    with pytest.raises(ValueError, match="No model has finite MASE"):
        models.select_best_model(monthly, cfg)
