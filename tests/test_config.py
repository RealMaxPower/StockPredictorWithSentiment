"""Configuration errors must fail before any external or numerical work."""

import pytest

from stockpredictor.config import AppConfig


@pytest.mark.parametrize(
    "settings",
    [
        {"start": "2024-01-02", "end": "2024-01-01"},
        {"end": "2024-02-30"},
        {"start": "20240101"},
        {"commission_bps": -1},
        {"rf_annual": -1},
        {"rf_annual": float("nan")},
        {"target_vol": float("inf")},
        {"initial_capital": 0},
        {"holdout_periods": 0},
        {"horizon": 1.5},
        {"horizon": True},
        {"max_weight": 2},
        {"kelly_fraction": -0.1},
        {"page_size": 101},
        {"seasonal_periods": 24, "min_months_seasonal": 24},
    ],
)
def test_invalid_configuration_is_rejected(settings):
    with pytest.raises(ValueError):
        AppConfig(**settings)


def test_mutated_configuration_is_revalidated():
    cfg = AppConfig()
    cfg.horizon = 0
    with pytest.raises(ValueError, match="horizon"):
        cfg.validate()
