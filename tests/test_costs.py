"""Tests for the pure transaction-cost model."""

from __future__ import annotations

import pytest

from stockpredictor.costs import TradingCosts, apply_costs


def test_per_notional_bps_uses_half_spread():
    c = TradingCosts(commission_bps=1.0, spread_bps=6.0, slippage_bps=2.0, fixed_fee=0.0)
    # commission + spread/2 + slippage = 1 + 3 + 2 = 6 bps
    assert c.per_notional_bps == 6.0


def test_apply_costs_scales_with_notional():
    c = TradingCosts(commission_bps=0.0, spread_bps=0.0, slippage_bps=10.0)
    # 10 bps of 1000 = 1.0
    assert apply_costs(1000.0, c) == pytest.approx(1.0)
    # Doubling notional doubles cost.
    assert apply_costs(2000.0, c) == pytest.approx(2.0)


def test_apply_costs_is_sign_independent_and_monotonic():
    c = TradingCosts()
    assert apply_costs(-500.0, c) == apply_costs(500.0, c)
    assert apply_costs(1000.0, c) > apply_costs(500.0, c) > apply_costs(0.0, c)


def test_zero_notional_pays_no_fixed_fee():
    c = TradingCosts(fixed_fee=5.0)
    assert apply_costs(0.0, c) == 0.0
    # A non-zero trade does pay the fixed fee on top of the variable cost.
    assert apply_costs(100.0, c) > 5.0


def test_negative_params_rejected():
    with pytest.raises(ValueError):
        TradingCosts(slippage_bps=-1.0)


def test_from_config_reads_cfg(cfg):
    c = TradingCosts.from_config(cfg)
    assert c.commission_bps == cfg.commission_bps
    assert c.spread_bps == cfg.spread_bps
    assert c.slippage_bps == cfg.slippage_bps
