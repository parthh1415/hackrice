"""A user's portfolio, and the predicate that says it broke.

The pivot's whole claim is that the engine did not need changing — that
"this person crossed their loss limit" is the same shape of question as
"three funds breached", asked of a different observer. These tests are where
that claim is either true or not.
"""

import numpy as np
import pytest

from firebreak.portfolio import (
    CASH, Portfolio, UnknownSymbol, normalise, portfolio_loss,
    portfolio_loss_above, weight_vector,
)

TICKERS = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"]


def demo_rows():
    return [
        {"symbol": "NVDA", "market_value": 3600.0},
        {"symbol": "MSFT", "market_value": 3150.0},
        {"symbol": "AMZN", "market_value": 2250.0},
        {"symbol": "GOOGL", "market_value": 2250.0},
        {"symbol": "CASH", "market_value": 1050.0},
    ]


class Result:
    """Only the field the predicate reads."""
    def __init__(self, prices):
        self.prices = np.asarray(prices, dtype=float)


def test_weights_and_cash_account_for_the_whole_portfolio():
    """No residual. A vector that does not sum to one with cash is silently
    losing part of somebody's money."""
    p = normalise(demo_rows())
    vector, cash = weight_vector(p, TICKERS)

    assert vector.sum() + cash == pytest.approx(1.0, abs=1e-12)
    assert p.total_value == pytest.approx(12300.0)


def test_a_symbol_we_cannot_model_is_refused_not_dropped():
    """Dropping it renormalises every other weight and understates
    concentration — the same silent-undercount shape as the CUSIP bug."""
    p = normalise(demo_rows() + [{"symbol": "TSLA_WARRANT", "market_value": 500.0}])

    with pytest.raises(UnknownSymbol, match="TSLA_WARRANT"):
        weight_vector(p, TICKERS)


def test_duplicate_symbols_are_summed_not_overwritten():
    """Two lots of the same stock are not two opinions about how much you own."""
    p = normalise([
        {"symbol": "NVDA", "market_value": 1000.0, "quantity": 5},
        {"symbol": "nvda", "market_value": 500.0, "quantity": 2},
    ])

    assert len(p.holdings) == 1
    assert p.holdings[0].market_value == pytest.approx(1500.0)
    assert p.holdings[0].quantity == pytest.approx(7)


def test_quantity_and_price_reconstruct_a_market_value():
    p = normalise([{"symbol": "NVDA", "quantity": 20, "price": 182.5}])
    assert p.holdings[0].market_value == pytest.approx(3650.0)


def test_a_holding_with_no_value_is_an_error_not_a_zero():
    with pytest.raises(ValueError, match="cannot be weighted"):
        normalise([{"symbol": "NVDA", "quantity": 20}])


def test_no_shock_is_no_loss():
    """The control. If this is not exactly zero, everything downstream is
    measuring the arithmetic rather than the cascade."""
    vector, cash = weight_vector(normalise(demo_rows()), TICKERS)
    assert portfolio_loss(vector, cash, np.ones(len(TICKERS))) == pytest.approx(0.0, abs=1e-15)


def test_loss_is_the_weighted_price_move_and_cash_dilutes_it():
    vector, cash = weight_vector(normalise(demo_rows()), TICKERS)
    prices = np.ones(len(TICKERS))
    prices[0] = 0.5                       # NVDA halves

    nvda_weight = 3600.0 / 12300.0
    assert portfolio_loss(vector, cash, prices) == pytest.approx(nvda_weight * 0.5)
    assert cash == pytest.approx(1050.0 / 12300.0)


def test_the_predicate_flips_at_the_limit_and_not_before():
    """`>=`, deliberately: the user named the loss they would not tolerate,
    and a loss exactly equal to it is not tolerated either."""
    vector, cash = weight_vector(normalise(demo_rows()), TICKERS)
    nvda_weight = 3600.0 / 12300.0

    # a price move sized to land exactly on a 10% portfolio loss
    exact = np.ones(len(TICKERS))
    exact[0] = 1.0 - (0.10 / nvda_weight)

    breaks = portfolio_loss_above(vector, cash, 0.10)
    assert breaks(Result(exact)) is True

    just_under = np.ones(len(TICKERS))
    just_under[0] = 1.0 - (0.0999 / nvda_weight)
    assert breaks(Result(just_under)) is False


def test_an_all_cash_portfolio_cannot_break():
    """Not a trick: it is the boundary that proves the predicate reads
    exposure rather than the size of the shock."""
    vector, cash = weight_vector(normalise([{"symbol": CASH, "market_value": 5000.0}]), TICKERS)

    assert cash == pytest.approx(1.0)
    assert portfolio_loss_above(vector, cash, 0.01)(Result(np.zeros(len(TICKERS)))) is False


def test_a_portfolio_worth_nothing_is_refused_not_scored_as_a_total_loss():
    """The failure this guards is not a crash — it is a confident 0.00%.

    Without the guard, weights() returns {} for a worthless book, weight_vector
    hands back zeros with zero cash, and the vector no longer sums to 1. Then
    portfolio_loss computes 1 - 0 = 1.0, which clears every limit, the search's
    zero-shock check fires, and the screen reads "your portfolio breaks at a
    shock of 0.00%" — the app's single most alarming number, produced by a book
    that does not exist.

    test_portfolio_api.py already covered this through the endpoint. This adds
    the unit-level statement of it, plus the invariant the guard exists to
    protect — that the vector and the cash weight still sum to 1.

    Worth recording why it was written: pm_zero_value_scored was reporting
    GREEN, which looked like a hole. It was not. Its anchor, bare
    "    if total <= 0:", matched inside the eight-space copy of that line in
    weights(), so the mutation had never touched this guard at all. The anchor
    is fixed; the API test catches it now.
    """
    from firebreak.portfolio import Holding, Portfolio, weight_vector

    tickers = ["NVDA", "AAPL"]
    empty = Portfolio(holdings=[Holding(symbol="NVDA", market_value=0.0)])

    with pytest.raises(ValueError) as excinfo:
        weight_vector(empty, tickers)
    assert "no value" in str(excinfo.value)

    # and the same for a book whose values cancel out to nothing
    cancelled = Portfolio(holdings=[
        Holding(symbol="NVDA", market_value=1000.0),
        Holding(symbol="AAPL", market_value=-1000.0),
    ])
    with pytest.raises(ValueError):
        weight_vector(cancelled, tickers)

    # a real book still resolves, and still sums to 1
    real = Portfolio(holdings=[
        Holding(symbol="NVDA", market_value=3600.0),
        Holding(symbol="AAPL", market_value=2400.0),
    ])
    vector, cash = weight_vector(real, tickers)
    assert sum(vector) + cash == pytest.approx(1.0)

    # weights() carries its own copy of the guard. It is only ever called from
    # weight_vector, which raises first, so nothing else can reach this branch
    # — but it is a public method and the division is right there.
    assert empty.weights() == {}
    assert cancelled.weights() == {}
    assert real.weights()["NVDA"] == pytest.approx(0.6)
