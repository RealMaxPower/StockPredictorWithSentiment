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
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .costs import TradingCosts, apply_costs
from .data import validate_monthly

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
    trades: pd.DataFrame  # turnover is a fraction; notional/cost/equity are in currency
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


def _rebalance(
    invested: float, cash: float, target: float, costs: TradingCosts
) -> tuple[float, float, float, float, bool]:
    """Reach a post-fee target using a self-financing trade, or reject it.

    For signed trade ``v``, solve ``invested + v = target * (equity - fee(v))``.
    Fees are funded by cash/sale proceeds, never by an unrecorded asset adjustment.
    A rejected trade leaves the existing book intact and pays no fee.
    """
    equity = invested + cash
    tolerance = max(equity, 1.0) * 1e-12
    desired = target * equity - invested
    if abs(desired) <= tolerance:
        return invested, cash, 0.0, 0.0, False
    rate = costs.per_notional_bps / 1e4
    denominator = 1.0 + target * rate if desired > 0 else 1.0 - target * rate
    if denominator <= 0:
        return invested, cash, 0.0, 0.0, True
    trade = (desired - target * costs.fixed_fee) / denominator
    if (desired > 0 and trade <= 0) or (desired < 0 and trade >= 0):
        return invested, cash, 0.0, 0.0, True
    fee = apply_costs(trade, costs)
    next_invested, next_cash = invested + trade, cash - trade - fee
    if (
        not all(math.isfinite(v) for v in (trade, fee, next_invested, next_cash))
        or fee >= equity
        or next_invested < -tolerance
        or next_cash < -tolerance
    ):
        return invested, cash, 0.0, 0.0, True
    return max(next_invested, 0.0), max(next_cash, 0.0), abs(trade), fee, False


def _buy_and_hold(
    prices: np.ndarray, first: int, costs: TradingCosts, initial_capital: float, rf_period: float
) -> tuple[list[float], bool]:
    """Buy once using the same self-financing accounting as the strategy."""
    invested, cash, _, _, rejected = _rebalance(0.0, initial_capital, 1.0, costs)
    curve = [1.0]
    for i in range(first, len(prices) - 1):
        r = prices[i + 1] / prices[i] - 1.0
        invested *= 1.0 + r
        cash *= 1.0 + rf_period
        curve.append((invested + cash) / initial_capital)
    return curve, rejected


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
    cfg.validate()
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

    validate_monthly(monthly)
    prices = monthly.to_numpy(dtype=float)
    dates = monthly.index
    rf_period = config.periodic_rate(cfg.rf_annual)
    max_w = float(cfg.max_weight)

    initial_capital = cfg.initial_capital
    invested, cash = 0.0, initial_capital
    rejected_trades = 0
    eq_curve: list[float] = [1.0]
    eq_dates: list[pd.Timestamp] = [dates[first]]
    weight_vals: list[float] = []
    weight_dates: list[pd.Timestamp] = []
    trade_rows: list[dict[str, float]] = []

    for i in range(first, n - 1):
        # Point-in-time slice: prices with timestamps ≤ t (peek>0 leaks the future).
        hist_end = min(i + peek, n - 1)
        hist = monthly.iloc[: hist_end + 1]
        requested_weight = float(weight_fn(hist, cfg))
        if not math.isfinite(requested_weight):
            raise ValueError("strategy weight must be finite")
        w_target = float(np.clip(requested_weight, 0.0, max_w))

        equity_before = invested + cash
        w_prev = invested / equity_before
        invested, cash, notional, cost, rejected = _rebalance(invested, cash, w_target, costs)
        rejected_trades += int(rejected)
        turnover = notional / equity_before
        w_after = invested / (invested + cash)

        r_next = prices[i + 1] / prices[i] - 1.0
        invested *= 1.0 + r_next
        cash *= 1.0 + rf_period
        equity = invested + cash
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError("simulation equity became non-finite or non-positive")

        weight_vals.append(w_target)
        weight_dates.append(dates[i])
        trade_rows.append(
            {
                "weight_before": w_prev,
                "weight_after": w_after,
                "target_weight": w_target,
                "turnover": turnover,
                "notional": notional,
                "cost": cost,
                "equity": equity,
                "rejected": float(rejected),
            }
        )
        eq_curve.append(equity / initial_capital)
        eq_dates.append(dates[i + 1])

    eq_index = pd.DatetimeIndex(eq_dates)
    equity_series = pd.Series(eq_curve, index=eq_index, name="strategy")
    weights_series = pd.Series(weight_vals, index=pd.DatetimeIndex(weight_dates), name="weight")
    trades = pd.DataFrame(trade_rows, index=pd.DatetimeIndex(weight_dates))

    n_steps = len(eq_curve) - 1
    bh_curve, bh_rejected = _buy_and_hold(prices, first, costs, initial_capital, rf_period)
    bh_series = pd.Series(bh_curve, index=eq_index, name="buy_and_hold")
    rf_series = pd.Series(_risk_free(n_steps, rf_period), index=eq_index, name="risk_free")

    notes = [config.DISCLAIMER]
    if rejected_trades:
        notes.append(
            f"{rejected_trades} unaffordable rebalance(s) rejected; existing holdings retained"
        )
        logger.warning(notes[-1])
    if bh_rejected:
        notes.append("buy-and-hold entry was unaffordable; benchmark remained in cash")
        logger.warning(notes[-1])
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
