"""
Paper-trading simulator — the heart of the simulated betting layer.

Walks time forward one rebalance at a time. At each monthly rebalance date *t* it
asks a ``WeightFn`` for a target weight, computes the trade against the current
book, **applies costs**, then marks the book to market over the *next* period.
The equity curve it produces is out-of-sample by construction: the weight chosen
at *t* is shown only prices with timestamps ≤ *t*, while the return it earns is
the realized move from *t* to *t+1* — data the weight never saw.

Two benchmarks are simulated on the identical dates and costs:

- **Buy-and-hold (BH):** fully invested in the asset from the first rebalance,
  paying the entry cost once.
- **Risk-free (RF):** compounds a configured annual rate (a constant default,
  which emits a warning — it is not a real T-bill series).

Guardrails honored here (execution brief §3): no lookahead (the ``peek``
parameter exists *only* so a test can deliberately leak the future and prove the
production path does not), costs always on, and both benchmarks always computed.

Everything is injectable and offline: the simulator never touches the network. A
``WeightFn`` encapsulates signal → strategy → sizing behind one callable, so this
module stays independent of those stages (they land in later phases) and tests can
drive it with a trivial fixed-weight strategy.

⚠ Educational demo — not financial advice. Paper trading only; no orders are placed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import config
from .costs import TradingCosts, apply_costs

logger = logging.getLogger("stockpredictor.portfolio")

# A weight function maps (price history with timestamps ≤ t, config) -> target
# weight in [0, max_weight]. The simulator is responsible for the point-in-time
# slice; the function must only read the series it is handed.
WeightFn = Callable[[pd.Series, config.AppConfig], float]


class InsufficientHistoryError(ValueError):
    """Raised when there is not enough history to run even one rebalance."""


@dataclass
class SimulationResult:
    """Outcome of one paper-trading run plus its two benchmarks."""

    equity: pd.Series  # strategy equity curve, starts at 1.0 at the first rebalance
    weights: pd.Series  # target weight chosen at each rebalance date
    trades: pd.DataFrame  # per-rebalance: weight_before/after, turnover, cost, equity
    benchmark_bh: pd.Series  # buy-and-hold equity on the same dates/costs
    benchmark_rf: pd.Series  # risk-free equity on the same dates
    costs: TradingCosts
    rf_annual: float
    warmup: int
    peek: int = 0  # >0 means the run intentionally leaked the future (tests only)
    notes: list[str] = field(default_factory=list)


def fixed_weight_fn(weight: float) -> WeightFn:
    """A trivial strategy that always targets ``weight`` — validates the harness."""

    def _fn(_history: pd.Series, _cfg: config.AppConfig) -> float:
        return weight

    return _fn


def _buy_and_hold(prices: np.ndarray, first: int, costs: TradingCosts) -> list[float]:
    """Fully invested from ``first``; pays the entry cost once, then compounds.

    Entry buys weight 1.0 from a flat book, so the traded notional is the full
    starting equity of 1.0 — the same cost the strategy would pay to reach full
    investment, keeping the comparison fair.
    """
    equity = 1.0 - apply_costs(1.0, costs)
    curve = [1.0]
    for i in range(first, len(prices) - 1):
        r = prices[i + 1] / prices[i] - 1.0
        equity *= 1.0 + r
        curve.append(equity)
    return curve


def _risk_free(n_steps: int, rf_period: float) -> list[float]:
    """Compound the per-period risk-free rate for ``n_steps`` holding periods."""
    equity = 1.0
    curve = [1.0]
    for _ in range(n_steps):
        equity *= 1.0 + rf_period
        curve.append(equity)
    return curve


def simulate(
    monthly: pd.Series,
    weight_fn: WeightFn,
    cfg: config.AppConfig,
    *,
    costs: TradingCosts | None = None,
    warmup: int | None = None,
    peek: int = 0,
) -> SimulationResult:
    """Run a monthly, long-only, cost-aware paper-trading backtest.

    Parameters
    ----------
    monthly:
        Month-end price series (the same series ``forecast``/``pipeline`` use).
    weight_fn:
        Maps the point-in-time price history to a target weight in
        ``[0, cfg.max_weight]``. The simulator clips to that range.
    costs:
        Transaction-cost model; defaults to ``TradingCosts.from_config(cfg)``.
    warmup:
        Months of history required before the first trade (defaults to
        ``config.SIM_WARMUP_MONTHS``). Uninvested capital earns the risk-free rate.
    peek:
        Number of future periods to leak into ``weight_fn`` — **0 in production**.
        A value > 0 deliberately violates point-in-time discipline and exists only
        so the leakage test can show that peeking improves results (and that the
        real path, ``peek=0``, does not). Logged loudly when non-zero.

    Returns
    -------
    SimulationResult with the strategy equity curve and both benchmarks aligned on
    identical dates, all starting at 1.0 at the first rebalance.
    """
    costs = costs or TradingCosts.from_config(cfg)
    warmup = config.SIM_WARMUP_MONTHS if warmup is None else warmup
    if peek:
        logger.warning(
            "simulate() called with peek=%d — LEAKING %d future period(s); "
            "this is a leakage diagnostic and must never be a reported result.",
            peek,
            peek,
        )

    n = len(monthly)
    first = max(int(warmup), 1)
    # Need ``first`` history points to form a signal plus at least one forward
    # return to realize. Below that, no honest rebalance is possible.
    if n - first < 2:
        raise InsufficientHistoryError(
            f"need >= warmup+2 ({first + 2}) monthly points to simulate, got {n}"
        )

    prices = monthly.to_numpy(dtype=float)
    dates = monthly.index
    rf_period = config.periodic_rate(cfg.rf_annual)
    max_w = float(cfg.max_weight)

    equity = 1.0
    w_prev = 0.0
    eq_curve: list[float] = [1.0]
    eq_dates: list[pd.Timestamp] = [dates[first]]
    weight_vals: list[float] = []
    weight_dates: list[pd.Timestamp] = []
    trade_rows: list[dict[str, float]] = []

    for i in range(first, n - 1):
        # Point-in-time slice: prices with timestamps ≤ t (peek>0 leaks the future).
        hist_end = min(i + peek, n - 1)
        hist = monthly.iloc[: hist_end + 1]
        w_target = float(np.clip(float(weight_fn(hist, cfg)), 0.0, max_w))

        turnover = abs(w_target - w_prev)
        notional = turnover * equity
        cost = apply_costs(notional, costs)
        equity_after_cost = equity - cost

        r_next = prices[i + 1] / prices[i] - 1.0
        invested = w_target * equity_after_cost
        cash = (1.0 - w_target) * equity_after_cost
        equity = invested * (1.0 + r_next) + cash * (1.0 + rf_period)

        weight_vals.append(w_target)
        weight_dates.append(dates[i])
        trade_rows.append(
            {
                "weight_before": w_prev,
                "weight_after": w_target,
                "turnover": turnover,
                "cost": cost,
                "equity": equity,
            }
        )
        eq_curve.append(equity)
        eq_dates.append(dates[i + 1])
        w_prev = w_target

    eq_index = pd.DatetimeIndex(eq_dates)
    equity_series = pd.Series(eq_curve, index=eq_index, name="strategy")
    weights_series = pd.Series(weight_vals, index=pd.DatetimeIndex(weight_dates), name="weight")
    trades = pd.DataFrame(trade_rows, index=pd.DatetimeIndex(weight_dates))

    n_steps = len(eq_curve) - 1
    bh_series = pd.Series(_buy_and_hold(prices, first, costs), index=eq_index, name="buy_and_hold")
    rf_series = pd.Series(_risk_free(n_steps, rf_period), index=eq_index, name="risk_free")

    notes = [config.DISCLAIMER]
    if cfg.rf_annual == config.RF_ANNUAL:
        notes.append(
            f"risk-free benchmark uses a constant {cfg.rf_annual:.2%} annual rate "
            "(default), not a point-in-time T-bill series"
        )

    return SimulationResult(
        equity=equity_series,
        weights=weights_series,
        trades=trades,
        benchmark_bh=bh_series,
        benchmark_rf=rf_series,
        costs=costs,
        rf_annual=cfg.rf_annual,
        warmup=first,
        peek=peek,
        notes=notes,
    )


def total_return(equity: pd.Series) -> float:
    """Cumulative return of an equity curve (final / initial − 1)."""
    if len(equity) < 2 or equity.iloc[0] == 0:
        return float("nan")
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)
