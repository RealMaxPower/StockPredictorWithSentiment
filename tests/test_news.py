"""Tests for the NewsAPI retry/date-fallback state machine and window anchoring."""

from __future__ import annotations

from stockpredictor import news

NOOP = lambda _s: None  # noqa: E731
ARTS = {
    "articles": [
        {
            "title": "X beats earnings",
            "description": "strong",
            "url": "u",
            "source": {"name": "S"},
            "publishedAt": "2024-12-20T00:00:00Z",
        },
    ]
}


class Client:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_everything(self, **kw):
        self.calls.append(kw)
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


def test_window_anchored_to_end_date():
    assert news._news_window("2024-12-31", 30) == ("2024-12-01", "2024-12-31")


def test_company_map_dedup_and_lookup():
    assert list(news._COMPANY_NAMES).count("NFLX") == 1
    assert news.ticker_to_company_name("NFLX") == "Netflix"
    assert news.ticker_to_company_name("ZZZZ") == "ZZZZ"  # passthrough


def test_retry_drops_dates_on_far_in_past(cfg):
    c = Client([{"code": "parameterInvalid", "message": "too far in the past"}, ARTS])
    out = news.fetch_articles(c, "AAPL", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert len(out) == 1
    assert "from_param" not in c.calls[1]  # second call dropped the date filter


def test_empty_then_retry_without_dates(cfg):
    c = Client([{"articles": []}, ARTS])
    out = news.fetch_articles(c, "MSFT", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert len(out) == 1


def test_rate_limited_exhausts_to_empty(cfg):
    c = Client([{"code": "rateLimited", "message": "slow down"}])
    out = news.fetch_articles(c, "NVDA", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert out == []


def test_normalized_article_keys(cfg):
    c = Client([ARTS])
    out = news.fetch_articles(c, "TSLA", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert set(out[0]) == {"title", "description", "url", "source", "publishedAt"}
