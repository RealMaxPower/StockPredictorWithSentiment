"""Tests for position sizing: vol-targeting, fractional Kelly, and edge cases."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from stockpredictor import config, sizing
from stockpredictor.signals import Signal


def _sig(mu: float, sigma: float = 0.30) -> Signal:
    return Signal(
        expected_return=mu, uncertainty=sigma, confidence=1.0, as_of=pd.Timestamp("2025-01-31")
    )


# --- Volatility targeting ----------------------------------------------------
def test_vol_target_hits_target_over_forecast_vol():
    cfg = config.AppConfig(target_vol=0.10, max_weight=1.0)
    s = _sig(mu=0.05, sigma=0.10)
    forecast_vol = 0.10 * math.sqrt(config.PERIODS_PER_YEAR)
    assert sizing.vol_target_weight(s, cfg) == pytest.approx(0.10 / forecast_vol)


def test_vol_target_caps_at_max_weight_for_calm_asset():
    cfg = config.AppConfig(target_vol=0.10, max_weight=1.0)
    # A near-zero-vol asset would imply an enormous position -> capped at max_weight.
    assert sizing.vol_target_weight(_sig(mu=0.05, sigma=1e-9), cfg) == cfg.max_weight


def test_vol_target_respects_lower_max_weight():
    cfg = config.AppConfig(target_vol=0.50, max_weight=0.6)
    assert sizing.vol_target_weight(_sig(mu=0.05, sigma=0.05), cfg) == 0.6


# --- Fractional Kelly --------------------------------------------------------
def test_fractional_kelly_is_lambda_times_full_kelly():
    cfg = config.AppConfig(kelly_fraction=0.25, max_weight=1.0)
    s = _sig(mu=0.05, sigma=0.30)
    excess = s.expected_return - config.periodic_rate(cfg.rf_annual)
    full_kelly = excess / s.uncertainty**2
    frac = sizing.kelly_weight(s, cfg)
    assert frac == pytest.approx(0.25 * full_kelly)
    assert frac < full_kelly  # fractional NEVER exceeds full Kelly


def test_kelly_caps_at_max_weight():
    cfg = config.AppConfig(kelly_fraction=0.25, max_weight=1.0)
    # Large edge / small vol -> raw Kelly >> 1, clipped to the cap.
    assert sizing.kelly_weight(_sig(mu=0.20, sigma=0.05), cfg) == cfg.max_weight


def test_kelly_sigma_underflow_is_capped_not_divide_by_zero():
    cfg = config.AppConfig(max_weight=1.0)
    # σ so small that σ² underflows to exactly 0.0 -> guard returns the cap.
    assert sizing.kelly_weight(_sig(mu=0.05, sigma=1e-200), cfg) == cfg.max_weight


# --- Shared long-only / excess guards ----------------------------------------
@pytest.mark.parametrize("method", [sizing.vol_target_weight, sizing.kelly_weight])
def test_non_positive_return_gives_zero(method):
    cfg = config.AppConfig()
    assert method(_sig(mu=-0.10), cfg) == 0.0
    assert method(_sig(mu=0.0), cfg) == 0.0


@pytest.mark.parametrize("method", [sizing.vol_target_weight, sizing.kelly_weight])
def test_positive_but_below_risk_free_gives_zero(method):
    """μ above 0 but below the RF rate has no *excess* edge -> weight 0."""
    cfg = config.AppConfig(rf_annual=0.04)
    rf_period = config.periodic_rate(cfg.rf_annual)
    assert method(_sig(mu=rf_period * 0.5), cfg) == 0.0


@pytest.mark.parametrize("method", [sizing.vol_target_weight, sizing.kelly_weight])
def test_sizing_never_negative(method):
    cfg = config.AppConfig()
    for mu in (-0.5, -0.01, 0.0, 0.01, 0.2):
        assert method(_sig(mu), cfg) >= 0.0


# --- Dispatcher --------------------------------------------------------------
def test_size_position_dispatches_on_config():
    s = _sig(mu=0.05, sigma=0.30)
    vol_cfg = config.AppConfig(sizing_method="vol")
    kelly_cfg = config.AppConfig(sizing_method="kelly")
    assert sizing.size_position(s, vol_cfg) == sizing.vol_target_weight(s, vol_cfg)
    assert sizing.size_position(s, kelly_cfg) == sizing.kelly_weight(s, kelly_cfg)
    # The two methods generally disagree on magnitude for the same signal.
    assert sizing.size_position(s, vol_cfg) != sizing.size_position(s, kelly_cfg)


def test_size_position_rejects_unknown_method():
    with pytest.raises(ValueError):
        sizing.size_position(_sig(mu=0.05), config.AppConfig(sizing_method="bogus"))
