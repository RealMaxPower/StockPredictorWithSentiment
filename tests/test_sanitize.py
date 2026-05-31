"""Input-hardening tests: ticker validation (path-traversal) and markdown safety."""

from __future__ import annotations

import pytest

from stockpredictor import pipeline
from stockpredictor.sanitize import escape_markdown, safe_url, sanitize_ticker


class TestSanitizeTicker:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("aapl", "AAPL"),
            (" msft ", "MSFT"),
            ("brk.b", "BRK.B"),  # dotted class shares are valid
            ("rds-a", "RDS-A"),  # hyphenated shares are valid
            ("reliance.ns", "RELIANCE.NS"),  # international suffix
            ("^gspc", "^GSPC"),  # index symbol
            ("gc=f", "GC=F"),  # futures symbol
            ("V", "V"),
        ],
    )
    def test_normalizes_valid_symbols(self, raw, expected):
        assert sanitize_ticker(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "../../etc/passwd",  # path traversal
            "..",
            "a/b",  # path separator
            r"a\b",
            ".env",  # leading dot
            "-rf",  # leading hyphen
            "AAPL_NEWS",  # underscore not allowed
            "a b",  # whitespace inside
            "ABCDEFGHIJKLMNOP",  # 16 valid chars, over the 15-char bound
            "",
            "   ",
        ],
    )
    def test_rejects_invalid_symbols(self, raw):
        with pytest.raises(ValueError):
            sanitize_ticker(raw)

    def test_run_ticker_rejects_path_traversal(self, cfg):
        # The pipeline core must reject before the symbol becomes a file name.
        with pytest.raises(ValueError):
            pipeline.run_ticker("../../tmp/evil", cfg)


def test_escape_markdown_neutralizes_link_breakout():
    evil = "Buy now](http://evil.test) ![pwn](http://evil.test/x"
    out = escape_markdown(evil)
    assert "](" not in out  # brackets and parens are escaped
    assert r"\]" in out and r"\(" in out


def test_escape_markdown_handles_none():
    assert escape_markdown(None) == ""


class TestSafeUrl:
    @pytest.mark.parametrize(
        "url",
        ["https://example.com/a", "http://news.test/path?q=1&x=2"],
    )
    def test_allows_clean_http(self, url):
        assert safe_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ftp://example.com/x",
            "https://e.test/a b",  # whitespace
            "https://e.test/a)b",  # paren would close the link
            "https://e.test/<x>",  # angle brackets
            "//example.com",  # scheme-relative
            None,
            "",
            "#",
        ],
    )
    def test_rejects_unsafe(self, url):
        assert safe_url(url) is None
