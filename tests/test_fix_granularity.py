"""The fix has to answer "how much", not just "which position".

`_STEPS = 20` gave 5% granularity, and every single golden recording came
back with `reduction: 0.050` — the floor — at every band and every leverage.
The search was optimising which position to cut and never how deep, so
"Millennium cuts GOOGL by 5%" actually meant "by at most 5%, we didn't look
closer".

That is the same fake-precision failure the shock search was tightened to
5e-5 to avoid, left standing in the beat the product is named after. MATLAB's
patternsearch explores reduction continuously, so the two engines were
solving different problems and the badge said which ran, not that.
"""

import json
import pathlib

import numpy as np
import pytest

from minima import api
from minima.engine import run_cascade
from minima.search import at_least_n_breaches
from minima.stabilise import Fix, find_cheapest_fix

REAL = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache" / "dataset.json"


def scenario(leverage=5.0, gamma=0.2, band=1.05):
    data = json.loads(REAL.read_text())
    m = len(data["funds"])
    return data, dict(
        holdings=np.array(data["holdings"]),
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * band),
        target_leverage=np.full(m, min(max(1.0, leverage * 0.95), leverage * band)),
        gamma=gamma,
        adv=np.array(data["adv"]),
    )


def test_the_reduction_is_not_pinned_to_the_grid_floor():
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})

    assert result["found"]
    reduction = result["fix"]["reduction"]
    assert reduction not in (0.05, 0.10, 0.15, 0.20), (
        f"reduction {reduction} is exactly a 5% grid point — the search is "
        "still only choosing a position, not a depth"
    )


def true_minimum_at(condition, kw, shock, fund, asset):
    """Bisect the same position to far past display precision."""
    holdings = kw["holdings"]
    other = {k: v for k, v in kw.items() if k != "holdings"}

    def still_fails(r):
        patched = Fix(fund, asset, r, 0.0).apply(holdings)
        return condition(run_cascade(holdings=patched, shock=shock, **other))

    lo, hi = 0.0, 1.0
    if still_fails(hi):
        return None  # selling the whole position doesn't save it
    for _ in range(45):
        mid = (lo + hi) / 2.0
        if still_fails(mid):
            lo = mid
        else:
            hi = mid
    return hi


def test_the_reported_cut_is_close_to_the_true_minimum():
    """The previous version of this test clamped to zero and proved nothing.

    It took `slack = 0.004` absolute and checked `fix.reduction - 2 * slack`.
    Once the bisection landed the answer at 0.0015625 that expression went
    negative, `max(0.0, ...)` turned it into a zero-reduction run, and the
    assertion became "the system we have not fixed yet still fails" — true by
    construction, for any code, forever. It stayed green exactly as long as it
    was meaningless.

    What it should have caught: `_DEPTH_TOLERANCE` was absolute at 0.002 while
    the answer had shrunk to 0.0007, so the bisection halted holding a bracket
    wider than the number it was about to report, and printed the top of it.
    Measured 0.15625% against a true minimum of 0.07252% — 2.15x too much, on
    the single number this product exists to produce.
    """
    _, kw = scenario()
    condition = at_least_n_breaches(3)
    from minima.search import find_weakest_shock

    found = find_weakest_shock(condition=condition, **kw)
    fix = find_cheapest_fix(condition=condition, shock=found.shock, **kw)
    assert fix is not None

    truth = true_minimum_at(condition, kw, found.shock, fix.fund, fix.asset)
    assert truth is not None
    assert fix.reduction >= truth, (
        f"reported {fix.reduction:.6f} is BELOW the true minimum {truth:.6f} — "
        "it does not actually clear the condition"
    )
    assert fix.reduction <= truth * 1.05, (
        f"reported cut {fix.reduction:.6f} against a true minimum of {truth:.6f} "
        f"({fix.reduction / truth:.2f}x too large). The search resolved the "
        "position but not the depth."
    )


