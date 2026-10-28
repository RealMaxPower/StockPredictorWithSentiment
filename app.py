"""
Streamlit dashboard for stockpredictor.

Run with:  streamlit run app.py

Wraps the same ``pipeline.run_ticker`` core the CLI uses, so the dashboard and the
command line never diverge. Works without a NEWSAPI_KEY (forecasts only / "demo"
mode); set the key in the environment or in .streamlit/secrets.toml for news.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os

import pandas as pd
import streamlit as st

from stockpredictor import config, evaluation, forecast, news, plotting
from stockpredictor.pipeline import record_simulation, run_simulation, run_ticker
from stockpredictor.reproducibility import code_version
from stockpredictor.sanitize import escape_markdown, safe_url, sanitize_ticker
from stockpredictor.store import Store

PRESETS = {
    "Magnificent Seven": "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA",
    "FAANG": "META,AAPL,AMZN,NFLX,GOOGL",
    "Semiconductors": "NVDA,AVGO,AMD,INTC,QCOM,TSM",
    "AI & data": "NVDA,MSFT,GOOGL,PLTR,AMD,AVGO",
    "Big banks & payments": "JPM,V,MA,BAC,GS,AXP",
    "Enterprise software": "MSFT,ORCL,CRM,ADBE,IBM,NOW",
    "Dividend blue chips": "KO,PG,JNJ,XOM,CVX,PEP",
    "Meme stocks": "GME,AMC,BB,PLTR,RBLX",
}

# Tab labels show "TICKER · Company" when the company name is known.
_TAB_CSS = """
<style>
button[data-baseweb="tab"] { padding: 10px 18px; }
button[data-baseweb="tab"] p { font-size: 1.05rem; font-weight: 600; }
div[data-baseweb="tab-list"] { gap: 6px; flex-wrap: wrap; }
</style>
"""


def _tab_label(ticker: str) -> str:
    name = news.ticker_to_company_name(ticker)
    return f"{ticker} · {name}" if name != ticker else ticker


def _news_client():
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        try:
            key = st.secrets.get("NEWSAPI_KEY")
        except Exception:  # noqa: BLE001 - no secrets file is fine
            key = None
    if not key:
        return None
    try:
        from newsapi import NewsApiClient

        return NewsApiClient(api_key=key)
    except Exception:  # noqa: BLE001
        return None


@st.cache_data(show_spinner=True, ttl=3600, max_entries=128)
def _run(
    ticker: str,
    start: str,
    end: str,
    page_size: int,
    sentiment_enabled: bool,
    has_key: bool,
    implementation: str,
):
    """Cached wrapper. ``has_key`` is part of the cache key so toggling it re-runs."""
    cfg = config.AppConfig(
        start=start, end=end, page_size=page_size, sentiment_enabled=sentiment_enabled
    )
    result = run_ticker(ticker, cfg, news_client=_news_client() if has_key else None)
    return result, cfg


@st.cache_data(show_spinner=False, ttl=3600, max_entries=64)
def _simulate(ticker: str, monthly: pd.Series, cfg: config.AppConfig, implementation: str):
    """Cache pure computation; recording experiments belongs outside this function."""
    return run_simulation(ticker, cfg, monthly=monthly)


def _render_simulation(ticker: str, result, cfg, sizing: str) -> None:
    """Render the paper-trading simulation: equity overlay, scorecard, overfit warning."""
    sim_cfg = dataclasses.replace(cfg, sizing_method=sizing)
    try:
        report = _simulate(ticker, result.monthly, sim_cfg, code_version())
    except Exception as exc:  # noqa: BLE001 - surface, don't crash the dashboard
        st.warning(f"Simulation unavailable for {ticker}: {exc}")
        return

    if sim_cfg.use_cache:
        try:
            with Store(sim_cfg.db_path) as store:
                logged = st.session_state.setdefault("logged_simulations", set())
                key = (ticker, report.variant_id, sim_cfg.db_path)
                if key not in logged:
                    record_simulation(report, sim_cfg, store)
                    if report.variants_tried is not None:
                        logged.add(key)
                else:
                    report.variants_tried = store.count_simulations(ticker) or None
        except Exception as exc:  # noqa: BLE001 - results survive optional history failures
            st.warning(f"Experiment history unavailable: {exc}")

    for warning in report.warnings:
        if warning != config.DISCLAIMER:
            st.warning(warning)
    st.subheader("Paper-trading simulation (after costs, out-of-sample)")
    if report.scorecard.n_periods < config.MIN_RELIABLE_PERIODS:
        st.warning(
            f"⚠ Small sample: only {report.scorecard.n_periods} rebalances. Annualized "
            f"CAGR/Sharpe are extrapolated from too few points to trust — widen the date "
            f"range (≥ ~{config.MIN_RELIABLE_PERIODS} months, ideally several years)."
        )
    try:
        st.plotly_chart(plotting.build_equity_figure(report.result, ticker), width="stretch")
    except ImportError:
        st.info("Install plotly for the equity overlay (`pip install plotly`).")

    card = report.scorecard
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Beat buy & hold?",
        "YES" if card.beat_buy_and_hold else "NO",
        f"{card.excess_cagr_vs_bh * 100:+.1f}% CAGR",
    )
    c2.metric(
        "Beat risk-free?",
        "YES" if card.beat_risk_free else "NO",
        f"{card.excess_cagr_vs_rf * 100:+.1f}% CAGR",
    )
    c3.metric(
        "Max drawdown", f"{card.max_drawdown * 100:.1f}%", f"turnover {card.turnover_annual:.1f}x"
    )
    st.code(
        evaluation.format_scorecard(
            card, ticker=ticker, variants_tried=report.variants_tried, holdout=report.holdout
        ),
        language="text",
    )
    st.warning(
        "⚠ Multiple-testing caution: trying many tickers, date ranges, or sizing "
        "methods and keeping the best is **overfitting**. Treat a single green "
        "scorecard with deep skepticism. Final-period performance is part of the full "
        "scorecard and is not independent validation. "
        "For monthly single-name timing, **no durable edge after costs is the "
        "expected, honest result.**"
    )


def _render_result(
    ticker: str, result, cfg, *, simulate: bool = False, sizing: str = "vol"
) -> None:
    """Render one ticker's chart, metrics, backtest, and headlines."""
    col_chart, col_meta = st.columns([3, 1])
    with col_chart:
        try:
            fig = plotting.build_plotly_figure(
                result.monthly,
                result.forecast,
                result.adjusted,
                ticker,
                result.sentiment.label(),
            )
            st.plotly_chart(fig, width="stretch")
        except ImportError:
            st.warning("Install plotly for the interactive chart (`pip install plotly`).")

    with col_meta:
        change = (result.forecast.point.iloc[-1] / result.monthly.iloc[-1] - 1) * 100
        st.metric(f"{cfg.horizon}-month projected change", f"{change:+.1f}%")
        st.metric(
            "News sentiment",
            result.sentiment.label(),
            f"{result.sentiment.mean:+.2f} (n={result.sentiment.n_articles})",
        )
        hw = result.backtest.get("holt_winters", {})
        sn = result.backtest.get("seasonal_naive", {})
        if hw.get("mase") is not None and hw["mase"] == hw["mase"]:
            verdict = "comparison unavailable (incomplete folds)"
            if forecast.comparable_mase(hw, sn):
                verdict = "beats baseline" if hw["mase"] < sn["mase"] else "worse"
            st.metric(
                "Backtest MASE (vs seasonal-naive)",
                f"{hw['mase']:.2f}",
                verdict,
            )

    if result.warnings:
        st.warning("Data-quality notes: " + "; ".join(result.warnings))

    if result.backtest:
        st.subheader("Backtest (lower MASE is better)")
        st.caption(
            "MASE scales error by training seasonal-naive error; compare models on the same folds."
        )
        st.dataframe(
            {k: {m: round(v, 3) for m, v in d.items()} for k, d in result.backtest.items()}
        )

    if result.articles:
        st.subheader("Headlines")
        for art in result.articles:
            score = art.get("sentiment", 0.0)
            emoji = "🟢" if score > 0.05 else "🔴" if score < -0.05 else "⚪"
            # News titles/URLs are untrusted: escape markdown and allow only
            # http(s) links so a headline can't break out or inject a script URL.
            title = escape_markdown(art.get("title") or "(untitled)")
            source = escape_markdown(art.get("source") or "unknown")
            url = safe_url(art.get("url"))
            label = f"[{title}]({url})" if url else title
            st.markdown(f"{emoji} **{label}** — *{source}* ({score:+.2f})")

    if simulate:
        _render_simulation(ticker, result, cfg, sizing)


