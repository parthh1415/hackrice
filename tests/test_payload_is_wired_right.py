"""The forty lines that glue the tested modules to the response.

`validate.py` and `portfolio.py` are thoroughly unit-tested. `_portfolio_full`
— which calls them and assembles what the screen reads — was not, and an audit
that mutated the call sites rather than the functions found eleven of fifteen
corruptions leaving the suite green. Four of those put a wrong number on screen:

  - `synthetic_stress(after, before, …)`, arguments swapped, so the evidence
    page reports the fix made the book WORSE in all 400 scenarios: worst of 400
    reads 10.73% -> 11.94% and survival 99% -> 98%.
  - `prices` published as the post-shock prices instead of the post-cascade
    ones, so the attribution table's contagion column reads 0.000% for every
    name, under a headline still saying amplification 1.38x.
  - `limit=limit * 2` in the synthetic call, so survival reads 100% / 100% —
    the strongest claim the product can make.
  - a narrowed `shock_range`, so "worst of 400" understates by 6.6x while
    `shock_range_pct` faithfully reports the narrower range nobody reads.

Every one of those is a well-tested function called slightly wrong. The unit
tests cannot see it and neither could anything else, because nothing asserted
the relationship between what went in and what came out.

So this file tests the PAYLOAD: the thing the frontend actually parses.
"""

import numpy as np
import pytest

from minima import api


@pytest.fixture(scope="module")
def full():
    return api.handle("/api/portfolio/full?limit=0.10", {})


def test_there_is_a_result_to_check(full):
    """Guard the guard: a refusal would make everything below vacuous."""
    assert full["found"] is True and full.get("fix"), full.get("reason")


def test_the_defended_book_is_the_one_reported_as_defended(full):
    """Swap the two portfolios and every number below inverts.

    The suite stayed green through exactly that swap. The sign IS the claim
    here — the page's entire job is saying the fix helped — so it is asserted
    on every measure the page prints, not just the headline.
    """
    syn = full["validation"]["synthetic"]
    before, after = syn["before"], syn["after"]

    assert after["worst_loss"] < before["worst_loss"], (
        f"the defended book's worst case is {after['worst_loss']:.4f} against "
        f"the current book's {before['worst_loss']:.4f} — the arguments are "
        "the wrong way round"
    )
    assert after["survival"] >= before["survival"]
    assert after["median_loss"] <= before["median_loss"]
    assert after["p95_loss"] <= before["p95_loss"]

    shock = full["validation"]["identical_shock"]
    assert shock["after_loss"] < shock["before_loss"]
    assert shock["before_breaks"] is True and shock["after_breaks"] is False

    moved = full["validation"]["new_breaking_point"]
    if moved.get("after_pct") is not None:
        assert moved["after_pct"] > moved["before_pct"]
        assert moved["moved_pp"] > 0


def test_survival_is_scored_against_the_limit_that_was_asked_for(full):
    """`limit * 2` in the synthetic call reads as 100% / 100% survival.

    Recomputed here from the losses the same call returned, so a limit applied
    inside the function that is not the one on screen cannot hide.
    """
    limit = full["params"]["limit"]
    syn = full["validation"]["synthetic"]

    assert syn["limit"] == pytest.approx(limit), (
        f"the scenarios were scored against {syn['limit']} while the page says "
        f"{limit}"
    )
    # a book whose 95th percentile already clears the limit cannot be at 100%
    # survival unless the limit it was scored against was loosened
    for side in ("before", "after"):
        s = syn[side]
        if s["worst_loss"] > limit:
            assert s["survival"] < 1.0, (
                f"{side}: worst case {s['worst_loss']:.4f} is past a {limit} "
                f"limit, yet survival is {s['survival']}"
            )


