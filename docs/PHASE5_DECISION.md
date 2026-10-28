# Phase 5 trading rerun — predictability screen not revalidated

> **Educational demo — not financial advice.** The monthly trading component was
> recomputed October 27, 2026 (America/Phoenix), with corrected portfolio accounting.
> All twelve additional tickers completed: **beat buy-and-hold 1/12; beat the 4%
> risk-free benchmark 11/12**. Combined with the corrected original eight names,
> the descriptive counts are **1/20 vs buy-and-hold and 18/20 vs risk-free**.

The old trading statistics and combined counts are superseded. The original question,
pre-registration, tables, and development decision are retained in the archive below
as an audit trail, not presented as newly validated conclusions.

The model-free predictability screen was separate from the trading simulator. Its
source snapshots and executable screen were not retained here, and its daily/weekly/
monthly autocorrelation and momentum-IC figures **have not been regenerated**. The
monthly trading rerun does not revalidate that screen or establish that no exploitable
signal can exist. The archived Phase 5 decision remains a historical decision.

## Corrected monthly trading evidence

The complete manifest and full-precision metrics are in
[`results/phase5-trading-corrected.json`](results/phase5-trading-corrected.json).
It records all twelve requested names, including META's shorter coverage warning,
and contains no failed or excluded ticker. The original eight-name evidence and
method are in [`RESULTS.md`](RESULTS.md).

| Item | Recorded value |
|---|---|
| Requested prices | `[2005-01-01, 2025-01-01)`; end exclusive |
| Source | Fresh yfinance `auto_adjust=True`; no legacy cache or news |
| Acquisition/run interval | 2026-10-28 06:25:43–06:26:48 UTC (October 27 in Phoenix) |
| Signal / sizing | Price-only Holt-Winters; annual volatility target 10% |
| Costs | Commission 1 bps + half of 5 bps full spread + 5 bps slippage |
| Initial capital / fixed fee | 10,000 / 0 currency units |
| Cash benchmark | Constant 4% annual rate |
| Eleven full-history names | 240 monthly observations; equity 2005-07-31–2024-12-31; 233 returns |
| META | Prices begin 2012-05-18; 152 monthly observations; equity 2012-11-30–2024-12-31; 145 returns |
| Earlier variants tried | Unknown; no total experiment count established by this rerun |

Both corrected manifests record the same package source hash:
`sha256:b6e15ddae37db637ed33822111e58079fa750c7a2b95ee2fa8b54bc26bad8cfa`.
Dependency versions, the script hash, full configuration, CSV hashes, monthly input
fingerprints, actual evaluation ranges, and warnings are retained in the JSON.
Raw snapshots and equity arrays remain local under
`/tmp/stockpredictor-phase5-review-network/`; they are not embedded in the repository
evidence file. Relative artifact paths in the manifest refer to that run directory.
A future download can revise historical adjusted prices and is a different data vintage.

## All twelve monthly results

“Beat” is based on CAGR after costs. Excess CAGR is in percentage points (pp). META
has a shorter evaluation window; the row is retained rather than silently excluded.

| Ticker | Monthly returns | Strategy CAGR | BH CAGR | Excess CAGR vs BH | Excess Sharpe vs BH | Beat BH / RF? |
|---|---|---|---|---|---|---|
| AMZN | 233 | 8.03% | 26.57% | -18.55 pp | -0.117 | NO / YES |
| GOOGL | 233 | 8.24% | 18.35% | -10.11 pp | -0.027 | NO / YES |
| META | 145 | 8.01% | 28.64% | -20.63 pp | -0.130 | NO / YES |
| NVDA | 233 | 9.27% | 39.58% | -30.31 pp | -0.186 | NO / YES |
| CVX | 233 | 5.89% | 8.88% | -2.99 pp | -0.072 | NO / YES |
| CAT | 233 | 4.62% | 13.14% | -8.52 pp | -0.305 | NO / YES |
| DIS | 233 | 6.51% | 9.08% | -2.57 pp | -0.009 | NO / YES |
| INTC | 233 | 2.20% | 1.23% | +0.97 pp | -0.208 | YES / NO |
| CSCO | 233 | 4.02% | 8.21% | -4.19 pp | -0.246 | NO / YES |
| MCD | 233 | 8.77% | 15.37% | -6.60 pp | -0.186 | NO / YES |
| WMT | 233 | 7.39% | 11.45% | -4.05 pp | -0.020 | NO / YES |
| HD | 233 | 6.86% | 14.74% | -7.89 pp | -0.150 | NO / YES |

