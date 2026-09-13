import numpy as np

from minima.engine import run_cascade

# three assets. fund 0 owns the shocked name and shares asset 1 with fund 1.
# fund 1 has never heard of asset 0 — it only gets hurt through asset 1.
OVERLAPPING = np.array(
    [
        [50.0, 50.0, 0.0],
        [0.0, 50.0, 50.0],
    ]
)
ADV = np.array([200.0, 200.0, 200.0])


def cascade(gamma, leverage=5.0, shock0=-0.10, holdings=OVERLAPPING, adv=ADV):
    m = holdings.shape[0]
    shock = np.zeros(holdings.shape[1])
    shock[0] = shock0
    return run_cascade(
        holdings=holdings,
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * 1.05),
        target_leverage=np.full(m, max(1.0, leverage * 0.95)),
        gamma=gamma,
        adv=adv,
        shock=shock,
    )


def test_no_shock_means_nothing_happens():
    result = cascade(gamma=0.5, shock0=0.0)

    assert result.rounds == 0
    assert result.breached == []
    np.testing.assert_allclose(result.final_loss, 0.0)


def test_without_price_impact_there_is_no_amplification():
    # funds still breach and still sell, but selling moves nothing,
    # so nobody else is hurt. this is the control case.
    result = cascade(gamma=0.0)

    assert result.rounds == 1
    np.testing.assert_allclose(result.amplification, 1.0)


def test_selling_pushes_prices_down():
    result = cascade(gamma=0.5)

    assert (result.prices < 1.0).any()
    assert result.prices[1] < 1.0  # asset 1 was never shocked, only sold


def test_contagion_reaches_a_fund_with_no_direct_exposure():
    result = cascade(gamma=0.9, leverage=6.0)

    assert 1 in result.breached, "fund 1 holds no asset 0 — it should still get dragged in"
    assert result.rounds >= 2
    assert result.amplification > 1.0


def test_unlevered_funds_never_breach():
    result = cascade(gamma=0.9, leverage=1.0, shock0=-0.40)

    assert result.breached == []
    np.testing.assert_allclose(result.amplification, 1.0)


def test_damage_never_decreases_as_the_shock_grows():
    worst_loss, worst_count = -np.inf, -1
    for pct in range(0, 31):
        result = cascade(gamma=0.6, shock0=-pct / 100)
        assert result.final_loss >= worst_loss - 1e-9, f"loss went down at {pct}%"
        assert len(result.breached) >= worst_count, f"breaches went down at {pct}%"
        worst_loss, worst_count = result.final_loss, len(result.breached)


def test_a_disjoint_book_is_not_contagion():
    # nobody shares a name, so fund 1 cannot be touched
    disjoint = np.array([[100.0, 0.0, 0.0], [0.0, 0.0, 100.0]])

    result = cascade(gamma=0.9, leverage=6.0, holdings=disjoint)

    assert 1 not in result.breached


def test_a_cascade_that_settles_on_the_last_round_is_not_called_divergent():
    """`converged` was false whenever the final permitted round had sellers in
    it, even when that round was the one that settled the system. The UI prints
    "did not converge" off this, so it was libelling runs that finished.
    """
    from minima.engine import run_cascade

    holdings = np.array([[60.0, 40.0], [30.0, 70.0]])
    kwargs = dict(
        leverage=np.array([6.0, 6.0]),
        max_leverage=np.array([6.3, 6.3]),
        target_leverage=np.array([5.7, 5.7]),
        gamma=0.4,
        adv=np.array([200.0, 200.0]),
        shock=np.array([-0.05, 0.0]),
    )

    unhurried = run_cascade(holdings=holdings, max_rounds=24, **kwargs)
    assert unhurried.converged and unhurried.rounds >= 2

    # exactly enough budget: it finishes, so it converged
    tight = run_cascade(holdings=holdings, max_rounds=unhurried.rounds, **kwargs)
    assert tight.rounds == unhurried.rounds
    assert tight.converged is True

    # one round short: it genuinely didn't finish
    cut = run_cascade(holdings=holdings, max_rounds=unhurried.rounds - 1, **kwargs)
    assert cut.converged is False
