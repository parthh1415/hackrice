import numpy as np

from firebreak.engine import Book


def levered_and_breached():
    """A=94, D=75, E=19, so L=4.95 — over a 4.2 limit."""
    book = Book(np.array([[60.0, 30.0, 10.0]]), leverage=np.array([4.0]))
    book.shock(np.array([-0.10, 0.0, 0.0]))
    return book


def test_selling_to_repay_debt_leaves_equity_alone():
    book = levered_and_breached()
    before = book.equity()[0]

    book.deleverage(max_leverage=np.array([4.2]), target_leverage=np.array([4.0]))

    # assets and debt both drop by the sale amount, so equity can't move
    np.testing.assert_allclose(book.equity()[0], before)


def test_deleveraging_lands_on_the_target():
    book = levered_and_breached()

    book.deleverage(max_leverage=np.array([4.2]), target_leverage=np.array([4.0]))

    np.testing.assert_allclose(book.leverage()[0], 4.0)
    np.testing.assert_allclose(book.assets()[0], 76.0)
    np.testing.assert_allclose(book.debt[0], 57.0)


def test_a_fund_inside_its_limit_sells_nothing():
    book = Book(np.array([[60.0, 30.0, 10.0]]), leverage=np.array([2.0]))
    book.shock(np.array([-0.10, 0.0, 0.0]))

    sold = book.deleverage(max_leverage=np.array([4.2]), target_leverage=np.array([4.0]))

    assert sold.sum() == 0.0


def test_liquidation_is_spread_pro_rata_across_the_book():
    book = levered_and_breached()

    sold = book.deleverage(max_leverage=np.array([4.2]), target_leverage=np.array([4.0]))

    # 18 dollars raised, book is 54/30/10 by value after the shock
    np.testing.assert_allclose(sold.sum(), 18.0)
    np.testing.assert_allclose(sold[0], 18.0 * 54.0 / 94.0)
    np.testing.assert_allclose(sold[1], 18.0 * 30.0 / 94.0)
    np.testing.assert_allclose(sold[2], 18.0 * 10.0 / 94.0)
