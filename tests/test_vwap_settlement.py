"""Sellers settle at round VWAP, not at the price they opened the round with.

`test_deleveraging.py` says in its own docstring that book-price settlement is
"the precise bug the VWAP change was made to kill", and then does not detect
it: set `execution = before` in engine.py and all five of its tests still
pass. Its strongest assertion is `equity[-1] < equity[0]`, which holds under
book settlement too — a fire-seller's equity falls either way, because the
mark-to-market loss on the book it KEEPS already does that. What book
settlement hides is the slippage on what it SELLS.

A mutation sweep found this, and my first attempt to close it failed the same
way: three freshly written tests that passed under both rules. Asserting that
a seller loses equity, or that prices fall, does not separate them — both are
true either way.

What separates them is how far a forced sale falls short of its own target.
A fund selling to reach target leverage raises less than it marked, so it
lands above target. Book settlement narrows that shortfall but does not
remove it, because impact moves the mark as well. So the test pins the
measured number, with the book-settlement number written down beside it:

    post-sale leverage, target 4.75
      VWAP  5.057081     <- what this engine does
      book  5.025014     <- what `execution = before` does

Both values were measured by running the engine each way. The assertion is
tight enough that the two cannot be confused.
"""

import numpy as np

from minima.engine import run_cascade

# One fund, deep ADV, a shock just past its breach ceiling — so it sells once,
# survives, and its post-sale leverage is readable. Deliberately not the demo
# path: there the two rules give 1.8710 against 1.8551 amplification, which
# rounds to 1.87 and 1.86 on screen and hides inside any loose tolerance.
BOOK = dict(
    holdings=np.array([[100.0, 100.0]]),
    leverage=np.array([5.0]),
    max_leverage=np.array([5.25]),
    target_leverage=np.array([4.75]),
    gamma=1.0,
    adv=np.array([1000.0, 1000.0]),
)
SHOCK = np.array([-0.05, 0.0])

VWAP_LEVERAGE = 5.057081        # this engine
BOOK_LEVERAGE = 5.025014        # `execution = before`


def test_a_forced_sale_falls_short_of_target_by_the_slippage_it_paid():
    result = run_cascade(shock=SHOCK, **BOOK)
    landed = result.trajectory[-1]["leverage"][0]

    assert abs(landed - VWAP_LEVERAGE) < 5e-6, (
        f"post-sale leverage {landed:.6f}; VWAP settlement gives {VWAP_LEVERAGE}, "
        f"book-price settlement gives {BOOK_LEVERAGE}. If this reads like the "
        "latter, sellers have stopped paying for their own impact."
    )
    assert landed > BOOK_LEVERAGE + 0.02, (
        f"post-sale leverage {landed:.6f} is at or below what book-price "
        f"settlement would give ({BOOK_LEVERAGE}) — the seller is realising "
        "the pre-trade mark on what it sold"
    )
    assert landed > BOOK["target_leverage"][0], (
        "a fund that sold into its own impact cannot have reached its target"
    )


def test_the_gap_widens_with_impact_because_slippage_is_what_makes_it():
    """gamma is the only thing that puts a wedge between execution and mark.

    Turn it up and the shortfall must grow. If it does not, the execution
    price is not participating in the answer.
    """
    shortfalls = []
    for gamma in (0.25, 0.5, 1.0, 2.0):
        result = run_cascade(shock=SHOCK, **dict(BOOK, gamma=gamma))
        shortfalls.append(result.trajectory[-1]["leverage"][0] - BOOK["target_leverage"][0])

    assert all(b > a for a, b in zip(shortfalls, shortfalls[1:])), (
        f"shortfall against target did not grow with impact: {shortfalls}"
    )


def test_zero_impact_leaves_nothing_for_the_execution_price_to_change():
    """The control, and the boundary the VWAP rule must not cross.

    At gamma=0 there is no price move within the round, so `before` and
    `after` are the same number and the two settlement rules are identical.
    Forced selling is exactly equity-neutral here — and that is the one case
    where it should be.
    """
    # This ran at shock=[0, 0], which is a control with nothing in it: nobody
    # breaches, so no forced selling happens, the trajectory is one frame, and
    # `start` is read from that same frame — abs(start - start) < 1e-9. The
    # price assertion was inert for the same reason. Both survived a mutation
    # that paid sellers NOTHING for what they sold.
    #
    # The file's own SHOCK does breach, so at gamma=0 there is a real sale to
    # be equity-neutral about.
    result = run_cascade(shock=SHOCK, **dict(BOOK, gamma=0.0))

    assert result.rounds >= 1, "no forced selling happened, so nothing was tested"
    sold = sum(sum(row) for f in result.trajectory for row in f["sold"])
    assert sold > 0, "nobody sold anything, so nothing was tested"

    for frame in result.trajectory:
        # gamma=0: the shock moves prices once and the selling moves them not
        # at all, so every frame carries the post-shock prices unchanged.
        assert all(abs(p - q) < 1e-12 for p, q in
                   zip(frame["prices"], result.trajectory[0]["prices"])), frame["prices"]
    start = result.trajectory[0]["equity"][0]
    assert all(abs(f["equity"][0] - start) < 1e-9 for f in result.trajectory), (
        "with no price impact, forced selling must be equity-neutral"
    )
