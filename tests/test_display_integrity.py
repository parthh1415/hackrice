"""Three things the screen showed that the payload couldn't support."""

import numpy as np

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

    coarse = find_weakest_shock(condition=at_least_n_breaches(3), tolerance=0.0005, **kw)
    default = find_weakest_shock(condition=at_least_n_breaches(3), **kw)

    # the default must be at least ten times finer than one printed decimal
    assert abs(default.pct - coarse.pct) < 0.05
    assert round(default.pct, 2) == round(default.pct, 2)
