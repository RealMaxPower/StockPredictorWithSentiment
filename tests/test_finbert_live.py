"""
Live FinBERT check: real transformers + torch + the ProsusAI/finbert weights.

Opt-in because the first run downloads ~440 MB. It runs only when
``STOCKPREDICTOR_LIVE_FINBERT=1``, which the dedicated ``finbert`` CI job sets.
With the flag set, a missing extra is a failure rather than a skip, so that job
cannot pass without actually exercising the model.
"""

from __future__ import annotations

import os

import pytest

from stockpredictor import sentiment

pytestmark = pytest.mark.skipif(
    os.getenv("STOCKPREDICTOR_LIVE_FINBERT") != "1",
    reason="live FinBERT check is opt-in (set STOCKPREDICTOR_LIVE_FINBERT=1)",
)


@pytest.fixture(scope="module")
def scorer():
    return sentiment.get_scorer("finbert")


@pytest.mark.parametrize(
    ("text", "low", "high"),
    [
        ("Company beats earnings expectations, shares surge", 0.3, 1.0),
        ("Company files for bankruptcy amid fraud probe", -1.0, -0.3),
        ("The annual shareholder meeting is scheduled for Tuesday", -0.3, 0.3),
    ],
)
def test_finbert_scores_have_the_expected_sign(scorer, text, low, high):
    assert low <= scorer.score(text) <= high
