import numpy as np

from firebreak.engine import run_cascade
from firebreak.search import (
    amplification_above,
    at_least_n_breaches,
    find_weakest_shock,
    system_loss_above,
)

# asset 1 is the crowded one — 80% of both books. assets 0 and 2 are
# each held by a single fund. so asset 1 should be the cheapest way in.
OVERLAPPING = np.array(
    [
        [20.0, 80.0, 0.0],
        [0.0, 80.0, 20.0],
    ]
)
ADV = np.array([2000.0, 2000.0, 2000.0])


def system(leverage=6.0):
    m = OVERLAPPING.shape[0]
    return dict(
        holdings=OVERLAPPING,
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * 1.05),
        target_leverage=np.full(m, leverage * 0.95),
        gamma=0.5,
        adv=ADV,
    )


def test_it_finds_a_shock_that_actually_breaks_things():
    found = find_weakest_shock(condition=at_least_n_breaches(2), **system())

    assert found is not None
    result = run_cascade(shock=found.shock, **system())
    assert len(result.breached) >= 2


def test_the_shock_it_finds_is_close_to_the_smallest_one():
    found = find_weakest_shock(condition=at_least_n_breaches(2), tolerance=0.001, **system())

    # back it off by more than the tolerance and the system should survive
    weaker = found.shock * 0.95
    result = run_cascade(shock=weaker, **system())
    assert len(result.breached) < 2


def test_an_unbreakable_system_reports_no_shock_found():
    # unlevered funds can't breach no matter what you throw at them
    m = OVERLAPPING.shape[0]
    unbreakable = dict(
        holdings=OVERLAPPING,
        leverage=np.ones(m),
        max_leverage=np.ones(m) * 1.05,
        target_leverage=np.ones(m),
        gamma=0.5,
        adv=ADV,
    )

    assert find_weakest_shock(condition=at_least_n_breaches(1), **unbreakable) is None


def test_it_picks_the_cheapest_asset_to_attack():
    found = find_weakest_shock(condition=at_least_n_breaches(2), **system())

    # asset 1 is 80% of both books; assets 0 and 2 are 20% of one book each.
    # the crowded name has to be the cheaper way in.
    assert found.asset == 1


def test_a_harder_condition_needs_a_bigger_shock():
    easy = find_weakest_shock(condition=at_least_n_breaches(1), **system())
    hard = find_weakest_shock(condition=at_least_n_breaches(2), **system())

    assert abs(hard.magnitude) >= abs(easy.magnitude)


def test_loss_and_amplification_conditions_both_work():
    by_loss = find_weakest_shock(condition=system_loss_above(0.30), **system())
    by_amp = find_weakest_shock(condition=amplification_above(1.2), **system())

    assert by_loss is not None
    assert by_amp is not None
    assert run_cascade(shock=by_loss.shock, **system()).final_loss > 0.30
    assert run_cascade(shock=by_amp.shock, **system()).amplification > 1.2
