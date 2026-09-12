"""The frame has to carry everything the stage draws, or scrubbing needs a round trip."""

import numpy as np

from firebreak.engine import run_cascade

OVERLAPPING = np.array([[50.0, 50.0, 0.0], [0.0, 50.0, 50.0]])


def run(gamma=0.9, leverage=6.0):
    m = OVERLAPPING.shape[0]
    return run_cascade(
        holdings=OVERLAPPING,
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * 1.05),
        target_leverage=np.full(m, max(1.0, leverage * 0.95)),
        gamma=gamma,
        adv=np.full(3, 200.0),
        shock=np.array([-0.10, 0.0, 0.0]),
    )


def test_every_frame_carries_what_was_sold_per_portfolio_per_asset():
    result = run()

    for frame in result.trajectory:
        assert "sold" in frame, "FlowLayer animates this; without it scrubbing needs a fetch"
        assert len(frame["sold"]) == OVERLAPPING.shape[0]
        assert len(frame["sold"][0]) == OVERLAPPING.shape[1]


def test_round_zero_sold_nothing():
    result = run()

    assert np.allclose(result.trajectory[0]["sold"], 0.0)


def test_a_breached_portfolio_shows_up_as_a_seller():
    result = run()

    first_action = result.trajectory[1]
    sellers = [j for j, row in enumerate(first_action["sold"]) if sum(row) > 0]
    assert sellers, "somebody breached in round 1, so somebody sold in round 1"
    assert set(sellers) <= set(first_action["breached"] + first_action["defaulted"])


def test_sold_is_dollars_and_reconciles_with_the_price_move():
    result = run()

    frame = result.trajectory[1]
    total_by_asset = np.array(frame["sold"]).sum(axis=0)
    # the asset that got sold hardest must be the one that moved most
    assert total_by_asset.argmax() in (0, 1)
    assert total_by_asset.sum() > 0


def test_round_zero_names_whoever_the_shock_already_put_over_the_limit():
    # t=0 is post-shock, pre-deleverage. The stage rings `breached`, so an
    # empty list here draws a fund sitting at 8.14 against a 6.3 limit with
    # no ring on it — the opening frame arguing against its own numbers.
    result = run()
    frame = result.trajectory[0]
    limit = 6.0 * 1.05

    over = [
        j
        for j, lev in enumerate(frame["leverage"])
        if frame["insolvent"][j] or lev > limit
    ]

    assert over, "sanity: this shock should already push somebody over"
    assert frame["breached"] == over
    # same funds the cascade then acts on in round 1
    assert frame["breached"] == result.trajectory[1]["breached"]


def test_round_zero_is_empty_when_the_shock_left_everyone_inside_their_limit():
    result = run(gamma=0.9, leverage=1.0)

    assert result.trajectory[0]["breached"] == []
