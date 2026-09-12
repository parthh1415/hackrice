"""The validation layer: does the fix actually help, and can we show it.

The failure mode these guard against is a comparison that flatters itself —
two portfolios scored under different conditions, or an "after" number derived
from the "before" one by arithmetic instead of measured by the same search.
Both would look like evidence and be none.
"""

import json
import pathlib

import numpy as np
import pytest

from firebreak.portfolio import (
    cheapest_portfolio_fix, find_portfolio_firebreak, normalise, weight_vector,
)
from firebreak import validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data" / "cache" / "dataset.json").read_text())
TICKERS = DATA["tickers"]
LIMIT = 0.10


def scenario(leverage=5.0, gamma=0.2, band=1.05):
    m = len(DATA["funds"])
    return dict(
        holdings=np.array(DATA["holdings"]),
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * band),
        target_leverage=np.full(m, min(max(1.0, leverage * 0.95), leverage * band)),
        gamma=gamma,
        adv=np.array(DATA["adv"]),
    )


@pytest.fixture(scope="module")
def solved():
    p = normalise([
        {"symbol": "NVDA", "market_value": 3600.0},
        {"symbol": "MSFT", "market_value": 3150.0},
        {"symbol": "AMZN", "market_value": 2250.0},
        {"symbol": "GOOGL", "market_value": 2250.0},
        {"symbol": "CASH", "market_value": 1050.0},
    ], source="demo")
    vector, cash = weight_vector(p, TICKERS)
    kw = scenario()
    found = find_portfolio_firebreak(vector, cash, LIMIT, **kw)
    fix = cheapest_portfolio_fix(vector, cash, LIMIT, found.shock, **kw)
    return {
        "before": {"vector": vector, "cash": cash},
        "after": {"vector": fix["vector"], "cash": fix["cash"]},
        "found": found, "fix": fix, "kw": kw,
    }


def test_the_replay_breaks_before_and_survives_after(solved):
    out = validate.replay_identical(
        solved["before"], solved["after"], solved["found"].shock, LIMIT, **solved["kw"])

    assert out["before_breaks"] is True
    assert out["after_breaks"] is False
    assert out["after_loss"] < out["before_loss"]


def test_the_replay_uses_one_cascade_for_both_sides(solved):
    """"Only the portfolio changed" is the entire claim of this comparison.

    Scoring each side against its own cascade run would let the two drift under
    some future edit while the caption went on saying they had not.
    """
    out = validate.replay_identical(
        solved["before"], solved["after"], solved["found"].shock, LIMIT, **solved["kw"])

    # identical shock, and an amplification that belongs to the one run
    assert out["shock_pct"] == pytest.approx(solved["found"].pct)
    assert out["amplification"] > 1.0


def test_the_new_break_point_is_recomputed_not_derived(solved):
    """Measured by the same search that found the first one.

    Inferring it from the old break point and the size of the cut would be a
    formula dressed as a measurement.
    """
    out = validate.new_breaking_point(
        solved["before"], solved["after"], LIMIT, **solved["kw"])

    assert out["before_pct"] == pytest.approx(solved["found"].pct)
    if out["after_pct"] is not None:
        assert out["after_pct"] > out["before_pct"], (
            "the fix was chosen to survive this shock, so the next break point "
            "has to sit further out"
        )
        assert out["moved_pp"] == pytest.approx(out["after_pct"] - out["before_pct"])
    else:
        assert out["after_unbreakable"] is True


def test_both_portfolios_are_scored_on_identical_draws(solved):
    """Different weather for the two sides would make any difference meaningless."""
    a = validate.synthetic_stress(solved["before"], solved["after"], n=60, seed=7,
                                  **solved["kw"])
    b = validate.synthetic_stress(solved["before"], solved["after"], n=60, seed=7,
                                  **solved["kw"])
    assert a == b, "the seed does not reproduce"

    c = validate.synthetic_stress(solved["before"], solved["after"], n=60, seed=8,
                                  **solved["kw"])
    assert c["before"] != a["before"], "a different seed produced identical draws"


def test_the_fix_does_not_make_the_portfolio_worse_on_average(solved):
    out = validate.synthetic_stress(solved["before"], solved["after"], n=120, seed=11,
                                    **solved["kw"])

    assert out["after"]["median_loss"] <= out["before"]["median_loss"]
    assert out["after"]["worst_loss"] <= out["before"]["worst_loss"]


def test_no_scenario_produces_a_nan_or_an_infinity(solved):
    out = validate.synthetic_stress(solved["before"], solved["after"], n=120, seed=3,
                                    **solved["kw"])
    for side in ("before", "after"):
        for key, value in out[side].items():
            assert np.isfinite(value), f"{side}.{key} is {value}"


def test_survival_counts_scenarios_under_the_limit():
    assert validate.survival([0.0, 0.05, 0.11, 0.20], 0.10) == pytest.approx(0.5)
    assert validate.survival([0.10, 0.10], 0.10) == pytest.approx(0.0), (
        "a loss exactly at the limit is not survival — the user said they would "
        "not tolerate it"
    )


def test_historical_replay_says_it_is_unavailable_rather_than_inventing_returns():
    """The one test in this file that asserts a feature is ABSENT.

    Shipping it against plausible-looking invented returns would be a confident
    number with nothing underneath it, on the screen that exists to show
    evidence. Missing coverage is stated, not scored as zero risk.
    """
    out = validate.historical_stress()

    assert out["available"] is False
    assert "no price history" in out["reason"].lower()
    assert "loss" not in out, "an unavailable test must not report a number"
