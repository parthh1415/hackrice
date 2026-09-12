"""The hero prints two decimals. The search has to have earned them.

Loosening `DEFAULT_TOLERANCE` from 5e-5 to 5e-4 is a one-character change
that a future reader might make for speed. It costs nothing visible and
quadruples the answer:

    5e-5 : reduction 0.00073242   sell $1,731,560   hero 5.273438%
    5e-4 : reduction 0.00288086   sell $6,810,803   hero 5.281250%

That is precisely the fake-precision regression `docs/devpost.md` claims was
fixed — the hero's second decimal being noise, and worse, being wrong. The
recordings catch it today, but only incidentally: the failure reads
"recording does not match live", which tells the next person nothing about
what they actually broke.

So this states the relationship directly. The number of decimals the UI
prints is a claim about how finely the search resolved, and the two have to
stay tied to each other.
"""

import json
import pathlib

import numpy as np
import pytest

from firebreak.search import DEFAULT_TOLERANCE, at_least_n_breaches, find_weakest_shock

WEB = pathlib.Path(__file__).resolve().parents[1] / "web" / "app.js"
REAL = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache" / "dataset.json"

# `pct2` in web/app.js — the hero, and every percentage beside it.
DISPLAYED_DECIMALS = 2


def test_the_ui_still_prints_the_number_of_decimals_this_file_assumes():
    """If the UI's precision changes, the bound below has to be revisited."""
    assert f"toFixed({DISPLAYED_DECIMALS})" in WEB.read_text(), (
        f"web/app.js no longer formats percentages to {DISPLAYED_DECIMALS} decimals; "
        "the tolerance bound in this file was derived from that and needs redoing"
    )


def test_the_search_resolves_finer_than_the_last_digit_it_prints():
    """Half a unit in the last place, in percentage points.

    Two decimals of a percentage is a 0.01pp grid, so an answer is only
    honest to that digit if the search pins it to better than 0.005pp. At
    5e-5 the search resolves to 0.005pp exactly — the tightest it can be and
    still justify what is on screen, which is why it was set there.
    """
    half_ulp_pp = 0.5 * 10 ** -DISPLAYED_DECIMALS
    assert DEFAULT_TOLERANCE * 100.0 <= half_ulp_pp, (
        f"the search resolves to {DEFAULT_TOLERANCE * 100:.4f}pp but the UI prints "
        f"{DISPLAYED_DECIMALS} decimals, which claims {half_ulp_pp}pp. Either tighten "
        "DEFAULT_TOLERANCE or print fewer digits — the screen must not promise "
        "precision the search did not deliver."
    )


def test_tightening_the_tolerance_further_does_not_move_the_answer():
    """Convergence, checked rather than assumed.

    If the reported shock still moves when the tolerance is tightened by a
    factor of ten, the current tolerance had not converged and the digits on
    screen are still partly noise.
    """
    data = json.loads(REAL.read_text())
    m = len(data["funds"])
    kw = dict(
        holdings=np.array(data["holdings"]),
        leverage=np.full(m, 5.0),
        max_leverage=np.full(m, 5.25),
        target_leverage=np.full(m, 4.75),
        gamma=0.2,
        adv=np.array(data["adv"]),
    )
    condition = at_least_n_breaches(3)

    coarse = find_weakest_shock(condition=condition, **kw)
    fine = find_weakest_shock(condition=condition, tolerance=DEFAULT_TOLERANCE / 10, **kw)
    assert coarse is not None and fine is not None

    moved_pp = abs(coarse.pct - fine.pct)
    half_ulp_pp = 0.5 * 10 ** -DISPLAYED_DECIMALS
    assert moved_pp <= half_ulp_pp, (
        f"a ten-fold tighter search moves the answer by {moved_pp:.5f}pp, which is "
        f"more than the {half_ulp_pp}pp the display claims. The printed digits are "
        "not all earned."
    )
    assert coarse.asset == fine.asset, "and it should not change which name breaks first"
