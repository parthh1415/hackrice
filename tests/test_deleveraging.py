"""Forced selling, against the cascade that actually ships.

These used to drive `Book.deleverage()`, which settled at book prices and was
therefore equity-neutral at any impact — the precise bug the VWAP change was
made to kill. `run_cascade` has never called that method. So the suite was
asserting, unconditionally, the one property the engine deliberately gave up.

Equity-neutral selling is the limit case, not the rule: it holds at gamma=0,
where the round VWAP and the book price are the same number. That is also
where the sale size is derived, so it is worth pinning — next to the test that
says what happens once impact is switched on.
"""

import numpy as np

from minima.engine import run_cascade

# one fund, so nothing that happens to it can be blamed on anybody else
LEVERED = np.array([[60.0, 30.0, 10.0]])
DEEP = np.array([1e9, 1e9, 1e9])      # so much volume that selling moves nothing
THIN = np.array([200.0, 200.0, 200.0])

# A=100, D=75, E=25 at 4x. after a 10% hit on asset 0: A=94, E=19, L=4.95,
# which is over the 4.2 ceiling.
BREAKING_SHOCK = np.array([-0.10, 0.0, 0.0])


def cascade(gamma, adv=DEEP, leverage=4.0, shock=BREAKING_SHOCK):
    return run_cascade(
        holdings=LEVERED,
        leverage=np.array([leverage]),
        max_leverage=np.array([leverage * 1.05]),
        target_leverage=np.array([leverage]),
        gamma=gamma,
        adv=adv,
        shock=shock,
    )


def test_the_sale_is_equity_neutral_only_when_impact_is_off():
    # assets and debt fall by the same amount, so equity cannot move — but
    # that is only true while the proceeds come in at book price.
    frames = cascade(gamma=0.0).trajectory

    np.testing.assert_allclose(frames[0]["equity"][0], 19.0)
    np.testing.assert_allclose(frames[-1]["equity"][0], 19.0)


def test_a_fire_seller_eats_its_own_price_impact():
    # the same fund, the same sale, into a market thin enough to move. there
    # is nobody else in this book, so every dollar lost here is its own doing.
    frames = cascade(gamma=0.5, adv=THIN).trajectory

    assert frames[-1]["equity"][0] < frames[0]["equity"][0]


def test_deleveraging_lands_on_the_target():
    result = cascade(gamma=0.0)
    frames = result.trajectory

    assert result.rounds == 1
    np.testing.assert_allclose(frames[-1]["leverage"][0], 4.0)


def test_a_fund_inside_its_limit_sells_nothing():
    # same shock, but at 1.5x it lands at L=1.55 against a 1.575 ceiling
    result = cascade(gamma=0.0, leverage=1.5)

    assert result.rounds == 0
    assert result.breached == []


def test_liquidation_is_spread_pro_rata_across_the_book():
    sold = cascade(gamma=0.0).trajectory[1]["sold"][0]

    # 18 dollars raised, book is 54/30/10 by value after the shock
    np.testing.assert_allclose(sum(sold), 18.0)
    np.testing.assert_allclose(sold[0], 18.0 * 54.0 / 94.0)
    np.testing.assert_allclose(sold[1], 18.0 * 30.0 / 94.0)
    np.testing.assert_allclose(sold[2], 18.0 * 10.0 / 94.0)
