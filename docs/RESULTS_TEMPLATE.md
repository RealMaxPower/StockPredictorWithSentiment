# Results: Does the Simulated Betting Layer Beat Buy-and-Hold After Costs?

> ⚠️ **Educational demo — not financial advice.** This is a paper-trading study. No
> real orders were placed. A null result (no durable edge after costs) is the
> expected and honest outcome, not a defect.

> **How to use this template:** copy it to `docs/RESULTS.md` (or a dated file),
> fill §2 *before* looking at any curves, run the studies, paste each scorecard into
> §3 as you go, then interpret. The section order is the discipline — pre-register,
> read everything, interpret, then a limitations section you may not omit. Do not
> edit §2 after seeing §3.

**TL;DR (fill in last):** _State the findings without assuming the prior was correct.
Report N tickers attempted, M completed, and all failures or incomplete histories.
Separate descriptive walk-forward performance from independently protected validation._

---

## 1. What was tested

| Item | Value |
|---|---|
| Commit / source hashes | `_______` _(record the commit, package hash, and script hash)_ |
| Environment | Python and dependency versions from `summary.json` |
| Input provenance | Provider, acquisition time, adjusted-price convention, CSV hashes |
| Input artifacts | Path to retained `prices/` snapshots and `summary.json` |
| Tickers studied | `_______` |
| Study type | single-ticker timing _(still subject to survivor selection)_ / cross-sectional |
| In-sample window (tuning) | `____-__-__` → `____-__-__` |
| Requested price window | `[____-__-__, ____-__-__)` _(end exclusive)_ |
| **Actual evaluation window** | first and final equity timestamps after warmup, per ticker |
| Final-period descriptive slice | final `--final-period` months (default 12), also included in full results |
| Protected final evaluation | none / separately controlled dataset and documented release procedure |
| Rebalance cadence | monthly |
| Sizing method(s) | vol-targeting _(default)_ / fractional Kelly (λ = 0.25 default) |
| Cost assumptions | commission 1 bps, spread 5 bps, slippage 5 bps _(defaults; override with flags)_ |
| Starting capital / fixed fee | record both currency amounts from configuration |
| Risk-free rate used | 4.0% _(default constant; not a point-in-time T-bill series)_ |
| Variants tried (total) | N = ___ / unknown _(include experiments outside this run or local store)_ |
| Configuration identity | full configuration, variant ID, and monthly data fingerprint |

State the in-sample vs out-of-sample split explicitly. Numbers in §3 are **out-of-sample
only**. In-sample numbers, if shown at all, go in an appendix clearly labeled as such.

> The simulator is out-of-sample *by construction* — the weight at month *t* uses only
> prices ≤ *t* and earns the realized *t→t+1* return. "In-sample" here means any window
> you used to *choose* a variant (sizing method, cost params, thresholds); the reported
> numbers must come from a window you did **not** tune on.

The automatic final-period slice is descriptive: it overlaps the headline scorecard
and is visible on every rerun. Do not call it independent, untouched, or once-only.
To make a protected-validation claim, arrange that evaluation **outside this tool**:
freeze the code, configuration, universe, and success criterion; restrict access to the
evaluation data/results; record who released them and when. Previously viewed periods
cannot be made unseen by renaming them. Otherwise state that independent validation
has not been performed.

Reproduce a study from retained adjusted-price CSVs with:

```bash
python -m scripts.regenerate_results \
  --prices-dir /path/to/adjusted-price-snapshots --outdir stock_plots/new-study \
  --tickers TICKER --start YYYY-MM-DD --end YYYY-MM-DD \
  --sizing vol --rf-rate 0.04 \
  --commission-bps 1 --spread-bps 5 --slippage-bps 5 --final-period 12
# summary.json includes every ticker, including errors; per-ticker JSON and input CSVs are retained
```

---

## 2. Pre-registration (write this BEFORE looking at §3)

