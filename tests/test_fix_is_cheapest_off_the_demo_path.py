"""The cheapest fix has to be cheapest everywhere, not just on the demo path.

`test_fix_granularity.py` runs entirely at leverage 5.0 / gamma 0.2 /
band 1.05 / >=3 breaching, and at that one point the answer is
Citadel/NVDA — fund 0, asset 0, the very first cell the scan visits. So
`best` is set before a bad pruning rule can discard anything, and the
whole family of pruning bugs is invisible there.

Commit 87c0217 fixed exactly such a bug: the scan pruned a position when
the cost of the grid step it was ABOUT TO TRY already exceeded the
incumbent, rather than the cost of the last step that FAILED. Nothing
says a position needs the 5% cut being priced — it may clear at 0.06%.

That fix shipped with no test. A mutation sweep put the old rule back
and all 151 tests stayed green, while the answer moved to a different
fund, a different asset, and 303x the price.
"""

import json
import pathlib

import numpy as np
import pytest

from firebreak.engine import run_cascade
from firebreak.search import at_least_n_breaches, find_weakest_shock
from firebreak.stabilise import Fix, find_cheapest_fix

REAL = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache" / "dataset.json"

# Settings where the cheapest position is NOT the first one scanned. Chosen
# because the pre-87c0217 prune returns 303x and 27x the true cost here.
OFF_PATH = [(7.5, 0.1, 1.05, 5), (8.0, 0.2, 1.05, 5)]


def scenario(leverage, gamma, band):
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


def brute_force_cheapest(condition, kw, shock):
    """Every position, bisected far past display precision. Slow and honest."""
    holdings = kw["holdings"]
    other = {k: v for k, v in kw.items() if k != "holdings"}
    total = holdings.sum()

    def fails(f, a, r):
        return condition(run_cascade(
            holdings=Fix(f, a, r, 0.0).apply(holdings), shock=shock, **other))

    best = None
    for f in range(holdings.shape[0]):
        for a in range(holdings.shape[1]):
            if holdings[f, a] <= 0 or fails(f, a, 1.0):
                continue
            lo, hi = 0.0, 1.0
            for _ in range(30):
                mid = (lo + hi) / 2.0
                if fails(f, a, mid):
                    lo = mid
                else:
                    hi = mid
            cost = holdings[f, a] * hi / total
            if best is None or cost < best[0]:
                best = (cost, f, a, hi)
    return best


@pytest.mark.parametrize("leverage,gamma,band,breaches", OFF_PATH)
def test_the_fix_is_the_cheapest_one_away_from_the_demo_settings(leverage, gamma, band, breaches):
    data, kw = scenario(leverage, gamma, band)
    condition = at_least_n_breaches(breaches)
    found = find_weakest_shock(condition=condition, **kw)
    assert found is not None, "these settings are supposed to break"

    fix = find_cheapest_fix(condition=condition, shock=found.shock, **kw)
    assert fix is not None

    truth = brute_force_cheapest(condition, kw, found.shock)
    assert truth is not None
    cost, f, a, _ = truth

    assert (fix.fund, fix.asset) == (f, a), (
        f"picked {data['funds'][fix.fund]}/{data['tickers'][fix.asset]} at cost "
        f"{fix.cost:.3e}, but {data['funds'][f]}/{data['tickers'][a]} costs {cost:.3e} "
        f"({fix.cost / cost:.1f}x cheaper). The scan discarded a position it had no "
        "grounds to discard."
    )
    assert fix.cost <= cost * 1.05, (
        f"cost {fix.cost:.3e} against a true minimum of {cost:.3e} "
        f"({fix.cost / cost:.2f}x too expensive)"
    )


def test_a_cheap_position_is_never_pruned_on_the_price_of_a_cut_it_does_not_need():
    """The pruning rule itself, stated directly.

    A position may only be skipped when its FLOOR cost — the last grid step
    that failed for it — already beats the incumbent. Pricing the step about
    to be tried instead throws away positions that would have cleared far
    below it, and does so more eagerly the better the incumbent gets.
    """
    data, kw = scenario(7.5, 0.1, 1.05)
    condition = at_least_n_breaches(5)
    found = find_weakest_shock(condition=condition, **kw)
    fix = find_cheapest_fix(condition=condition, shock=found.shock, **kw)
    assert fix is not None

    holdings = kw["holdings"]
    other = {k: v for k, v in kw.items() if k != "holdings"}
    # The winning cut is far below one grid step, so a scan that priced
    # positions at 5% could never have reached it.
    assert fix.reduction < 1.0 / 20, (
        f"reduction {fix.reduction:.6f} is a whole grid step or more; this test "
        "no longer exercises the case it was written for"
    )
    assert not condition(run_cascade(
        holdings=Fix(fix.fund, fix.asset, fix.reduction, 0.0).apply(holdings),
        shock=found.shock, **other)), "the reported fix does not actually clear the condition"