INTC is the only name in these twelve with higher CAGR than buy-and-hold, but its
strategy CAGR is below the configured risk-free benchmark and its excess Sharpe is
negative. These comparisons describe this chosen configuration and sample. They are
not an estimate of the chance of finding an edge across all possible strategies.
The selected surviving names, unequal histories, constant cash rate, simplified
execution, and possible revised source data limit interpretation. Changes from the
archived table cannot be attributed solely to the cost-accounting correction because
its exact source snapshots and run procedure were not retained.

The final-period metrics are recorded in the JSON for completeness. They use the
last twelve returns, overlap the full scorecards, and are exposed on every rerun.
They are **not a protected holdout**. No new independent validation was performed,
and the unchanged original pre-registration does not make previously viewed history
unseen. Revalidating the signal-side screen requires its own versioned executable,
explicit snapshots, and complete universe report; any new evaluation criteria must
be frozen before new results are revealed.

## Replay the trading component

Use retained `Date` / adjusted `Close` snapshots and a new output directory:

```bash
python -m scripts.regenerate_results \
  --prices-dir /path/to/adjusted-price-snapshots \
  --tickers AMZN,GOOGL,META,NVDA,CVX,CAT,DIS,INTC,CSCO,MCD,WMT,HD \
  --outdir stock_plots/phase5-trading-regeneration-01
```

For a fresh data vintage, replace `--prices-dir ...` with explicit `--download`.
Report all input coverage warnings and failures alongside completed studies. This
command does not reproduce the separate predictability screen.

## Historical archive — not current validated evidence

<details>
<summary>Original Phase 5 report and unchanged pre-registration (superseded)</summary>

# Phase 5 decision: do not build the signal-side work (yet)

> ⚠️ **Educational demo — not financial advice.** A pre-registered screen run to
> decide whether the gated Phase 5 work (short-horizon signals, long/short,
> deflated Sharpe, point-in-time universe) is worth building. The conclusion is a
> **null**: no exploitable price-based timing edge was found, so the signal-side
> items stay parked. A cheap "don't build it" is a successful outcome.

Commit screened: `c516ecd` · screen script: a reusable predictability + trading
sweep (model-free, no library changes).

---

## 1. The question

Phases 1–4 produced a credible null on monthly single-ticker timing (beat
buy-and-hold 0/8, 80% prediction band ~5× the one-step move — see
[`RESULTS.md`](RESULTS.md)). Before spending engineering on Phase 5, the question
is whether the *signal* — not the plumbing — has anything to offer at a different
cadence or under different constraints. The principle: **gate each Phase 5 build
behind a diagnostic far cheaper than the build, and kill bad ideas with a stats
script, not a new module.**

## 2. Pre-registration (written BEFORE running)

- **Prior:** the broad universe will confirm the null (few/no names beat BH after
  costs). Momentum IC will be near zero and sign-inconsistent across time-halves at
  all horizons; possibly weak *negative* daily autocorrelation (short-term reversal)
  and faint intermediate momentum, but nothing stable enough to survive costs.
- **Green light for short-horizon Phase 5:** some horizon shows a momentum IC that is
  non-trivial (|IC| ≳ 0.03–0.05), **same-signed across both 2005–14 and 2015–24
  halves, and positive across the universe.**
- **Red flag:** any |IC| > 0.2 — almost certainly a lookahead bug in the screen, not
  real predictability.

## 3. Method

- **Universe:** 34 liquid large-caps (AAPL, MSFT, AMZN, GOOGL, META, NVDA, JPM, BAC,
  WFC, JNJ, PFE, MRK, KO, PEP, PG, WMT, HD, XOM, CVX, CAT, BA, DIS, VZ, T, INTC, CSCO,
  IBM, ORCL, MCD, NKE, MMM, GE, SPY, QQQ).
- **Predictability screen (model-free, no trading layer):** at daily / weekly /
  monthly, two statistics on two disjoint time-halves (split 2015-01-01) for an
  out-of-sample stability check:
  - lag-1 return autocorrelation;
  - **momentum IC** = Spearman correlation of a trailing-return signal (sum of the last
    L returns, L = 21/4/12) with the next return. The signal is shifted so it uses only
    returns strictly *before* the predicted one — no lookahead.