def test_the_reported_shock_range_is_the_one_the_scenarios_were_drawn_from(full):
    """Narrow the range and "worst of 400" falls 6.6x while the label follows.

    The label being right is what makes this invisible: `shock_range_pct` says
    1–5% quite honestly, next to a worst case computed over 1–5% and a headline
    that means nothing without it. Re-running at the reported range has to
    reproduce the reported number.
    """
    from minima import validate as V
    from minima.portfolio import (Holding, Portfolio, cheapest_portfolio_fix,
                                     weight_vector)

    syn = full["validation"]["synthetic"]
    lo, hi = [x / 100.0 for x in syn["shock_range_pct"]]
    assert (lo, hi) == pytest.approx((0.01, 0.30)), (
        f"the scenarios were drawn from {lo}–{hi}, which is not this build's range"
    )

    # Re-run at the range the payload REPORTS. If the call used a different one
    # the numbers will not reproduce — which is the whole point, because the
    # label follows the call and stays honest while the figure beside it moves.
    data = api.load_dataset()
    book = Portfolio(holdings=[Holding(symbol=h["symbol"], market_value=h["market_value"])
                               for h in full["portfolio"]["holdings"]])
    vector, cash = weight_vector(book, data["tickers"])
    limit = full["params"]["limit"]
    m = len(data["funds"])
    scenario = dict(
        holdings=np.array(data["holdings"], dtype=float),
        leverage=np.full(m, full["params"]["leverage"]),
        max_leverage=np.full(m, full["params"]["leverage"] * full["params"]["band"]),
        target_leverage=np.full(m, full["params"]["leverage"] * 0.95),
        gamma=full["params"]["gamma"],
        adv=np.array(data["adv"], dtype=float),
    )
    fix = cheapest_portfolio_fix(vector, cash, limit,
                                 np.array(full["magnitude"] * np.eye(len(vector))[full["asset_index"]]),
                                 **scenario)
    again = V.synthetic_stress({"vector": vector, "cash": cash},
                               {"vector": fix["vector"], "cash": fix["cash"]},
                               n=syn["scenarios"], seed=syn["seed"],
                               limit=limit, shock_range=(lo, hi), **scenario)

    assert again["before"]["worst_loss"] == pytest.approx(syn["before"]["worst_loss"], rel=1e-9), (
        f"re-running at the reported range {lo}–{hi} gives a worst case of "
        f"{again['before']['worst_loss']:.6f}, not the {syn['before']['worst_loss']:.6f} "
        "the payload publishes. The label and the draws disagree"
    )
    assert again["after"]["worst_loss"] == pytest.approx(syn["after"]["worst_loss"], rel=1e-9)
    assert again["before"]["survival"] == pytest.approx(syn["before"]["survival"])


def test_the_published_prices_are_the_end_of_the_cascade(full):
    """`prices` as the post-SHOCK vector zeroes the contagion column.

    Every name the user holds but nobody shocked then reads 0.000% under
    "from contagion", on the same screen whose headline says amplification
    1.38x. The table and the number above it would contradict each other, and
    the table is the more believable of the two.
    """
    from minima.portfolio import Holding, Portfolio, portfolio_loss, weight_vector

    data = api.load_dataset()
    book = Portfolio(holdings=[Holding(symbol=h["symbol"], market_value=h["market_value"])
                               for h in full["portfolio"]["holdings"]])
    vector, cash = weight_vector(book, data["tickers"])

    prices = np.array(full["prices"], dtype=float)
    direct = np.array(full["direct_prices"], dtype=float)

    # the two vectors are not the same thing, and the page subtracts them
    assert not np.allclose(prices, direct), (
        "the post-cascade prices equal the post-shock prices, so every "
        "contagion figure on the analysis page is zero"
    )
    # only the shocked name moves under the shock alone
    moved = np.flatnonzero(direct < 1.0 - 1e-9)
    assert moved.tolist() == [full["asset_index"]], (
        f"the shock alone moved {moved.tolist()}, not just {full['asset_index']}"
    )
    # the cascade moves more names than the shock did
    assert np.count_nonzero(prices < 1.0 - 1e-9) > len(moved)

    # and each published vector reproduces the loss published beside it
    assert portfolio_loss(vector, cash, prices) == pytest.approx(full["cascade_loss"], rel=1e-9)
    assert portfolio_loss(vector, cash, direct) == pytest.approx(full["direct_loss"], rel=1e-9)


def test_the_attribution_the_page_draws_sums_to_the_loss_it_prints(full):
    """The analysis table's arithmetic, done here rather than in the browser.

    The page computes weight x fall per name and prints a total. If the two
    price vectors are wired wrongly the columns still add up to something —
    just not to the loss in the headline.
    """
    weights = {h["symbol"]: h["weight"] for h in full["portfolio"]["holdings"]}
    contributions = 0.0
    for i, ticker in enumerate(full["tickers"]):
        w = weights.get(ticker)
        if not w:
            continue
        contributions += w * (1.0 - full["prices"][i])

    assert contributions == pytest.approx(full["cascade_loss"], abs=5e-5), (
        f"the per-name contributions sum to {contributions:.6f} where the page "
        f"headlines {full['cascade_loss']:.6f}"
    )
