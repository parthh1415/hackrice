"""Three things the screen showed that the payload couldn't support."""

import numpy as np
import pytest

from firebreak import api
from firebreak.search import at_least_n_breaches, find_weakest_shock


def test_the_after_panel_can_draw_the_cut_it_is_claiming():
    """The split view's whole visual claim is "this book is different".

    `before`/`after` carried no holdings, so the frontend fell back to the
    unpatched top-level matrix and drew byte-identical edges on both halves.
    The cut position — the one thing the beat is about — was invisible.
    """
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})

    assert "holdings" in result["after"], "after panel cannot draw the patched book"
    assert "holdings" in result["before"]

    fix = result["fix"]
    f, a = fix["fund_index"], fix["asset_index"]
    before = np.array(result["before"]["holdings"])
    after = np.array(result["after"]["holdings"])

    assert after[f][a] < before[f][a], "the cut position should be smaller after"
    np.testing.assert_allclose(after[f][a], before[f][a] * (1 - fix["reduction"]))


def test_the_boundary_marker_stays_on_its_own_grid():
    """`here.leverage` came straight off the query string, so a URL could put
    the "you are here" dot outside the plot entirely."""
    result = api.handle("/api/boundary?leverage=99&gamma=0.2", {})

    lo, hi = result["leverage_axis"][0], result["leverage_axis"][-1]
    assert lo <= result["here"]["leverage"] <= hi


def test_the_hero_number_resolves_the_precision_it_prints():
    """It prints 2dp. Bisection tolerance was 0.0005 — half a tenth of a point
    — so the second decimal was noise, and it was wrong: 5.28 against 5.27.
    """
    import json, pathlib

    data = json.loads((pathlib.Path(__file__).resolve().parents[1]
                       / "data" / "cache" / "dataset.json").read_text())
    m = len(data["funds"])
    kw = dict(
        holdings=np.array(data["holdings"]),
        leverage=np.full(m, 5.0), max_leverage=np.full(m, 5.25),
        target_leverage=np.full(m, 4.75), gamma=0.2, adv=np.array(data["adv"]),
    )

    from firebreak.search import DEFAULT_TOLERANCE

    coarse = find_weakest_shock(condition=at_least_n_breaches(3), tolerance=0.0005, **kw)
    default = find_weakest_shock(condition=at_least_n_breaches(3), **kw)
    fine = find_weakest_shock(condition=at_least_n_breaches(3),
                              tolerance=DEFAULT_TOLERANCE / 10, **kw)

    half_ulp_pp = 0.005  # half a unit in the last place of a 2dp percentage

    # Why the tolerance was tightened, stated as an assertion rather than left
    # in the docstring: the old one moved the answer by more than the last
    # digit on screen is worth, which is the 5.28-against-5.27 above.
    assert abs(default.pct - coarse.pct) > half_ulp_pp, (
        f"the old 0.0005 tolerance now agrees with the default to within "
        f"{abs(default.pct - coarse.pct):.5f}pp. If that is genuinely true the "
        "docstring's example is stale and this test needs rewriting"
    )

    # And the payoff: the digits we print do not move when the search is
    # tightened another ten-fold.
    #
    # This line used to read `round(default.pct, 2) == round(default.pct, 2)`
    # — x == x, an assertion with no way to fail. Inflating WeakestShock.pct by
    # 20% moved the hero number from 5.273% to 6.328% and this file still
    # reported three passes.
    assert f"{default.pct:.2f}" == f"{fine.pct:.2f}", (
        f"a ten-fold tighter search prints {fine.pct:.2f}% where the default "
        f"prints {default.pct:.2f}%; the second decimal is not earned"
    )
    assert abs(default.pct - fine.pct) <= half_ulp_pp

    # The two assertions above compare two searches to each other, so a factor
    # applied to `pct` cancels out of both and neither notices: multiplying
    # WeakestShock.pct by 1.2 moves the hero number 5.27% -> 6.33% and leaves
    # them green. What is missing is the unit contract itself — the percentage
    # on screen IS the magnitude the engine found, times a hundred, with the
    # sign carried by the word "falls" rather than by the number.
    assert default.magnitude < 0, "a break point is a fall; the magnitude is negative"
    assert default.pct == pytest.approx(abs(default.magnitude) * 100.0), (
        f"pct reports {default.pct} for a magnitude of {default.magnitude}. The "
        "hero number is a percentage of that magnitude and nothing else"
    )
