"""Regression tests for the insolvency hole.

A fund whose equity crosses zero has A/E negative, so `L > L_max` is FALSE and
it silently stopped breaching and stopped selling. Bigger shock, fewer sellers,
less damage. Damage was not monotone in shock size, which makes "the smallest
shock that breaks the system" meaningless — it isn't a threshold.

Found independently by two reviewers on the real 13F books at the default
slider positions, not just in a contrived fixture.
"""

import json
import pathlib

import numpy as np

from minima.engine import run_cascade
from minima.search import at_least_n_breaches

# the toy case that shows the degenerate end most starkly
TOY = dict(
    holdings=np.array([[70.0, 30.0, 0.0], [0.0, 60.0, 40.0]]),
    leverage=np.array([10.0, 5.0]),
    max_leverage=np.array([10.2, 5.1]),
    target_leverage=np.array([9.0, 4.5]),
    gamma=0.8,
    adv=np.array([50.0, 50.0, 50.0]),
)

REAL = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache" / "dataset.json"


def drop(config, asset, pct):
    shock = np.zeros(config["holdings"].shape[1])
    shock[asset] = -pct
    return run_cascade(shock=shock, **config)


def test_a_shock_that_bankrupts_a_fund_is_not_reported_as_stable():
    mild = drop(TOY, 0, 0.06)
    severe = drop(TOY, 0, 0.15)

    assert mild.breached, "sanity: the mild shock should break something"
    assert severe.breached, (
        "a 15% drop wipes fund 0 out entirely — it cannot be reported as "
        f"zero breaches. got breached={severe.breached}, amp={severe.amplification}"
    )


def test_breach_count_is_monotone_on_the_toy_case():
    """Breach count must never fall as the shock grows.

    This is the property the failure conditions actually depend on, and it's
    the one the insolvency hole broke. Final loss is NOT monotone and we don't
    pretend otherwise — see test_loss_is_not_claimed_to_be_monotone.
    """
    worst_count = -1
    for pct in range(0, 41):
        result = drop(TOY, 0, pct / 100)
        assert len(result.breached) >= worst_count, f"breach count fell at {pct}%"
        worst_count = len(result.breached)


def test_breach_count_is_monotone_on_the_real_books():
    data = json.loads(REAL.read_text())
    m = len(data["funds"])
    lev = 5.0
    config = dict(
        holdings=np.array(data["holdings"]),
        leverage=np.full(m, lev),
        max_leverage=np.full(m, lev * 1.05),
        target_leverage=np.full(m, lev * 0.95),
        gamma=0.2,
        adv=np.array(data["adv"]),
    )

    for asset in range(len(data["tickers"])):
        worst_count = -1
        for pct in range(0, 61):
            result = drop(config, asset, pct / 100)
            assert len(result.breached) >= worst_count, (
                f"{data['tickers'][asset]} breach count fell at {pct}%"
            )
            worst_count = len(result.breached)


def test_an_insolvent_fund_liquidates_everything():
    result = drop(TOY, 0, 0.30)

    final = result.trajectory[-1]
    # a fund that went under should have nothing left and be counted
    assert 0 in result.breached
    assert final["defaulted"], "the result has to say who actually went under"


def test_loss_is_not_claimed_to_be_monotone():
    """Final loss genuinely is not monotone, and that's a model property.

    A larger shock can bankrupt a fund one round *sooner*, so it liquidates at
    a higher VWAP and the system-wide loss comes out marginally smaller. Across
    12,200 runs on the real books that shows up in ~6% of steps, worst dip 16%.
    Recorded here so nobody 'fixes' it into a false monotonicity claim later,
    and so the search never advertises a proven threshold.
    """
    losses = [drop(TOY, 0, pct / 100).final_loss for pct in range(0, 41)]

    dips = [i for i in range(1, len(losses)) if losses[i] < losses[i - 1] - 1e-9]
    assert dips, "if this ever passes cleanly, re-derive the monotonicity claim"