def test_the_cost_is_priced_from_the_cut_it_reports():
    """cost and reduction have to describe the same trade.

    An earlier revision passed 0.0 as the cost while bisecting and rebuilt the
    Fix afterwards; if those two ever drift, the UI quotes a price for a cut
    nobody made.
    """
    data, kw = scenario()
    condition = at_least_n_breaches(3)
    from minima.search import find_weakest_shock

    found = find_weakest_shock(condition=condition, **kw)
    fix = find_cheapest_fix(condition=condition, shock=found.shock, **kw)
    assert fix is not None

    holdings = kw["holdings"]
    expected = holdings[fix.fund, fix.asset] * fix.reduction / holdings.sum()
    assert fix.cost == pytest.approx(expected, rel=1e-12), (
        f"cost {fix.cost} prices a reduction of "
        f"{fix.cost * holdings.sum() / holdings[fix.fund, fix.asset]:.6f}, "
        f"but the reported reduction is {fix.reduction:.6f}"
    )


def test_the_fix_still_actually_works():
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})

    assert len(result["after"]["breached"]) < result["params"]["breaches"]


def test_the_two_per_cent_guarantee_holds_where_the_floor_can_take_over():
    """The depth floor is in DOLLARS, and the comment on it says why: stated as
    a fraction of a position it is an absolute tolerance wearing a different
    hat, and it silently takes over from the 2% relative bound as soon as the
    answer gets small.

    Nothing tested that. `depth_floor_is_a_fraction_again` — the mutation that
    puts the fraction back — survived a full sweep, because every setting the
    suite exercises returns a cut far above where the floor binds. It is not an
    inert mutation: a scan of the knobs finds four reachable settings whose
    answer is under 5e-6, and this is the deepest of them.

    The guarantee is checked on its own terms rather than against a recorded
    number: if the reported cut is within 2% of the smallest one that works,
    then a cut 2% smaller must NOT work.
    """
    import numpy as np

    from minima import api
    from minima.engine import run_cascade
    from minima.matlab_bridge import _python_fallback
    from minima.search import at_least_n_breaches
    from minima.stabilise import Fix

    # the spec is written to disk by the route, so ask for the scenario first
    api.handle("/api/stabilise?leverage=3.0&gamma=0.1&band=1.1&breaches=2", {})
    root = pathlib.Path(__file__).resolve().parents[1]
    spec = json.loads((root / "data" / "cache" / "solve_spec.json").read_text())

    solved = _python_fallback(spec)
    assert solved is not None, "this setting has to have a fix for the test to mean anything"
    assert solved["reduction"] < 5e-6, (
        f"reduction {solved['reduction']:.3e} is above where the floor can bind — "
        "pick another setting or this tests nothing"
    )

    holdings = np.array(spec["holdings"], dtype=float)
    kwargs = dict(
        leverage=np.array(spec["leverage"], dtype=float),
        max_leverage=np.array(spec["max_leverage"], dtype=float),
        target_leverage=np.array(spec["target_leverage"], dtype=float),
        gamma=float(spec["gamma"]),
        adv=np.array(spec["adv"], dtype=float),
    )
    shock = np.array(spec["shock"], dtype=float)
    fails = at_least_n_breaches(int(spec["breaches"]))

    def clears(reduction):
        fix = Fix(int(solved["fund_index"]), int(solved["asset_index"]), reduction, 0.0)
        return not fails(run_cascade(holdings=fix.apply(holdings), shock=shock, **kwargs))

    assert clears(solved["reduction"]), "the reported cut does not even work"
    smaller = solved["reduction"] * 0.97      # 3% under, against a 2% guarantee
    assert not clears(smaller), (
        f"a cut 3% smaller ({smaller:.6e}) also clears the condition, so the "
        f"reported {solved['reduction']:.6e} is more than 2% above the minimum — "
        "the depth floor has taken over from the relative bound"
    )
