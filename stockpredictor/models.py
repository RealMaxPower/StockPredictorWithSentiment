"""
Phase-5 alternative models, kept behind the same ``(train, horizon) -> point series``
interface the baselines use so they are *measured* on the backtest before being
trusted — never assumed better.

- SARIMAX (statsmodels): handles differencing + seasonality, accepts exog later.
- Gradient boosting (sklearn, optional): recursive forecast on lagged-return features,
  the natural home for sentiment-as-a-feature.
- ``select_best_model``: backtest the full panel and pick the lowest-MASE winner.

Deep learning is deliberately out of scope: too little data, too much tuning, no
payoff at this volume.
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

from . import config, forecast
from .forecast import ModelFn, _future_index

logger = logging.getLogger("stockpredictor.models")


def sarimax_model_fn(cfg: config.AppConfig) -> ModelFn:
    """SARIMAX(1,1,1) with a seasonal term when there is enough history."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    def _fn(train: pd.Series, horizon: int) -> pd.Series:
        seasonal = (
            (1, 1, 0, cfg.seasonal_periods)
            if len(train) >= cfg.min_months_seasonal
            else (0, 0, 0, 0)
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = SARIMAX(
                train.to_numpy(),
                order=(1, 1, 1),
                seasonal_order=seasonal,
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False)
            out = np.asarray(fit.forecast(horizon))
        return pd.Series(out, index=_future_index(train.index, horizon))

    return _fn


def make_features(series: pd.Series, n_lags: int = 6) -> pd.DataFrame:
    """Lagged returns + short rolling volatility — cheap, stationary GBM features."""
    if not isinstance(n_lags, int) or isinstance(n_lags, bool) or n_lags <= 0:
        raise ValueError("n_lags must be a positive integer")
    ret = series.pct_change()
    df = pd.DataFrame(index=series.index)
    for lag in range(1, n_lags + 1):
        df[f"ret_lag{lag}"] = ret.shift(lag)
    df["roll_vol"] = ret.shift(1).rolling(3).std()
    df["target_ret"] = ret  # next-step return to predict (aligned to row)
    return df.dropna()


def gbm_model_fn(cfg: config.AppConfig, n_lags: int = 6) -> ModelFn:
    """
    Gradient-boosted regressor forecasting one-step returns, rolled forward
    recursively and compounded back into a price path. Lazy-imports sklearn.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    def _fn(train: pd.Series, horizon: int) -> pd.Series:
        feat = make_features(train, n_lags=n_lags)
        if len(feat) < 12:  # not enough rows to learn anything
            return forecast.naive_forecast(train, horizon)
        feature_cols = [c for c in feat.columns if c != "target_ret"]
        model = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, random_state=0)
        model.fit(feat[feature_cols].to_numpy(), feat["target_ret"].to_numpy())

        ret = train.pct_change()
        recent = list(ret.dropna().iloc[-max(n_lags, 3) :])
        last_price = float(train.iloc[-1])
        preds = []
        for _ in range(horizon):
            recent_vol = float(np.std(recent[-3:], ddof=1))
            row = list(reversed(recent[-n_lags:])) + [recent_vol]
            pred_ret = float(model.predict(np.array([row]))[0])
            last_price *= 1 + pred_ret
            preds.append(last_price)
            recent.append(pred_ret)
        return pd.Series(preds, index=_future_index(train.index, horizon))

    return _fn


def sklearn_available() -> bool:
    try:
        import sklearn  # noqa: F401

        return True
    except ImportError:
        return False


def extended_models(cfg: config.AppConfig) -> dict[str, ModelFn]:
    """Baselines + Holt-Winters + SARIMAX (+ GBM when sklearn is installed)."""
    models = dict(forecast.default_models(cfg))
    models["sarimax"] = sarimax_model_fn(cfg)
    if sklearn_available():
        models["gbm"] = gbm_model_fn(cfg)
    return models


def select_best_model(monthly: pd.Series, cfg: config.AppConfig) -> tuple[str, dict]:
    """Select the lowest MASE among models valid on every attempted fold.

    Partial evaluation must not reward a model for failing on difficult folds.
    Undefined MASE (for example a constant training series) is not a valid basis
    for selecting a winner, even if the point forecasts themselves succeeded.
    """
    summary = forecast.backtest(monthly, cfg, models=extended_models(cfg))
    eligible = {
        name: metrics["mase"]
        for name, metrics in summary.items()
        if metrics["attempted_folds"] > 0
        and metrics["folds"] == metrics["attempted_folds"]
        and metrics["mase_folds"] == metrics["attempted_folds"]
        and np.isfinite(metrics["mase"])
    }
    if not eligible:
        raise ValueError("No model has finite MASE on every attempted backtest fold")
    best = min(eligible, key=lambda name: eligible[name])
    logger.info("Best model for series: %s (MASE=%.3f)", best, eligible[best])
    return best, summary
