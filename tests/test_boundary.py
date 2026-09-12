import pytest
import numpy as np

from firebreak.api import blend_toward_mean, handle


def test_blend_zero_leaves_the_books_exactly_as_filed():
    holdings = np.array([[80.0, 20.0], [10.0, 90.0]])

    np.testing.assert_allclose(blend_toward_mean(holdings, 0.0), holdings)


def test_blend_one_makes_every_fund_hold_the_same_weights():
    holdings = np.array([[80.0, 20.0], [10.0, 90.0]])

    blended = blend_toward_mean(holdings, 1.0)
    weights = blended / blended.sum(axis=1, keepdims=True)

    np.testing.assert_allclose(weights[0], weights[1])


def test_blending_never_changes_how_much_money_a_fund_has():
    holdings = np.array([[80.0, 20.0], [10.0, 90.0]])

    for blend in (0.0, 0.3, 0.7, 1.0):
        blended = blend_toward_mean(holdings, blend)
        np.testing.assert_allclose(blended.sum(axis=1), holdings.sum(axis=1))


def test_boundary_endpoint_returns_a_grid_of_amplification():
    result = handle("/api/boundary?gamma=0.2", {})

    grid = result["grid"]
    assert len(grid) == result["rows"]
    assert len(grid[0]) == result["cols"]
    assert all(cell >= 1.0 for row in grid for cell in row), "amplification can't be < 1"


def test_the_grid_gets_worse_as_leverage_rises():
    result = handle("/api/boundary?gamma=0.2", {})
    grid = result["grid"]

    # rows run low leverage -> high leverage; the crowded end of each row
    # should be at least as bad as the sparse end at high leverage
    assert max(grid[-1]) >= max(grid[0])


def test_negative_blend_makes_funds_more_distinct_not_less():
    from firebreak.api import mean_overlap

    holdings = np.array([[60.0, 30.0, 10.0], [50.0, 35.0, 15.0]])
    as_filed = mean_overlap(holdings)

    sharper = mean_overlap(blend_toward_mean(holdings, -1.0))
    blander = mean_overlap(blend_toward_mean(holdings, 1.0))

    assert sharper < as_filed < blander


def test_sharpening_still_keeps_every_fund_the_same_size():
    holdings = np.array([[60.0, 30.0, 10.0], [50.0, 35.0, 15.0]])

    for blend in (-1.0, -0.5, 0.0, 0.5, 1.0):
        blended = blend_toward_mean(holdings, blend)
        np.testing.assert_allclose(blended.sum(axis=1), holdings.sum(axis=1))
        assert (blended >= 0).all(), "no fund should end up short"


def test_the_map_has_the_leverage_cliff_its_docstring_advertises():
    """`_boundary`'s docstring names the reading to take off this map.

        "The sharp transition to read off this map is in leverage (1.00 at
        lambda~4.5 to 1.86 at lambda~5.0), not in crowding."

    That is the whole argument for showing the grid at all, and nothing
    checked it. `test_the_grid_gets_worse_as_leverage_rises` compares the
    maximum of the last row against the maximum of the first, which a grid
    that rose by 1% would also pass — it cannot see a cliff, only a slope.

    Measured at the crowding the real books actually have.
    """
    result = handle("/api/boundary?leverage=5&gamma=0.2&band=1.05", {})
    grid, levs, overlaps = result["grid"], result["leverage_axis"], result["overlap_axis"]
    here = result["here"]

    col = min(range(len(overlaps)), key=lambda j: abs(overlaps[j] - here["overlap"]))
    column = [grid[i][col] for i in range(len(levs))]

    quiet = [a for lev, a in zip(levs, column) if lev <= 4.1]
    assert quiet and all(a == pytest.approx(1.0) for a in quiet), (
        f"the low-leverage end is no longer flat at 1.00: {quiet}. Either the "
        "cliff has moved or the reference shock stopped being absorbable"
    )

    loud = [a for lev, a in zip(levs, column) if lev >= 4.9]
    assert loud and min(loud) > 1.5, (
        f"past the cliff the map no longer amplifies: {loud}"
    )

    # and it has to be a CLIFF, not a ramp: the jump across half a turn of
    # leverage is larger than everything that happens in the four turns below it
    jumps = [b - a for a, b in zip(column, column[1:])]
    biggest = max(jumps)
    assert biggest > 0.5, f"the steepest step is only {biggest:.3f}; there is no cliff here"
    at = levs[jumps.index(biggest)]
    assert 4.0 <= at <= 5.5, (
        f"the cliff moved to lambda {at:.2f}. The docstring, the pitch and any "
        "page drawing this map all say it sits between 4 and 5"
    )


def test_the_crowding_axis_is_not_monotone_and_that_is_on_purpose():
    """The map does NOT say "more crowding, more danger", and it must not be
    presented as though it did.

    A single-name reference shock means sharpening a fund onto its biggest
    names concentrates it into the shocked one — so amplification can fall as
    overlap rises. `_boundary`'s docstring says so, and a UI that drew this as
    a clean diagonal would be asserting a relationship the data does not have.

    If this ever starts passing monotonically, the reference shock has changed
    and the page's caveat needs rewriting with it.
    """
    result = handle("/api/boundary?leverage=5&gamma=0.2&band=1.05", {})
    grid, levs = result["grid"], result["leverage_axis"]

    rows_that_fall = 0
    for i, lev in enumerate(levs):
        row = grid[i]
        if any(b < a - 1e-9 for a, b in zip(row, row[1:])):
            rows_that_fall += 1
    assert rows_that_fall > 0, (
        "every row now rises monotonically with crowding. That is a different "
        "claim from the one this endpoint documents, and anything drawing the "
        "grid needs its caveat revisited"
    )
