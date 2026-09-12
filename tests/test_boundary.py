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
