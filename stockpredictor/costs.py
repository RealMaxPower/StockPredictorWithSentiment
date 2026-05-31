"""
Transaction-cost model for the simulated betting layer.

Pure and deterministic: no network, no I/O, no global state. Every simulated
trade pays a cost here, so the backtest is never flattered by free, frictionless
trading. There is deliberately no "gross of costs" path — a cost-free curve may
exist only as a clearly-labeled diagnostic elsewhere, never as a headline.

The model is intentionally simple and explicit (§5 of the execution brief):

    cost = |trade_notional| * (commission_bps + spread_bps/2 + slippage_bps) / 1e4
           + fixed_fee   (only when something is actually traded)

A trade crosses *half* the quoted bid/ask spread (you transact at the mid plus
half-spread), hence ``spread_bps / 2``; commission and slippage apply to the full
traded notional. Cost scales linearly with traded notional and therefore with
turnover, which is what makes the cost-monotonicity guarantee hold.

⚠ Educational demo — not financial advice. This moves simulated numbers only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from . import config


@dataclass(frozen=True)
class TradingCosts:
    """Per-notional transaction costs, all expressed in basis points (1e-4).

    ``fixed_fee`` is a flat per-trade charge in currency units, applied once per
    non-zero trade (a zero-notional rebalance pays nothing).
    """

    commission_bps: float = 1.0
    spread_bps: float = 5.0
    slippage_bps: float = 5.0
    fixed_fee: float = 0.0

    def __post_init__(self) -> None:
        for name in ("commission_bps", "spread_bps", "slippage_bps", "fixed_fee"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

    @property
    def per_notional_bps(self) -> float:
        """Total variable cost in bps charged on each unit of traded notional."""
        return self.commission_bps + self.spread_bps / 2.0 + self.slippage_bps

    @classmethod
    def from_config(cls, cfg: config.AppConfig) -> TradingCosts:
        """Build a cost model from the shared ``AppConfig`` (all flags live there)."""
        return cls(
            commission_bps=cfg.commission_bps,
            spread_bps=cfg.spread_bps,
            slippage_bps=cfg.slippage_bps,
            fixed_fee=cfg.fixed_fee,
        )


def apply_costs(trade_notional: float, costs: TradingCosts) -> float:
    """Cost in currency of trading ``trade_notional`` (signed or unsigned).

    Returns ``0.0`` for a zero-notional trade (no fixed fee on a no-op rebalance).
    Otherwise the variable per-notional cost plus any fixed per-trade fee. Always
    non-negative and monotonically increasing in ``|trade_notional|``.
    """
    notional = abs(float(trade_notional))
    if notional == 0.0:
        return 0.0
    return notional * costs.per_notional_bps / 1e4 + costs.fixed_fee
