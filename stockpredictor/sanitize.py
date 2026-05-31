"""
Input-hardening helpers for untrusted strings. Centralized so the CLI, the
dashboard, and the pipeline all validate identically.

Two concerns:

- ``sanitize_ticker`` stops a user-supplied symbol from escaping an output
  directory when it is interpolated into a file name (path traversal): a ticker
  is the key for ``{ticker}_forecasts.png`` etc., so ``../../x`` must never get
  that far.
- ``escape_markdown`` / ``safe_url`` keep untrusted news titles and links from
  breaking out of the Streamlit markdown they are rendered into.
"""

from __future__ import annotations

import re

# Real symbols use letters, digits, dots, hyphens, and (for indices/futures/forex)
# "^" and "=": AAPL, BRK.B, RDS-A, RELIANCE.NS, ^GSPC, GC=F, EURUSD=X. The first
# character must be alphanumeric or "^", so a value can never start with "." or
# "-" — in particular ".." and "/.." are rejected. Crucially the class excludes
# the path separators "/" and "\", so a symbol can never escape its output dir
# when interpolated into a file name.
_TICKER_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.\-^=]{0,14}$")

# Markdown delimiters that could let untrusted text break out of a link label,
# inject emphasis, or smuggle an image/link of its own.
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!~|<>])")

# Characters that must not appear in a markdown link target, since they would
# close the "(...)" or otherwise change where the link points.
_URL_FORBIDDEN = set("<> \t\r\n\"'()")


def sanitize_ticker(raw: str) -> str:
    """Normalize and validate a ticker symbol; raise ``ValueError`` if invalid."""
    ticker = raw.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"Invalid ticker symbol: {raw!r}")
    return ticker


def escape_markdown(text: str | None) -> str:
    """Escape markdown control characters so untrusted text renders literally."""
    return _MD_SPECIAL.sub(r"\\\1", str(text or ""))


def safe_url(url: str | None) -> str | None:
    """
    Return ``url`` only if it is a plain http(s) link safe to drop into a
    markdown target, else ``None``. Rejects ``javascript:``/``data:`` schemes
    and anything containing characters that could break out of the link.
    """
    if not url:
        return None
    candidate = str(url).strip()
    if not candidate.lower().startswith(("http://", "https://")):
        return None
    if any(ch in candidate for ch in _URL_FORBIDDEN):
        return None
    return candidate
