"""
Evaluation: turn a simulated equity curve into honest, risk-aware performance
metrics and a plain-language scorecard that answers the only questions that matter
— *did the strategy beat buy-and-hold, and did it beat cash, after costs, out of
sample?*

A **NO** is a first-class, correct result. Monthly single-name timing rarely
survives costs; the scorecard is built to say so plainly rather than to flatter.

Nothing here is gross-of-costs: the equity curves it consumes are produced by
``portfolio.simulate``, which charges every trade. All comparisons are reported as
*excess over buy-and-hold* and *excess over the risk-free rate*, never raw return.

⚠ Educational demo — not financial advice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from . import config


@dataclass(frozen=True)
class PerformanceMetrics:
    """Risk/return summary of a single equity curve (all annualized where sensible)."""

    total_return: float
    cagr: float
    ann_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float  # most negative peak-to-trough fraction (<= 0)
    hit_rate: float  # fraction of periods with a positive return
    n_periods: int

    def as_dict(self) -> dict[str, float]:
        return {
            "total_return": self.total_return,
            "cagr": self.cagr,
            "ann_volatility": self.ann_volatility,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown": self.max_drawdown,
            "hit_rate": self.hit_rate,
            "n_periods": float(self.n_periods),
        }


def _max_drawdown(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def equity_metrics(
    equity: pd.Series,
    *,
    rf_annual: float,
    periods_per_year: int = config.PERIODS_PER_YEAR,
) -> PerformanceMetrics:
    """Compute risk/return metrics from an equity curve (starts at any positive value).

    Sharpe/Sortino are excess of the per-period risk-free rate and annualized by
    √periods_per_year. Short or degenerate curves yield NaN for the affected metrics
    rather than raising, so the scorecard can still render.
    """
    rets = equity.pct_change().dropna()
    n = int(len(rets))
    nan = float("nan")
    if n == 0 or equity.iloc[0] <= 0:
        return PerformanceMetrics(nan, nan, nan, nan, nan, _max_drawdown(equity), nan, n)

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = n / periods_per_year
    ratio = equity.iloc[-1] / equity.iloc[0]
    cagr = float(ratio ** (1.0 / years) - 1.0) if (years > 0 and ratio > 0) else nan

    rf_period = config.periodic_rate(rf_annual, periods_per_year)
    excess = rets - rf_period
    sd = float(rets.std(ddof=1)) if n > 1 else nan
    ann_vol = sd * math.sqrt(periods_per_year) if sd == sd else nan

    mean_excess = float(excess.mean())
    sharpe = (mean_excess / sd) * math.sqrt(periods_per_year) if (sd == sd and sd > 0) else nan

    downside = excess.clip(upper=0.0)
    dd = float(math.sqrt(float((downside**2).mean())))
    sortino = (mean_excess / dd) * math.sqrt(periods_per_year) if dd > 0 else nan

    hit_rate = float((rets > 0).mean())
    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        ann_volatility=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=_max_drawdown(equity),
        hit_rate=hit_rate,
        n_periods=n,
    )


@dataclass(frozen=True)
class Scorecard:
    """The headline verdict: did the strategy beat BH and cash, after costs?"""

    beat_buy_and_hold: bool
    beat_risk_free: bool
    excess_cagr_vs_bh: float
    excess_sharpe_vs_bh: float
    excess_cagr_vs_rf: float
    skill_vs_bh: float  # terminal-wealth ratio strat/BH; > 1 ⇒ beat the dumb thing
    max_drawdown: float
    turnover_annual: float
    n_periods: int
    strategy: PerformanceMetrics
    buy_and_hold: PerformanceMetrics
    risk_free: PerformanceMetrics
    disclaimer: str = config.DISCLAIMER

    def as_dict(self) -> dict[str, object]:
        return {
            "beat_buy_and_hold": self.beat_buy_and_hold,
            "beat_risk_free": self.beat_risk_free,
            "excess_cagr_vs_bh": self.excess_cagr_vs_bh,
            "excess_sharpe_vs_bh": self.excess_sharpe_vs_bh,
            "excess_cagr_vs_rf": self.excess_cagr_vs_rf,
            "skill_vs_bh": self.skill_vs_bh,
            "max_drawdown": self.max_drawdown,
            "turnover_annual": self.turnover_annual,
            "n_periods": self.n_periods,
            "strategy": self.strategy.as_dict(),
            "buy_and_hold": self.buy_and_hold.as_dict(),
            "risk_free": self.risk_free.as_dict(),
            "disclaimer": self.disclaimer,
        }


def _annualized_turnover(turnover_per_period: pd.Series, n_periods: int, ppy: int) -> float:
    if n_periods <= 0:
        return float("nan")
    years = n_periods / ppy
    return float(turnover_per_period.sum() / years) if years > 0 else float("nan")


def build_scorecard(
    equity: pd.Series,
    benchmark_bh: pd.Series,
    benchmark_rf: pd.Series,
    turnover_per_period: pd.Series,
    *,
    rf_annual: float,
    periods_per_year: int = config.PERIODS_PER_YEAR,
) -> Scorecard:
    """Assemble the strategy-vs-BH-vs-RF scorecard from three aligned equity curves.

    ``beat`` decisions are on CAGR after costs. ``skill_vs_bh`` is the terminal-wealth
    ratio (the returns-space analog of "did it beat the naive thing"): > 1 means the
    strategy ended richer than buy-and-hold.
    """
    strat = equity_metrics(equity, rf_annual=rf_annual, periods_per_year=periods_per_year)
    bh = equity_metrics(benchmark_bh, rf_annual=rf_annual, periods_per_year=periods_per_year)
    rf = equity_metrics(benchmark_rf, rf_annual=rf_annual, periods_per_year=periods_per_year)

    skill = (
        float((1.0 + strat.total_return) / (1.0 + bh.total_return))
        if bh.total_return > -1
        else float("nan")
    )
    return Scorecard(
        beat_buy_and_hold=bool(strat.cagr > bh.cagr),
        beat_risk_free=bool(strat.cagr > rf.cagr),
        excess_cagr_vs_bh=float(strat.cagr - bh.cagr),
        excess_sharpe_vs_bh=float(strat.sharpe - bh.sharpe),
        excess_cagr_vs_rf=float(strat.cagr - rf.cagr),
        skill_vs_bh=skill,
        max_drawdown=strat.max_drawdown,
        turnover_annual=_annualized_turnover(
            turnover_per_period, strat.n_periods, periods_per_year
        ),
        n_periods=strat.n_periods,
        strategy=strat,
        buy_and_hold=bh,
        risk_free=rf,
    )


def _yn(flag: bool) -> str:
    return "YES" if flag else "NO"


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%" if x == x else "n/a"


def format_scorecard(
    card: Scorecard,
    *,
    ticker: str = "",
    variants_tried: int = 1,
    holdout: Scorecard | None = None,
) -> str:
    """Render the plain-language scorecard block (execution brief §6).

    ``variants_tried`` and the once-touched ``holdout`` slice surface the
    multiple-testing discipline: the best of N variants is likely overfit.
    """
    head = f"SCORECARD — {ticker}".rstrip(" —") if ticker else "SCORECARD"
    lines = [
        f"{head} (after costs, out-of-sample)",
        f"  Beat buy-and-hold?   {_yn(card.beat_buy_and_hold):3s}  "
        f"(excess CAGR: {_pct(card.excess_cagr_vs_bh)}, excess Sharpe: {card.excess_sharpe_vs_bh:+.2f})",
        f"  Beat risk-free?      {_yn(card.beat_risk_free):3s}  (excess CAGR: {_pct(card.excess_cagr_vs_rf)})",
        f"  Strategy CAGR:       {_pct(card.strategy.cagr)}  | Sharpe {card.strategy.sharpe:+.2f}",
        f"  Max drawdown:        {_pct(card.max_drawdown)}",
        f"  Turnover (ann.):     {card.turnover_annual:.1f}x",
        f"  Variants tried:      {variants_tried}"
        + (
            "   ⚠ best-of-N is likely overfit; see held-out result below"
            if variants_tried > 1
            else ""
        ),
    ]
    if holdout is not None:
        lines.append(
            f"  Held-out period:     beat BH={_yn(holdout.beat_buy_and_hold)}, "
            f"beat RF={_yn(holdout.beat_risk_free)}, "
            f"CAGR {_pct(holdout.strategy.cagr)} over {holdout.n_periods} mo (touched once)"
        )
    lines.append(f"  ⚠ {card.disclaimer}")
    return "\n".join(lines)
