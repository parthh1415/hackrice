import numpy as np

from minima.engine import run_cascade
from minima.search import at_least_n_breaches
from minima.stabilise import find_cheapest_fix

CROWDED = np.array([[20.0, 80.0, 0.0], [0.0, 80.0, 20.0]])
ADV = np.array([2000.0, 2000.0, 2000.0])


def system(leverage=6.0):
    m = CROWDED.shape[0]
    return dict(
        holdings=CROWDED,
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * 1.05),
        target_leverage=np.full(m, max(1.0, leverage * 0.95)),
        gamma=0.5,
        adv=ADV,
    )


BREAKING_SHOCK = np.array([0.0, -0.05, 0.0])


def test_the_fix_actually_prevents_the_failure():
    condition = at_least_n_breaches(2)
    assert condition(run_cascade(shock=BREAKING_SHOCK, **system())), "shock should break it first"

    fix = find_cheapest_fix(condition=condition, shock=BREAKING_SHOCK, **system())

    assert fix is not None
    patched = system()
    patched["holdings"] = fix.apply(CROWDED)
    assert not condition(run_cascade(shock=BREAKING_SHOCK, **patched))


def test_the_fix_is_a_real_instruction_not_a_score():
    fix = find_cheapest_fix(
        condition=at_least_n_breaches(2), shock=BREAKING_SHOCK, **system()
    )

    assert fix.fund in (0, 1)
    assert fix.asset in (0, 1, 2)
    assert 0.0 < fix.reduction <= 1.0
    assert 0.0 < fix.cost < 1.0


def test_an_already_safe_system_needs_no_fix():
    safe = system(leverage=1.0)
    tiny = np.array([0.0, -0.001, 0.0])

    fix = find_cheapest_fix(condition=at_least_n_breaches(2), shock=tiny, **safe)

    assert fix is None or fix.cost == 0.0
