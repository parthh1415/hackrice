import numpy as np

from firebreak.engine import Book


def test_requested_leverage_is_what_you_get():
    # two funds, three assets, dollar holdings at t0 (prices start at 1.0)
    holdings = np.array([[60.0, 30.0, 10.0], [20.0, 20.0, 60.0]])

    book = Book(holdings, leverage=np.array([4.0, 2.0]))

    assert book.leverage() == [4.0, 2.0]


def test_shock_hits_equity_harder_than_assets():
    # one fund, 60% of the book in asset 0, levered 4x
    book = Book(np.array([[60.0, 30.0, 10.0]]), leverage=np.array([4.0]))

    book.shock(np.array([-0.10, 0.0, 0.0]))

    # assets fall 6%, but equity is a quarter of assets, so it falls 24%
    assert book.assets()[0] == 94.0
    assert book.equity()[0] == 19.0
    assert book.leverage()[0] > 4.0
