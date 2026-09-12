"""The two properties the engine's credibility rests on, stated as identities.

Both came out of an audit that found the mathematics sound. A clean bill of
health is worth nothing a week later unless the thing that was checked is
pinned, so these are the checks written down: not "the numbers look right" but
"the code computes this closed form and no other".

Each asserts against a formula derived independently of the implementation, and
each has a rival formula asserted to be WRONG — because an identity only one
expression satisfies is evidence, and one that several satisfy is decoration.
"""

import json
import pathlib

import numpy as np
import pytest

from firebreak.engine import Book, run_cascade

DATA = json.loads((pathlib.Path(__file__).resolve().parents[1]
                   / "data" / "cache" / "dataset.json").read_text())
HOLDINGS = np.array(DATA["holdings"], dtype=float)
ADV = np.array(DATA["adv"], dtype=float)
N_FUNDS = len(DATA["funds"])


@pytest.mark.parametrize("leverage", [2.0, 5.0, 7.5])
def test_round_one_sales_are_the_greenwood_landier_thesmar_rule(leverage):
    """A fund run at its target sells (lambda - 1) x its loss.

    This is the deleveraging rule the whole model is an application of, and it
    is the line a finance reader will check first. Solving (A - q)/E = target
    for q with E = A/L gives q = A(L - target)/L; at target == L == the fund's
    own leverage that collapses to (L - 1) x loss, which is derived here from
    equity alone and never touches the code's arithmetic.
    """
    book = Book(HOLDINGS, np.full(N_FUNDS, leverage))
    equity_before = book.equity().copy()

    shock = np.zeros(HOLDINGS.shape[1])
    shock[0] = -0.20
    book.shock(shock)
    loss = equity_before - book.equity()

    # target == max means every fund is over and every fund deleverages
    hit = book.over_limit(np.full(N_FUNDS, leverage))
    units_sold, _ = book.plan_sales(hit, np.full(N_FUNDS, leverage))
    sold_dollars = (units_sold * book.prices).sum(axis=1)

    expected = (leverage - 1.0) * loss
    assert sold_dollars == pytest.approx(expected, rel=1e-12), (
        "round-one forced sales are not (leverage - 1) x loss. Either the "
        "deleveraging rule changed or the balance sheet did"
    )

    # the rival: selling the loss itself, with no leverage multiplier. That is
    # the shape of the bug where a fund deleverages as if it were unlevered,
    # and it produces a cascade an order of magnitude too mild.
    if leverage != 2.0:
        assert not np.allclose(sold_dollars, loss), (
            "sales equal the loss with no leverage multiplier; the cascade is "
            "being driven by the wrong rule"
        )


def _reference_cascade(leverage, gamma, drop, execution_rule):
    """The documented round, written out from the spec rather than the code.

    One round: whoever is over their limit plans sales, those sales move prices
    linearly in participation, the sales settle at `execution_rule(before,
    after)`, and whatever is still held is marked at the closing price. Returns
    the final prices so it can be compared against run_cascade's.
    """
    book = Book(HOLDINGS, np.full(N_FUNDS, leverage))
    max_leverage = np.full(N_FUNDS, leverage * 1.05)
    target = np.full(N_FUNDS, leverage * 0.95)
    shock = np.zeros(HOLDINGS.shape[1])
    shock[0] = drop
    book.shock(shock)

    rounds = 0
    for _ in range(24):
        hit = book.over_limit(max_leverage)
        if not hit:
            break
        units_sold, _ = book.plan_sales(hit, target)
        volume = (units_sold * book.prices).sum(axis=0)
        before = book.prices.copy()
        after = before * np.maximum(1.0 - gamma * volume / ADV, 1e-6)
        book.settle(units_sold, execution_rule(before, after))
        book.prices = after
        rounds += 1
    return book.prices, book.equity(), rounds


