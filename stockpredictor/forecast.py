"""
Forecasting: Holt-Winters point forecasts WITH prediction intervals, simple
baselines to benchmark against, walk-forward backtesting, and error metrics.

The model is never trusted blind: ``backtest`` measures out-of-sample skill and
compares Holt-Winters against naive / seasonal-naive / drift baselines, so the
plan's "does this beat guessing?" question gets an honest answer.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from . import config

logger = logging.getLogger("stockpredictor.forecast")

# A model function maps (training series, horizon) -> point-forecast series.
ModelFn = Callable[[pd.Series, int], pd.Series]

_SIM_REPS = 1000
_SIM_SEED = 12345  # fixed so prediction intervals are reproducible


class InsufficientDataError(ValueError):
    """Raised when there is not enough history to fit any forecast model."""


@dataclass
class ForecastResult:
    point: pd.Series
    # coverage (e.g. 80, 95) -> (lower series, upper series)
    intervals: dict[int, tuple[pd.Series, pd.Series]] = field(default_factory=dict)
    seasonal_used: bool = False


def _future_index(index: pd.Index, horizon: int) -> pd.DatetimeIndex:
    """Build the next ``horizon`` month-end timestamps after ``index``."""
    freq = getattr(index, "freq", None) or "ME"
    return pd.date_range(index[-1], periods=horizon + 1, freq=freq)[1:]


def _fit_holt_winters(monthly: pd.Series, cfg: config.AppConfig):
    """Fit Holt-Winters, using seasonality only when there is enough history."""
    seasonal = len(monthly) >= cfg.min_months_seasonal
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(
            monthly,
            trend="add",
            seasonal="add" if seasonal else None,
            seasonal_periods=cfg.seasonal_periods if seasonal else None,
            initialization_method="estimated",
        )
        fit = model.fit(optimized=True)
    return fit, seasonal


def forecast_with_intervals(monthly: pd.Series, cfg: config.AppConfig) -> ForecastResult:
    """
    Point forecast plus prediction intervals via Monte-Carlo simulation of the
    fitted model (robust across statsmodels versions and the seasonal/non-seasonal
    split). Intervals widen with the horizon, communicating real uncertainty.
    """
    if len(monthly) < config.MIN_MONTHS_FOR_ANY_FIT:
        raise InsufficientDataError(
            f"need >= {config.MIN_MONTHS_FOR_ANY_FIT} monthly points, got {len(monthly)}"
        )

    fit, seasonal = _fit_holt_winters(monthly, cfg)
    point = fit.forecast(cfg.horizon)
    point.index = _future_index(monthly.index, cfg.horizon)

    intervals: dict[int, tuple[pd.Series, pd.Series]] = {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sims = fit.simulate(
                nsimulations=cfg.horizon,
                repetitions=_SIM_REPS,
                anchor="end",
                random_state=_SIM_SEED,
            )
        sims = np.asarray(sims)  # shape (horizon, repetitions)
        for alpha in config.INTERVAL_ALPHAS:
            coverage = int(round((1 - alpha) * 100))
            lower = np.quantile(sims, alpha / 2, axis=1)
            upper = np.quantile(sims, 1 - alpha / 2, axis=1)
            intervals[coverage] = (
                pd.Series(lower, index=point.index),
                pd.Series(upper, index=point.index),
            )
    except Exception as exc:  # noqa: BLE001 - intervals are best-effort
        logger.warning("Prediction-interval simulation failed (%s); point only.", exc)

    return ForecastResult(point=point, intervals=intervals, seasonal_used=seasonal)


# --- Baselines ---------------------------------------------------------------
def naive_forecast(train: pd.Series, horizon: int) -> pd.Series:
    """Carry the last observed value forward."""
    return pd.Series([train.iloc[-1]] * horizon, index=_future_index(train.index, horizon))


def seasonal_naive_forecast(train: pd.Series, horizon: int, m: int = 12) -> pd.Series:
    """Repeat the value from m periods ago (falls back to naive if too short)."""
    idx = _future_index(train.index, horizon)
    if len(train) < m:
        return pd.Series([train.iloc[-1]] * horizon, index=idx)
    vals = [train.iloc[-m + (h % m)] for h in range(horizon)]
    return pd.Series(vals, index=idx)


def drift_forecast(train: pd.Series, horizon: int) -> pd.Series:
    """Last value plus the average per-step slope over the training series."""
    idx = _future_index(train.index, horizon)
    if len(train) < 2:
        return pd.Series([train.iloc[-1]] * horizon, index=idx)
    slope = (train.iloc[-1] - train.iloc[0]) / (len(train) - 1)
    last = train.iloc[-1]
    return pd.Series([last + slope * (h + 1) for h in range(horizon)], index=idx)


def holt_winters_model_fn(cfg: config.AppConfig) -> ModelFn:
    """Adapt the Holt-Winters fit into a (train, horizon) -> point-series fn."""

    def _fn(train: pd.Series, horizon: int) -> pd.Series:
        fit, _ = _fit_holt_winters(train, cfg)
        out = fit.forecast(horizon)
        out.index = _future_index(train.index, horizon)
        return out

    return _fn


def default_models(cfg: config.AppConfig) -> dict[str, ModelFn]:
    """The standard panel: the model plus the baselines it must beat."""
    return {
        "holt_winters": holt_winters_model_fn(cfg),
        "naive": naive_forecast,
        "seasonal_naive": lambda t, h: seasonal_naive_forecast(t, h, cfg.seasonal_periods),
        "drift": drift_forecast,
    }


# --- Metrics -----------------------------------------------------------------
def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def mase(y_true: np.ndarray, y_pred: np.ndarray, train: np.ndarray, m: int = 1) -> float:
    """MASE scaled by the in-sample seasonal-naive MAE (< 1 beats that baseline)."""
    if len(train) <= m:
        return float("nan")
    denom = np.mean(np.abs(train[m:] - train[:-m]))
    if denom == 0:
        return float("nan")
    return float(mae(y_true, y_pred) / denom)


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray, anchor: float) -> float:
    """Fraction of steps where the predicted direction matches the actual one."""
    prev = anchor
    hits = 0
    for t, p in zip(y_true, y_pred):
        if np.sign(p - prev) == np.sign(t - prev):
            hits += 1
        prev = t
    return float(hits / len(y_true)) if len(y_true) else float("nan")


def backtest(
    monthly: pd.Series,
    cfg: config.AppConfig,
    models: dict[str, ModelFn] | None = None,
) -> dict[str, dict[str, float]]:
    """
    Rolling-origin (expanding-window) backtest. Slides the origin backward in
    ``backtest_horizon`` steps, fits each model on the prefix, scores the held-out
    window, and averages metrics across folds. Returns {model: {metric: value}}.
    """
    models = models or default_models(cfg)
    n = len(monthly)
    h = cfg.backtest_horizon
    m = cfg.seasonal_periods
    per_model: dict[str, dict[str, list[float]]] = {
        name: {"mae": [], "rmse": [], "mape": [], "mase": [], "directional": []} for name in models
    }
    folds_run = 0
    for k in range(cfg.backtest_folds):
        test_end = n - k * h
        test_start = test_end - h
        if test_start < config.MIN_MONTHS_FOR_ANY_FIT:
            break
        train = monthly.iloc[:test_start]
        test = monthly.iloc[test_start:test_end]
        if len(test) == 0:
            break
        folds_run += 1
        y_true = test.to_numpy()
        anchor = float(train.iloc[-1])
        train_arr = train.to_numpy()
        for name, fn in models.items():
            try:
                pred = fn(train, len(test)).to_numpy()
            except Exception as exc:  # noqa: BLE001 - skip a model that fails a fold
                logger.debug("Model %s failed on fold %d: %s", name, k, exc)
                continue
            per_model[name]["mae"].append(mae(y_true, pred))
            per_model[name]["rmse"].append(rmse(y_true, pred))
            per_model[name]["mape"].append(mape(y_true, pred))
            per_model[name]["mase"].append(mase(y_true, pred, train_arr, m))
            per_model[name]["directional"].append(directional_accuracy(y_true, pred, anchor))

    summary: dict[str, dict[str, float]] = {}
    for name, metrics in per_model.items():
        summary[name] = {
            metric: (float(np.nanmean(vals)) if vals else float("nan"))
            for metric, vals in metrics.items()
        }
        summary[name]["folds"] = float(folds_run)
    return summary
