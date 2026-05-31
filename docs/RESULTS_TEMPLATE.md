# Results: Does the Simulated Betting Layer Beat Buy-and-Hold After Costs?

> ⚠️ **Educational demo — not financial advice.** This is a paper-trading study. No
> real orders were placed. A null result (no durable edge after costs) is the
> expected and honest outcome, not a defect.

> **How to use this template:** copy it to `docs/RESULTS.md` (or a dated file),
> fill §2 *before* looking at any curves, run the studies, paste each scorecard into
> §3 as you go, then interpret. The section order is the discipline — pre-register,
> read everything, interpret, then a limitations section you may not omit. Do not
> edit §2 after seeing §3.

**TL;DR (fill in last):** _One or two sentences stating the verdict plainly. e.g.
"Across N single-ticker out-of-sample studies, the strategy did not beat buy-and-hold
or the risk-free rate after costs. This is the expected result and the point of the
exercise — the value is a rigorous instrument that produces a credible null."_

---

## 1. What was tested

| Item | Value |
|---|---|
| Commit / release | `7fec68e` _(or later; record the exact commit run)_ |
| Tickers studied | `_______` |
| Study type | single-ticker timing _(preferred — sidesteps survivorship)_ / cross-sectional |
| In-sample window (tuning) | `____-__-__` → `____-__-__` |
| **Out-of-sample window (reported)** | `____-__-__` → `____-__-__` |
| Held-out slice (touched once) | final `--holdout` months (default 12) |
| Rebalance cadence | monthly |
| Sizing method(s) | vol-targeting _(default)_ / fractional Kelly (λ = 0.25 default) |
| Cost assumptions | commission 1 bps, spread 5 bps, slippage 5 bps _(defaults; override with flags)_ |
| Risk-free rate used | 4.0% _(default constant; not a point-in-time T-bill series)_ |
| Variants tried (total) | N = ___  _(read from the scorecard / `store.count_simulations`)_ |

State the in-sample vs out-of-sample split explicitly. Numbers in §3 are **out-of-sample
only**. In-sample numbers, if shown at all, go in an appendix clearly labeled as such.

> The simulator is out-of-sample *by construction* — the weight at month *t* uses only
> prices ≤ *t* and earns the realized *t→t+1* return. "In-sample" here means any window
> you used to *choose* a variant (sizing method, cost params, thresholds); the reported
> numbers must come from a window you did **not** tune on.

Reproduce a single study with:

```bash
python3 stock_forecast_with_sentiment.py \
  --tickers TICKER --start YYYY-MM-DD --end YYYY-MM-DD \
  --simulate --sizing vol --rf-rate 0.04 \
  --commission-bps 1 --spread-bps 5 --slippage-bps 5 --holdout 12
# scorecard prints to stdout; SIM_equity.png/.html + SIM_metrics.json land in the dated outdir
```

---

## 2. Pre-registration (write this BEFORE looking at §3)

Recording expectations first is what separates a result from a story fitted after the
fact. Fill this in, then run, then don't edit it. If you find yourself wanting to revise
the prior after seeing the curves, that is the exact bias this section exists to catch.

- **Prior:** I expect the strategy to ___ (beat / not beat) BH after costs, because ___.
- **What would change my mind:** a positive result is credible only if ___ (e.g. it
  survives the held-out slice, N is small, and the leakage re-check passes).
- **What I'll treat as a red flag:** ___ (e.g. excess Sharpe > 1.0 out-of-sample on a
  single liquid large-cap — more likely a bug than an edge).

---

## 3. Readings

For each ticker, paste the scorecard the tool emits, then the equity-curve overlay.
Do **not** summarize selectively — show every ticker you ran, winners and losers, or
state exactly which were excluded and why.

### 3.1 `TICKER` — out-of-sample

```
SCORECARD — TICKER (after costs, out-of-sample)
  Beat buy-and-hold?   ___  (excess CAGR: ___%, excess Sharpe: ___)
  Beat risk-free?      ___  (excess CAGR: ___%)
  Strategy CAGR:       ___%  | Sharpe ___
  Max drawdown:        ___%
  Turnover (ann.):     ___x
  Variants tried:      ___
  Held-out period:     beat BH=___, beat RF=___, CAGR ___% over __ mo (touched once)
  ⚠ Educational demo — not financial advice.
```