def _comparison_table(results: dict) -> pd.DataFrame:
    """One row per ticker: projected change, sentiment, and backtest MASE."""
    rows = []
    for tk, (res, cfg) in results.items():
        change = (res.forecast.point.iloc[-1] / res.monthly.iloc[-1] - 1) * 100
        mase = res.backtest.get("holt_winters", {}).get("mase", float("nan"))
        rows.append(
            {
                "ticker": tk,
                "company": news.ticker_to_company_name(tk),
                f"{cfg.horizon}mo change %": round(change, 1),
                "sentiment": res.sentiment.label(),
                "sent (effective)": round(res.sentiment.effective, 3),
                "backtest MASE": round(mase, 3) if mase == mase else None,
            }
        )
    return pd.DataFrame(rows).set_index("ticker")


def main() -> None:
    st.set_page_config(page_title="Stock Predictor with Sentiment", layout="wide")
    st.markdown(_TAB_CSS, unsafe_allow_html=True)
    st.title("📈 Stock Predictor with Sentiment")
    st.caption(config.DISCLAIMER)

    has_key = bool(os.getenv("NEWSAPI_KEY"))
    if not has_key:
        st.info(
            "No `NEWSAPI_KEY` set — running in **forecast-only** mode (no sentiment). "
            "Add a free key from [newsapi.org](https://newsapi.org) to enable news."
        )

    with st.sidebar:
        st.header("Settings")
        preset = st.selectbox("Preset watchlist", ["(custom)"] + list(PRESETS))
        default_tickers = PRESETS[preset] if preset in PRESETS else "AAPL"
        tickers_raw = st.text_input("Tickers (comma-separated)", value=default_tickers)
        today = dt.date.today()
        # Default to ~10 years: long enough for the seasonal model AND for the
        # paper-trading simulation's annualized metrics to be meaningful (a short
        # window yields only a handful of rebalances and noisy CAGR/Sharpe).
        start = st.date_input("Start", value=today - dt.timedelta(days=365 * 10)).isoformat()
        end = st.date_input("End", value=today).isoformat()
        page_size = st.slider("Headlines", 1, 20, config.PAGE_SIZE)
        sentiment_enabled = st.checkbox("Apply sentiment tilt", value=True)
        st.divider()
        simulate = st.checkbox(
            "Paper-trading simulation (after costs)",
            value=False,
            help="Cost-aware, out-of-sample backtest vs buy-and-hold and the risk-free rate. "
            "Educational demo — not financial advice.",
        )
        sizing = st.selectbox("Position sizing", ["vol", "kelly"], disabled=not simulate)
        go = st.button("Run forecast", type="primary")

    if not go and not st.session_state.get("forecast_results"):
        st.write("Set parameters in the sidebar and click **Run forecast**.")
        return

    if go:
        tickers: list[str] = []
        invalid: list[str] = []
        for raw in tickers_raw.split(","):
            if not raw.strip():
                continue
            try:
                tickers.append(sanitize_ticker(raw))
            except ValueError:
                invalid.append(raw.strip())
        if invalid:
            st.warning("Ignored invalid ticker(s): " + ", ".join(invalid))
        if not tickers:
            st.warning("Enter at least one valid ticker.")
            return

        results: dict = {}
        progress = st.progress(0.0, text="Running forecasts…")
        for i, tk in enumerate(tickers):
            try:
                results[tk] = _run(
                    tk, start, end, page_size, sentiment_enabled, has_key, code_version()
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not run {tk}: {exc}")
            progress.progress((i + 1) / len(tickers), text=f"Ran {tk}")
        progress.empty()

        st.session_state["forecast_results"] = results

    results = st.session_state.get("forecast_results", {})
    if not results:
        return

    st.caption(
        "Showing the last completed forecast. Click Run forecast to apply ticker, date, or news changes."
    )
    if len(results) == 1:
        tk, (res, cfg) = next(iter(results.items()))
        _render_result(tk, res, cfg, simulate=simulate, sizing=sizing)
        return

    st.subheader("Comparison")
    st.dataframe(_comparison_table(results), width="stretch")
    labels = [_tab_label(tk) for tk in results]
    for tab, tk in zip(st.tabs(labels), results, strict=True):
        with tab:
            res, cfg = results[tk]
            _render_result(tk, res, cfg, simulate=simulate, sizing=sizing)


if __name__ == "__main__":
    main()
