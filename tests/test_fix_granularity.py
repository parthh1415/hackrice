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

from firebreak import api
from firebreak.engine import run_cascade
from firebreak.search import at_least_n_breaches
from firebreak.stabilise import find_cheapest_fix

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


def test_a_smaller_cut_at_the_same_position_does_not_work():
    """Minimality, proven rather than asserted."""
    _, kw = scenario()
    condition = at_least_n_breaches(3)
    from firebreak.search import find_weakest_shock

    found = find_weakest_shock(condition=condition, **kw)
    fix = find_cheapest_fix(condition=condition, shock=found.shock, **kw)
    assert fix is not None

    holdings = kw["holdings"]
    slack = 0.004  # the search's own resolution on reduction
    smaller = max(0.0, fix.reduction - 2 * slack)
    patched = dict(kw, holdings=fix.__class__(
        fix.fund, fix.asset, smaller, 0.0).apply(holdings))

    assert condition(run_cascade(shock=found.shock, **patched)), (
        f"cutting only {smaller:.4f} already clears it — {fix.reduction:.4f} is not minimal"
    )


def test_the_fix_still_actually_works():
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})

    assert len(result["after"]["breached"]) < result["params"]["breaches"]