_(If the run covers < ~24 months the tool prepends a `⚠ SMALL SAMPLE` line — annualized
CAGR/Sharpe are unreliable there; widen the window before reporting.)_

_Equity curve: `TICKER_SIM_equity.png` / `.html` — strategy vs BH vs RF._

**Reading:** _2–4 sentences. What does the curve actually show? Where did the strategy
diverge from BH and why (sizing pulled it out of a drawdown? costs bled it during
chop?)? Resist narrating noise as skill._

_(Repeat 3.1 per ticker.)_

### 3.2 Aggregate

| Ticker | Beat BH? | Beat RF? | Excess Sharpe | Max DD | Turnover |
|---|---|---|---|---|---|
| | | | | | |

---

## 4. Interpretation

Answer these directly and without spin:

1. **Did it beat both benchmarks after costs, out of sample?** Yes / No / Mixed — and
   on how many of how many tickers.
2. **If mostly NO** — good. State that this is the expected outcome for a retail
   monthly timing strategy, and that the instrument producing a credible null *is* the
   result. Name the mechanism that ate any apparent gross signal (costs, wide intervals
   dwarfing the expected move, turnover).
3. **If any YES** — apply the suspicion checklist (§5) before believing it. A surprising
   positive is more likely a bug than an edge.
4. **What the prediction intervals implied.** If the 80% band routinely dwarfed the
   one-step expected move, say so — that is *why* sizing stayed small and *why* a
   well-calibrated forecast still wasn't a tradeable edge. This is the most important
   conceptual takeaway and worth stating plainly.

---

## 5. Suspicion checklist (run only if a result looks good)

A positive out-of-sample result is a trigger for scrutiny, not celebration. Before
reporting any "beat both benchmarks":

- [ ] **Sentiment timing re-check (by hand).** This layer uses a *price-only* signal in
      the backtest precisely to avoid sentiment lookahead — confirm no news-derived
      input leaked in. If you wire sentiment into the simulated signal, verify news
      feeding rebalance date *t* was published ≤ *t*, including how the NewsAPI window
      and SQLite caching interact. This is the leak the harness test can't catch.
- [ ] **Variant count.** How many configs were tried to find this one? Report N. The
      best of N is overfit until the held-out slice says otherwise.
- [ ] **Held-out slice.** Does the once-touched final period agree? If the edge lives
      only in the tuned window, it isn't an edge.
- [ ] **Liquidity/cost realism.** Were costs conservative enough for the names traded?
      Re-run with higher `--slippage-bps`; does the edge survive?
- [ ] **Zero-edge control still passes?** Re-confirm `tests/test_strategy.py`'s
      random-walk synthetic still shows no edge — guards against a sim change that
      flatters noise.
- [ ] **Single ticker vs universe.** If cross-sectional, restate the survivorship
      caveat: yfinance lists only survivors, biasing results upward.

---

## 6. Limitations (do not omit)

- **Survivorship bias** — the universe is currently-listed names only; cross-sectional
  results are upward-biased. The real fix (point-in-time / delisting-aware universe) is
  gated Phase 5. Single-ticker studies are less exposed but not immune. **If this study
  is cross-sectional, this caveat is load-bearing — move it to the top of §4 and do not
  present stock-picking claims as unbiased.**
- **Monthly cadence** — short-horizon dynamics are out of scope; conclusions don't
  transfer to daily/weekly trading.
- **Cost model** — a simplified bps model; real fills, market impact, and borrow costs
  differ.
- **Single regime** — the OOS window covers a limited set of market conditions; results
  may not generalize across regimes.
- **Not financial advice** — paper-trading study; if live recommendations were ever
  published for others to act on, investment-adviser regulatory considerations apply.

---

## 7. Conclusion

_3–5 sentences. State the verdict, restate that a null after costs is the correct and
expected outcome, and name the project's actual contribution: a rigorous, cost-aware,
leakage-checked, benchmark-honest instrument that reports what it finds — including, and
especially, when what it finds is "no edge." Point to the next gated step only if you
intend to take it._
