"""Reverse stress, asked about one person's portfolio.

The result must actually cross the limit, a hair less must not, and a stricter
limit must never need a bigger shock. Those three are the whole contract; the
rest of this file is about not letting the search claim precision it did not
resolve — the discipline the institutional side already carries and which a
new question does not entitle us to skip.
"""

import json
import pathlib

import numpy as np
import pytest

from minima.engine import run_cascade
from minima.portfolio import (
    cheapest_portfolio_fix, find_portfolio_breakpoint, normalise,
    portfolio_loss, weight_vector,
)
from minima.search import DEFAULT_TOLERANCE

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data" / "cache" / "dataset.json").read_text())
TICKERS = DATA["tickers"]


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


def demo_portfolio():
    """Concentrated enough to break, which is the point of a demo portfolio."""
    return normalise([
        {"symbol": "NVDA", "market_value": 3600.0},
        {"symbol": "MSFT", "market_value": 3150.0},
        {"symbol": "AMZN", "market_value": 2250.0},
        {"symbol": "GOOGL", "market_value": 2250.0},
        {"symbol": "CASH", "market_value": 1050.0},
    ], source="demo")


def loss_at(vector, cash, found, kw):
    result = run_cascade(shock=found.shock, **kw)
    return portfolio_loss(vector, cash, result.prices)


def test_the_shock_it_finds_actually_crosses_the_limit():
    vector, cash = weight_vector(demo_portfolio(), TICKERS)
    kw = scenario()
    found = find_portfolio_breakpoint(vector, cash, 0.10, **kw)

    assert found is not None, "this portfolio is supposed to be breakable"
    assert loss_at(vector, cash, found, kw) >= 0.10


def test_and_a_hair_less_does_not():
    """Minimality, proven rather than asserted — and with slack sized to the
    search's own tolerance rather than to a number that looks small."""
    vector, cash = weight_vector(demo_portfolio(), TICKERS)
    kw = scenario()
    found = find_portfolio_breakpoint(vector, cash, 0.10, **kw)

    weaker = np.array(found.shock, dtype=float)
    weaker[found.asset] *= (1.0 - 4 * DEFAULT_TOLERANCE / abs(found.magnitude))
    result = run_cascade(shock=weaker, **kw)

    assert portfolio_loss(vector, cash, result.prices) < 0.10, (
        "a measurably smaller shock also breaks it, so the reported one is not minimal"
    )


@pytest.mark.parametrize("limits", [(0.05, 0.10), (0.10, 0.15)])
def test_a_stricter_limit_never_needs_a_bigger_shock(limits):
    """Monotonicity. If tightening what you will tolerate made the break point
    move further away, the search would be answering a different question than
    the one on screen."""
    tight, loose = limits
    vector, cash = weight_vector(demo_portfolio(), TICKERS)
    kw = scenario()

    a = find_portfolio_breakpoint(vector, cash, tight, **kw)
    b = find_portfolio_breakpoint(vector, cash, loose, **kw)
    assert a is not None and b is not None
    assert abs(a.magnitude) <= abs(b.magnitude) + DEFAULT_TOLERANCE


def test_the_break_point_is_resolved_finer_than_it_is_printed():
    """Same rule as the institutional hero: two decimals of a percentage is a
    0.01pp grid, so the search has to pin it better than 0.005pp."""
    assert DEFAULT_TOLERANCE * 100.0 <= 0.005


def test_an_all_cash_portfolio_has_no_break_point():
    """No shock in the range breaks it, and the honest answer is "none found",
    not "you are safe"."""
    vector, cash = weight_vector(
        normalise([{"symbol": "CASH", "market_value": 10000.0}]), TICKERS)

    assert find_portfolio_breakpoint(vector, cash, 0.05, **scenario()) is None


def test_the_fix_survives_the_shock_that_broke_it():
    vector, cash = weight_vector(demo_portfolio(), TICKERS)
    kw = scenario()
    found = find_portfolio_breakpoint(vector, cash, 0.10, **kw)
    fix = cheapest_portfolio_fix(vector, cash, 0.10, found.shock, **kw)

    assert fix is not None
    assert loss_at(fix["vector"], fix["cash"], found, kw) < 0.10


def test_the_fix_conserves_the_portfolio_s_value():
    """Cut to cash, not cut into thin air. §18: do not quietly change value."""
    vector, cash = weight_vector(demo_portfolio(), TICKERS)
    kw = scenario()
    found = find_portfolio_breakpoint(vector, cash, 0.10, **kw)
    fix = cheapest_portfolio_fix(vector, cash, 0.10, found.shock, **kw)

    assert fix["vector"].sum() + fix["cash"] == pytest.approx(1.0, abs=1e-12)
    assert fix["cash"] > cash, "the cut has to land somewhere and cash is where"


def test_a_smaller_cut_than_the_one_reported_misses_the_target():
    """Minimal with respect to the TARGET it was solving for, not the limit.

    This first asserted against the limit and failed, correctly: the fix aims
    at limit x (1 - margin), so a shallower cut can still clear the limit while
    missing what it was asked to hit. The margin exists because without it the
    answer is literally zero dollars — the break point is where the loss lands
    exactly on the limit, so an infinitesimal cut already survives it.
    """
    vector, cash = weight_vector(demo_portfolio(), TICKERS)
    kw = scenario()
    found = find_portfolio_breakpoint(vector, cash, 0.10, **kw)
    fix = cheapest_portfolio_fix(vector, cash, 0.10, found.shock, **kw)

    from minima.portfolio import cut_to_cash
    smaller, smaller_cash = cut_to_cash(
        vector, cash, fix["asset"], fix["fraction_of_position"] * 0.9)

    assert loss_at(smaller, smaller_cash, found, kw) > fix["target_loss"], (
        "a 10% shallower cut also reaches the target, so the reported cut is "
        "not the smallest one that does"
    )
    assert fix["loss_after"] <= fix["target_loss"] + 1e-9
    assert fix["target_loss"] < fix["limit"], "the fix must buy real headroom"
