import numpy as np

from firebreak.dataset import assemble


def test_assemble_builds_a_matrix_in_universe_order():
    universe = {"67066G10": "NVDA", "03783310": "AAPL"}
    books = {"Alpha": {"67066G10": 100.0}, "Beta": {"03783310": 50.0}}
    adv = {"NVDA": 0.001, "AAPL": 0.0005}  # millions

    data = assemble(books, universe, adv, quarter="2026-08-14")

    assert data["funds"] == ["Alpha", "Beta"]
    assert data["tickers"] == ["NVDA", "AAPL"]
    np.testing.assert_allclose(data["holdings"], [[100.0, 0.0], [0.0, 50.0]])
    np.testing.assert_allclose(data["adv"], [1000.0, 500.0])  # dollars
    assert data["quarter"] == "2026-08-14"


def test_adv_follows_the_ticker_order_not_the_dict_order():
    universe = {"03783310": "AAPL", "67066G10": "NVDA"}
    books = {"Alpha": {"03783310": 10.0, "67066G10": 20.0}}
    adv = {"NVDA": 0.000999, "AAPL": 0.000111}  # millions

    data = assemble(books, universe, adv, quarter="x")

    assert data["tickers"] == ["AAPL", "NVDA"]
    np.testing.assert_allclose(data["adv"], [111.0, 999.0])  # dollars, ticker order


def test_adv_is_converted_to_dollars_to_match_the_holdings():
    # holdings come off 13F in dollars; the config writes ADV in millions
    # because nobody wants to read 28000000000. the engine divides one by
    # the other, so they have to be in the same unit or impact is off by 1e6.
    universe = {"67066G10": "NVDA"}
    books = {"Alpha": {"67066G10": 1_000_000.0}}
    adv_millions = {"NVDA": 28000.0}

    data = assemble(books, universe, adv_millions, quarter="x")

    assert data["adv"] == [28_000_000_000.0]
    assert data["adv_units"] == "USD"