@pytest.mark.parametrize("leverage,gamma", [(5.0, 0.5), (7.5, 0.2), (3.0, 1.0)])
def test_a_round_settles_at_the_midpoint_and_not_at_the_close(leverage, gamma):
    """Where in the round a fund's sales are priced, pinned to a rule.

    Sales execute at the round VWAP — the midpoint of the price before and
    after the impact they cause — while whatever the fund still holds is marked
    at the closing price. A fund that sold at the close instead would book the
    full benefit of its own price impact, and one that marked its residual at
    the midpoint would book part of it as a gain; both flatter every number
    downstream.

    The first version of this test asserted a closed form for equity while
    reimplementing the loop itself, so it never touched run_cascade and stayed
    green when `execution` was changed to `after` inside it. It compares
    run_cascade's OWN trajectory against a reference now, and requires the
    rival rule to disagree — an identity several implementations satisfy is
    decoration, not evidence.
    """
    drop = -0.25
    shock = np.zeros(HOLDINGS.shape[1])
    shock[0] = drop
    live = run_cascade(
        holdings=HOLDINGS, leverage=np.full(N_FUNDS, leverage),
        max_leverage=np.full(N_FUNDS, leverage * 1.05),
        target_leverage=np.full(N_FUNDS, leverage * 0.95),
        gamma=gamma, adv=ADV, shock=shock,
    )

    midpoint, mid_equity, rounds = _reference_cascade(
        leverage, gamma, drop, lambda b, a: (b + a) / 2.0)
    assert rounds > 0, "the shock caused no deleveraging; nothing was tested"
    assert live.prices == pytest.approx(midpoint, rel=1e-12), (
        "run_cascade no longer settles its sales at the round VWAP"
    )

    at_close, _, _ = _reference_cascade(leverage, gamma, drop, lambda b, a: a)
    assert not np.allclose(live.prices, at_close, rtol=1e-9), (
        "settling at the close produces the same prices as settling at the "
        "midpoint, so this test cannot tell them apart and is not evidence"
    )

    at_open, _, _ = _reference_cascade(leverage, gamma, drop, lambda b, a: b)
    assert not np.allclose(live.prices, at_open, rtol=1e-9), (
        "settling at the opening price is indistinguishable here too"
    )


def test_damage_from_a_zero_shock_is_not_reported_as_no_amplification():
    """A ratio with a zero denominator is undefined, not one.

    Books already over their limit before anything happens deleverage on their
    own: a zero shock here destroys 14.2% of system equity across five funds
    and two rounds. `amplification` fell back to 1.0, which is not a neutral
    placeholder — it is the specific claim that forced selling added nothing to
    the initial damage, and it is exactly false. The same books at a shock of
    -1e-6 report 128,255.

    Unreachable through the institutional API, which clamps the band to >= 1.0
    so max_leverage can never start below leverage. Live for any other caller,
    and this is the one case where the number is not merely imprecise but
    inverted.
    """
    from firebreak.engine import run_cascade

    over_from_the_start = run_cascade(
        holdings=HOLDINGS, leverage=np.full(N_FUNDS, 6.0),
        max_leverage=np.full(N_FUNDS, 5.0), target_leverage=np.full(N_FUNDS, 4.75),
        gamma=0.2, adv=ADV, shock=np.zeros(HOLDINGS.shape[1]),
    )
    assert over_from_the_start.shock_loss == pytest.approx(0.0)
    assert over_from_the_start.final_loss > 0.1, "this setup is meant to do damage"
    assert over_from_the_start.amplification is None, (
        "damage divided by no damage is undefined. Reporting 1.0 says the "
        "cascade added nothing, next to a final_loss saying it destroyed "
        f"{over_from_the_start.final_loss:.1%} of system equity"
    )
    assert over_from_the_start.as_dict()["metrics"]["amplification"] is None

    # a genuinely quiet run — nothing happened — may still say 1.0
    quiet = run_cascade(
        holdings=HOLDINGS, leverage=np.full(N_FUNDS, 5.0),
        max_leverage=np.full(N_FUNDS, 5.25), target_leverage=np.full(N_FUNDS, 4.75),
        gamma=0.2, adv=ADV, shock=np.zeros(HOLDINGS.shape[1]),
    )
    assert quiet.final_loss == pytest.approx(0.0)
    assert quiet.amplification == pytest.approx(1.0)
