import json

import numpy as np
import pytest

from minima.dataset import UNIVERSE, assemble, manager_ciks


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


def test_a_manager_can_file_under_more_than_one_cik():
    # Two Sigma Investments (1179392) and Two Sigma Advisers (1478735) are
    # separate registrants filing separate 13Fs for the same quarter. Read
    # only the first and the second book is simply missing from the system.
    config = {"managers": {"Two Sigma": [1179392, 1478735], "Citadel": 1423053}}

    assert manager_ciks(config) == {
        "Two Sigma": [1179392, 1478735],
        "Citadel": [1423053],
    }


def test_the_same_cik_under_two_managers_is_refused():
    # it would be fetched twice and summed into two different rows, which
    # inflates gross exposure and invents overlap that isn't there
    config = {"managers": {"Two Sigma": [1179392, 1478735], "Also": 1478735}}

    with pytest.raises(ValueError, match="1478735"):
        manager_ciks(config)


def test_a_manager_with_no_cik_at_all_is_refused():
    with pytest.raises(ValueError, match="Ghost"):
        manager_ciks({"managers": {"Ghost": []}})


def test_the_shipped_universe_has_no_cik_under_two_managers():
    config = json.loads(UNIVERSE.read_text())

    ciks = [cik for group in manager_ciks(config).values() for cik in group]

    assert len(ciks) == len(set(ciks))
