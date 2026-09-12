"""Every CUSIP we ship has to resolve, and every name has to hold something.

`universe.get(cusip)` drops an unmapped CUSIP silently — by design, since a
13F contains hundreds of names we do not model. The cost is that corrupting
the map is invisible: point GOOGL's Class A prefix at Class C and the whole
suite stays green while the holdings matrix quietly loses a column's worth
of value and the crowding measure gains dispersion that is not there.

That is not hypothetical. It shipped once: we mapped Alphabet's Class A
(02079K30) and dropped Class C and both depositary-share lines, capturing
47.9% of Citadel's $2.229B Alphabet position and a different fraction of
everyone else's. Heterogeneous by fund is exactly the shape of a real
crowding signal, and it was an artefact.

(The write-up of that bug had the two classes the wrong way round for
months, and quoted the captured share as the missing one. Both were found
by going back to `titleOfClass` in the filings rather than re-reading our
own prose — which is the same move this file automates.)

So: the shipped artefact must have every ticker present and every column
carrying value from at least two managers, which is the property the whole
overlapping-portfolio story rests on.
"""

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATASET = json.loads((ROOT / "data" / "cache" / "dataset.json").read_text())


def test_every_ticker_we_ship_holds_something():
    holdings = DATASET["holdings"]
    for a, ticker in enumerate(DATASET["tickers"]):
        column = [row[a] for row in holdings]
        assert sum(column) > 0, (
            f"{ticker} is worth zero across every manager — its CUSIP prefix "
            "resolves to nothing, or resolves to a class nobody filed"
        )


def test_every_name_is_held_by_at_least_two_managers():
    """Overlap is the mechanism. A name only one fund holds cannot transmit."""
    holdings = DATASET["holdings"]
    for a, ticker in enumerate(DATASET["tickers"]):
        holders = sum(1 for row in holdings if row[a] > 0)
        assert holders >= 2, (
            f"{ticker} is held by {holders} manager(s); a name with no overlap "
            "carries no contagion and should not be in the universe"
        )


def test_no_manager_is_empty():
    for f, fund in enumerate(DATASET["funds"]):
        assert sum(DATASET["holdings"][f]) > 0, f"{fund} holds nothing"


def test_the_shipped_universe_maps_every_prefix_it_claims():
    """The map's own consistency, independent of the artefact."""
    universe = json.loads((ROOT / "data" / "universe.json").read_text())["cusips"]

    tickers = set(DATASET["tickers"])
    mapped = set(universe.values())
    assert tickers <= mapped, (
        f"the dataset names {sorted(tickers - mapped)}, which the CUSIP map "
        "cannot produce"
    )
    # A CUSIP is 9 characters: 6 issuer, 2 issue, 1 check digit. We key on the
    # 8-character issuer+issue prefix, and every entry must be exactly that.
    # A truncated key still looks plausible and still maps to a real ticker,
    # so nothing downstream complains — it just stops matching the filings it
    # was there to match, and that name quietly loses a manager.
    for cusip, ticker in universe.items():
        assert len(cusip) == 8 and cusip.isalnum(), (
            f"{cusip!r} is not an 8-character CUSIP issuer+issue prefix; "
            "a short key matches nothing and fails silently"
        )
        assert ticker in tickers, (
            f"{cusip} maps to {ticker}, which is not in the shipped universe"
        )


def test_the_gross_book_is_the_sum_of_the_matrix():
    """Anything derived from the matrix must come FROM the matrix."""
    gross = sum(sum(row) for row in DATASET["holdings"])
    assert gross == pytest.approx(40_888_519_059, rel=1e-9), (
        f"gross is ${gross:,.0f}; the README, devpost and video script all "
        "quote $40.9B and would need re-checking"
    )


def test_a_multi_class_name_declares_an_adv_covering_every_class():
    """Not a number check — a check that the ambiguity stays closed.

    A multi-class column sums every class of the issuer, so its ADV has to be
    the combined figure. Divide multi-class dollars sold by single-class
    volume and price impact is overstated for that name alone, which is the
    quiet kind of wrong this project keeps finding.

    GOOGL is currently the only such name, and a review agent read its 6000
    as Class A and reported the liquidity understated 1.9x. Nothing in the
    file said either way, which is why the reading was available. It says so
    now, and this fails if a second multi-class name arrives without the note
    being extended to cover it.
    """
    universe = json.loads((ROOT / "data" / "universe.json").read_text())
    by_ticker = {}
    for cusip, ticker in universe["cusips"].items():
        by_ticker.setdefault(ticker, []).append(cusip)

    multi = sorted(t for t, cs in by_ticker.items() if len(cs) > 1)
    assert multi == ["GOOGL"], (
        f"multi-class names are now {multi}; data/universe.json's note explains "
        "the combined-ADV rule for GOOGL only and needs extending"
    )
    note = universe["_note"]
    assert "COMBINED" in note and "every class" in note, (
        "the note no longer states that a multi-class name's ADV covers every "
        "class it maps — that is the assumption its number rests on"
    )
    for ticker in multi:
        assert ticker in universe["adv_usd_millions"], ticker