- **Trading sweep:** the existing `pipeline.run_simulation` (vol-targeting, default
  1/5/5 bps costs, 4% RF, N=1) on 12 further names, to corroborate the breadth of the
  null beyond the original 8.

## 4. Results

### Predictability screen (h1 = 2005–14, h2 = 2015–24)

| Horizon | Lag-1 autocorr (h1/h2) | Momentum IC (h1/h2) | % names +IC (h1/h2) | IC sign-stable across halves |
|---|---|---|---|---|
| Daily | −0.052 / −0.062 | −0.022 / −0.011 | 21% / 29% | 62% |
| Weekly | −0.070 / −0.048 | −0.031 / −0.030 | 29% / 32% | 68% |
| Monthly | +0.018 / −0.066 | −0.070 / −0.078 | 18% / 21% | 64% |

### Trading sweep (12 new names → 20 single-ticker studies in total)

| Ticker | Beat BH? | Beat RF? | Strat CAGR | BH CAGR | Excess Sharpe |
|---|---|---|---|---|---|
| AMZN | NO | YES | +9.7% | +28.6% | −0.23 |
| GOOGL | NO | YES | +7.8% | +21.1% | −0.28 |
| META | NO | YES | +8.0% | +28.7% | −0.13 |
| NVDA | NO | YES | +13.9% | +56.7% | −0.11 |
| CVX | NO | YES | +6.1% | +8.7% | −0.04 |
| CAT | NO | YES | +6.0% | +15.0% | −0.21 |
| DIS | NO | YES | +8.8% | +9.7% | +0.17 |
| INTC | YES | YES | +4.1% | +2.7% | −0.05 |
| CSCO | NO | YES | +5.7% | +9.8% | −0.06 |
| MCD | NO | YES | +10.1% | +13.5% | −0.05 |
| WMT | NO | YES | +8.5% | +14.7% | −0.09 |
| HD | NO | YES | +8.4% | +22.8% | −0.39 |

**Sweep: beat BH 1/12 · beat RF 12/12.** Combined with the earlier 8 names:
**beat BH 1/20, beat RF 19/20.** The lone BH "win" (INTC) has *negative* excess
Sharpe (−0.05) — buy-and-hold being unusually weak, not a risk-adjusted win. 1/20 ≈
5% is coin-flip noise (and a live illustration of why deflated-Sharpe matters once
many variants are tried).

## 5. Interpretation — matched the prior, no green light

- **Momentum IC is small and negative at every horizon** (−0.01 to −0.08); only
  18–32% of names had a positive IC. Trailing-return momentum does not predict — if
  anything there is mild reversal. The green-light bar is **not cleared anywhere.**
- **Daily/weekly autocorrelation is consistently negative** (−0.05 to −0.07): real,
  sign-stable short-term reversal — but tiny, and reversal demands high-turnover
  daily/weekly trading, the exact regime where bid/ask + slippage dominate. A ~0.06
  autocorr will not survive 5–10 bps per leg.
- **No red flag** (no |IC| > 0.2) — the screen is not leaking.

## 6. Decision

| Phase 5 item | Decision on this evidence |
|---|---|
| **Short-horizon signals** | **Do not build.** Only weak short-term reversal exists; it is a cost trap, and there is no harvestable momentum. |
| **Long/short** | **Do not build.** Momentum IC ≈ 0/negative ⇒ no directional power to short on. |
| **Point-in-time / delisting-aware universe** | **Parked.** Only needed for cross-sectional claims, which are out of scope. |
| **Deflated Sharpe** | **Not needed at N=1.** Revisit when variant sweeps per ticker grow (read `store.count_simulations`). |

**Recommendation: keep Phase 5 parked.** Building short-horizon or long/short now
would be building on a known null.

## 7. The honest limit of this conclusion

This screen tested **price-derived** momentum/reversal signals only. It does **not**
rule out a genuinely different signal source — fundamentals, properly point-in-time
sentiment, cross-asset, or alternative data. That is the *only* gate worth opening
Phase 5 for, and it is a research project of its own (new data + a new leakage
surface), not a tweak to this layer. The precise finding is: **no exploitable
price-based timing edge at daily/weekly/monthly for liquid large-caps** — exactly the
null an efficient-market prior predicts.

If such a signal is ever proposed, the screen above is the reusable instrument: point
it at the new signal first, pre-register the bar, and build only if the out-of-sample
IC clears it across both time-halves and the universe.

</details>
