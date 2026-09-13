import numpy as np

from minima.engine import run_cascade
from minima.search import (
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
        target_leverage=np.full(m, max(1.0, leverage * 0.95)),
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


# --- what the search can and cannot promise -------------------------------


def _staggered_default_book():
    """Two funds behind one asset, one fund behind another, one bridging both.

    The bridge is the whole point: it's the only seller in asset 0, and how
    hard it sells depends on how much distress reaches it before it defaults.
    """
    return dict(
        holdings=np.array([
            [804665840.27, 0.0],            # only asset 0 — hurt second-hand
            [882371564.30, 836019928.60],   # the bridge
            [0.0, 538184754.06],
            [0.0, 970176934.93],
            [0.0, 986797182.03],
        ]),
        leverage=np.array([5.324533, 2.590321, 6.621589, 6.515861, 3.852326]),
        max_leverage=np.array([6.134146, 2.984188, 7.628424, 7.506619, 4.438085]),
        target_leverage=np.array([4.163121, 2.025308, 5.177258, 5.094591, 3.012039]),
        gamma=0.9275268799821211,
        adv=np.array([10770182322.75, 8583520840.37]),
    )


def test_breach_count_is_not_actually_monotone_in_shock_size():
    """The docstrings used to promise it was, and the reverse search is built
    on that promise. It doesn't hold.

    Bigger shock, fewer breaches: at -14% the distressed funds die one round
    apart, so the bridge fund is still solvent when the second wave hits, gets
    dragged well past its limit and dumps asset 0 hard enough to break the
    fund standing behind it. At -16% they all default in round one, the bridge
    breaches by a hair instead, sells little, and that fund never goes.
    """
    book = _staggered_default_book()

    counts = {}
    for drop in (0.14, 0.16):
        result = run_cascade(shock=np.array([0.0, -drop]), **book)
        counts[drop] = len(result.breached)

    assert counts[0.16] < counts[0.14], counts


def test_the_shock_it_reports_really_does_break_you():
    """Monotonicity is what would make the answer *minimal*. Without it the
    guarantee is weaker and worth stating: the reported shock trips the
    condition, and no whole-percent step below it does.
    """
    book = _staggered_default_book()
    condition = at_least_n_breaches(4)

    found = find_weakest_shock(condition=condition, **book)
    assert found is not None

    at = run_cascade(shock=found.shock, **book)
    assert condition(at), "the hero number has to be a shock that actually breaks it"

    step = 0.01
    below = abs(found.magnitude) - step
    while below > 0:
        vector = np.zeros(book["holdings"].shape[1])
        vector[found.asset] = -below
        assert not condition(run_cascade(shock=vector, **book)), (
            f"a {below:.2%} drop on asset {found.asset} already breaks it; "
            f"the search reported {found.pct:.3f}%"
        )
        below -= step
