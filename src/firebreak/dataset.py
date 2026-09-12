"""Turn real 13F filings into the matrix the engine eats.

Cached to disk on purpose. Citadel's information table alone is 8MB and we
are not fetching that live in front of a judge on conference wifi.
"""

import json
import pathlib

from .thirteenf import build_holdings, fetch_positions, latest_filings

ROOT = pathlib.Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data" / "universe.json"
CACHE = ROOT / "data" / "cache" / "dataset.json"

_MILLION = 1_000_000.0


def assemble(books, universe, adv_by_ticker, quarter):
    """Positions per fund -> the dict the API hands to the frontend.

    `universe` fixes the column order, so adv has to be reordered to match
    the tickers rather than trusting whatever order the config happened to
    be written in.

    ADV is written in the config in millions because nobody wants to read
    28000000000, but the engine divides dollars sold by ADV, so it has to
    come out of here in dollars. Getting this wrong makes price impact a
    million times too strong and the whole thing detonates on any shock.
    """
    funds, tickers, matrix = build_holdings(books, universe)
    return {
        "funds": funds,
        "tickers": tickers,
        "holdings": matrix.tolist(),
        "adv": [float(adv_by_ticker[t]) * _MILLION for t in tickers],
        "adv_units": "USD",
        "quarter": quarter,
        "source": "SEC 13F-HR",
    }


def load_dataset(refresh=False):
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())

    config = json.loads(UNIVERSE.read_text())
    books, periods, missing = {}, {}, []

    for name, cik in config["managers"].items():
        _, period, filings = latest_filings(cik)
        if not filings:
            missing.append(name)
            continue
        # a RESTATEMENT comes back alone; originals plus NEW HOLDINGS
        # supplements come back together and get summed
        merged = {}
        for filing in filings:
            for cusip, value in fetch_positions(cik, filing["accession"]).items():
                merged[cusip] = merged.get(cusip, 0.0) + value
        books[name] = merged
        periods[name] = period

    if missing:
        raise RuntimeError(
            f"no 13F found for {missing} — refusing to build a matrix with a "
            "manager silently absent"
        )
    distinct = set(periods.values())
    if len(distinct) > 1:
        raise RuntimeError(
            f"managers report different periods {periods} — one late filer would "
            "otherwise mix quarters into a single holdings matrix"
        )

    data = assemble(
        books, config["cusips"], config["adv_usd_millions"], distinct.pop()
    )
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2))
    return data