Recording expectations first is what separates a result from a story fitted after the
fact. Fill this in, then run, then don't edit it. If you find yourself wanting to revise
the prior after seeing the curves, that is the exact bias this section exists to catch.

- **Prior:** I expect the strategy to ___ (beat / not beat) BH after costs, because ___.
- **What would change my mind:** a positive result is credible only if ___ (e.g. it
  survives separately protected evaluation, all experiments are disclosed, and the
  leakage and accounting checks pass).
- **What I'll treat as a red flag:** ___ (e.g. excess Sharpe > 1.0 out-of-sample on a
  single liquid large-cap — more likely a bug than an edge).

---

## 3. Readings

For each ticker, report the metrics from the retained artifact and its source identity.
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
  Final-period performance: beat BH=___, beat RF=___, CAGR ___% over __ mo
    (included in full-period results; not an untouched holdout)
  ⚠ Educational demo — not financial advice.
```

_(If the run covers < ~24 months the tool prepends a `⚠ SMALL SAMPLE` line — annualized
CAGR/Sharpe are unreliable there; widen the window before reporting.)_

_Equity curves: `equity`, `benchmark_bh`, and `benchmark_rf` in the per-ticker JSON.
Optional plots must be generated from the same retained inputs and configuration._

**Reading:** _2–4 sentences. What does the curve actually show? Where did the strategy
diverge from BH and why (sizing pulled it out of a drawdown? costs bled it during
chop?)? Resist narrating noise as skill._

_(Repeat 3.1 per ticker.)_

### 3.2 Aggregate

| Ticker | Status / actual dates | Beat BH? | Beat RF? | Excess Sharpe | Max DD | Turnover / failure reason |
|---|---|---|---|---|---|---|
| | | | | | | |

Include failed tickers as rows. Aggregate denominators must distinguish attempted
from completed studies; a missing result is not a win or a loss. Undefined metrics
(`null`) must remain unavailable rather than being replaced with zero.

---

## 4. Interpretation

Answer these directly and without spin:

1. **Did it beat both benchmarks after costs, out of sample?** Yes / No / Mixed — and
   on how many of how many tickers.
2. **If mostly NO** — explain what the evidence supports and its limits. A null
   result alone does not validate the instrument or prove that no edge exists. Check
   accounting, temporal alignment, and controls for null results as well as positives.
3. **If any YES** — apply the suspicion checklist (§5) before believing it. A surprising
   positive is more likely a bug than an edge.
4. **What the prediction intervals implied.** If the 80% band routinely dwarfed the
   one-step expected move, say so — that is *why* sizing stayed small and *why* a
   well-calibrated forecast still wasn't a tradeable edge. This is the most important
   conceptual takeaway and worth stating plainly.

---

## 5. Validation checks

Apply the accounting and timing checks regardless of the sign of the result.
Scrutinize positive results further before reporting an edge:

- [ ] **Sentiment timing re-check (by hand).** This layer uses a *price-only* signal in
      the backtest precisely to avoid sentiment lookahead — confirm no news-derived
      input leaked in. If you wire sentiment into the simulated signal, verify news
      feeding rebalance date *t* was published ≤ *t*, including how the NewsAPI window
      and SQLite caching interact. This is the leak the harness test can't catch.
- [ ] **Variant count.** How many configs were tried to find this one? Report N. The
      best of N is subject to selection bias; unknown history must be labeled unknown.
- [ ] **Independent evaluation.** Was a separate protected procedure actually used?
      Record the frozen configuration and release evidence. Agreement with the
      repeatedly viewed final-period slice is not independent confirmation.
- [ ] **Accounting and data checks.** Confirm trades use drifted holdings, fees use
      actual capital, monthly timestamps are complete, and no input gap was hidden.
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

_3–5 sentences. State the observed result, missing evidence, and whether independent
validation occurred. Do not promote a descriptive final-period result to a protected
holdout or infer certainty from a null. Identify any next experiment before viewing its
results._
