"""
News fetching via NewsAPI.

Network/retry only — scoring lives in ``sentiment`` so this stays testable with a
mocked client. Two key fixes over the original:

- The news window is anchored to the forecast origin (``end_date``), not
  "last 30 days from now", so sentiment is causally aligned with the forecast.
- ``datetime.utcnow()`` (deprecated) is replaced with timezone-aware ``now``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import config
from .sanitize import scrub

logger = logging.getLogger("stockpredictor.news")

# NewsAPI free tier only serves roughly the last month of articles.
_FREE_TIER_DAYS = 30

_COMPANY_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google",
    "GOOG": "Google",
    "AMZN": "Amazon",
    "TSLA": "Tesla",
    "META": "Meta",
    "NVDA": "NVIDIA",
    "NFLX": "Netflix",
    "BA": "Boeing",
    "JPM": "JPMorgan",
    "JNJ": "Johnson & Johnson",
    "V": "Visa",
    "PG": "Procter & Gamble",
    "UNH": "UnitedHealth",
    "HD": "Home Depot",
    "MA": "Mastercard",
    "PFE": "Pfizer",
    "DIS": "Disney",
    "VZ": "Verizon",
    "ADBE": "Adobe",
    "KO": "Coca-Cola",
    "PEP": "PepsiCo",
    "T": "AT&T",
    "CVX": "Chevron",
    "WMT": "Walmart",
    "XOM": "ExxonMobil",
    "INTC": "Intel",
    "IBM": "IBM",
    "ORCL": "Oracle",
    "CSCO": "Cisco",
    "CRM": "Salesforce",
    "AVGO": "Broadcom",
    "GME": "GameStop",
    "AMC": "AMC Entertainment",
    "BB": "BlackBerry",
    "NOK": "Nokia",
    "PLTR": "Palantir",
    "RBLX": "Roblox",
    "AMD": "AMD",
    "QCOM": "Qualcomm",
    "TSM": "Taiwan Semiconductor",
    "BAC": "Bank of America",
    "GS": "Goldman Sachs",
    "AXP": "American Express",
    "NOW": "ServiceNow",
}


def ticker_to_company_name(ticker: str) -> str:
    """Map a ticker to a company name for better news search; passthrough if unknown."""
    return _COMPANY_NAMES.get(ticker.upper(), ticker)


def build_query(ticker: str) -> str:
    company = ticker_to_company_name(ticker.upper())
    return f'"{company}" OR {ticker.upper()}'


def _news_window(end_date: str | None, lookback_days: int) -> tuple[str, str]:
    """[end - lookback, end] in YYYY-MM-DD, anchored to the forecast origin."""
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end_dt = datetime.now(timezone.utc).date()
    start_dt = end_dt - timedelta(days=lookback_days)
    return start_dt.isoformat(), end_dt.isoformat()


def _normalize(art: dict) -> dict[str, object]:
    return {
        "title": art.get("title") or "",
        "description": art.get("description") or "",
        "url": art.get("url"),
        "source": (art.get("source") or {}).get("name"),
        "publishedAt": art.get("publishedAt"),
    }


def fetch_articles(
    client,
    ticker: str,
    end_date: str | None = None,
    cfg: config.AppConfig | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[dict[str, object]]:
    """
    Fetch normalized article dicts (no scoring) with retry/backoff. Tries the
    anchored date window first, then falls back to no date filter if the plan
    rejects the range (NewsAPI free tier ~30 days). Returns [] on exhaustion.
    """
    cfg = cfg or config.AppConfig()
    query = build_query(ticker)
    # Untrusted ticker/query are echoed in log lines below; scrub once for logging.
    log_ticker, log_query = scrub(ticker), scrub(query)
    win_from, win_to = _news_window(end_date, cfg.news_lookback_days)

    days_old = (datetime.now(timezone.utc).date() - datetime.fromisoformat(win_to).date()).days
    if days_old > _FREE_TIER_DAYS:
        logger.warning(
            "%s: requested news window ends %s (%d days ago) — NewsAPI free tier "
            "(~%d days) likely cannot serve it; will degrade to no-news.",
            log_ticker,
            win_to,
            days_old,
            _FREE_TIER_DAYS,
        )

    logger.info("%s: news query %s, window %s..%s", log_ticker, log_query, win_from, win_to)
    tried_without_dates = False

    for attempt in range(cfg.max_retries):
        try:
            if attempt > 0:
                wait = 2**attempt
                logger.warning("%s: retry %d in %ds", log_ticker, attempt, wait)
                sleeper(wait)

            kwargs = {
                "q": query,
                "language": "en",
                "sort_by": "relevancy",
                "page_size": cfg.page_size,
            }
            if not tried_without_dates:
                kwargs["from_param"] = win_from
                kwargs["to"] = win_to

            resp = client.get_everything(**kwargs)

            if resp.get("code"):
                code, msg = resp.get("code", ""), resp.get("message", "")
                logger.warning("%s: NewsAPI error (%s): %s", log_ticker, scrub(code), scrub(msg))
                if (
                    code == "parameterInvalid"
                    and "far in the past" in msg
                    and not tried_without_dates
                ):
                    tried_without_dates = True
                    continue
                if attempt == cfg.max_retries - 1:
                    return []
                continue

            articles = (resp or {}).get("articles", []) or []
            if not articles:
                if not tried_without_dates:
                    tried_without_dates = True
                    continue
                if attempt < cfg.max_retries - 1:
                    continue
            else:
                logger.info("%s: fetched %d articles", log_ticker, len(articles))
                return [_normalize(a) for a in articles]

        except Exception as exc:  # noqa: BLE001 - networking is best-effort
            msg = str(exc)
            logger.warning("%s: attempt %d failed: %s", log_ticker, attempt + 1, scrub(msg))
            if (
                "parameterInvalid" in msg or "too far in the past" in msg
            ) and not tried_without_dates:
                tried_without_dates = True
                continue
            if attempt == cfg.max_retries - 1:
                logger.error("%s: all news attempts failed; using no news", log_ticker)
                return []

    return []
