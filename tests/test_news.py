"""Tests for NewsAPI retries and strict publication-time alignment."""

from __future__ import annotations

import pytest

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


def test_unavailable_historical_window_returns_no_news(cfg):
    c = Client([{"code": "parameterInvalid", "message": "too far in the past"}, ARTS])
    out = news.fetch_articles(c, "AAPL", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert out == []
    assert len(c.calls) == 1
    assert c.calls[0]["from_param"] == "2024-12-01"
    assert c.calls[0]["to"] == "2024-12-31"


def test_empty_window_never_falls_back_to_current_news(cfg):
    c = Client([{"articles": []}, ARTS])
    out = news.fetch_articles(c, "MSFT", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert out == []
    assert len(c.calls) == 1


def test_rate_limited_exhausts_to_empty(cfg):
    c = Client([{"code": "rateLimited", "message": "slow down"}])
    out = news.fetch_articles(c, "NVDA", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert out == []
    assert len(c.calls) == cfg.max_retries
    assert all(call["from_param"] == "2024-12-01" for call in c.calls)
    assert all(call["to"] == "2024-12-31" for call in c.calls)


def test_normalized_article_keys(cfg):
    c = Client([ARTS])
    out = news.fetch_articles(c, "TSLA", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert set(out[0]) == {"title", "description", "url", "source", "publishedAt"}


@pytest.mark.parametrize(
    ("published", "accepted"),
    [
        ("2024-12-01T00:00:00Z", True),
        ("2024-12-30T23:59:59Z", True),
        ("2024-12-31T00:30:00+01:00", True),  # December 30 in UTC
        ("2024-11-30T23:59:59Z", False),
        ("2024-12-31T00:00:00Z", False),  # exclusive forecast boundary
        ("2024-12-30T23:30:00-01:00", False),  # December 31 in UTC
        ("2026-10-26T00:00:00Z", False),
        ("2024-12-20T00:00:00", False),  # unknown timezone
        ("invalid", False),
        (None, False),
        (42, False),
    ],
)
def test_publication_timestamp_enforced_locally(cfg, published, accepted):
    article = {**ARTS["articles"][0], "publishedAt": published}
    c = Client([{"articles": [article]}])
    out = news.fetch_articles(c, "AAPL", end_date="2024-12-31", cfg=cfg, sleeper=NOOP)
    assert bool(out) is accepted


def test_sdk_range_exception_does_not_retry_without_dates(cfg):
    class RejectingClient:
        calls = 0

        def get_everything(self, **kw):
            self.calls += 1
            raise RuntimeError("parameterInvalid: request is too far in the past")

    client = RejectingClient()
    assert news.fetch_articles(client, "AAPL", "2024-12-31", cfg, NOOP) == []
    assert client.calls == 1
