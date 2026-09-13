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


def assemble(books, universe, adv_by_ticker, quarter, observer_only=()):
    """Positions per fund -> the dict the API hands to the frontend.

    `universe` fixes the column order, so adv has to be reordered to match
    the tickers rather than trusting whatever order the config happened to
    be written in.

    ADV is written in the config in millions because nobody wants to read
    28000000000, but the engine divides dollars sold by ADV, so it has to
    come out of here in dollars. Getting this wrong makes price impact a
    million times too strong and the whole thing detonates on any shock.
    """
    funds, tickers, matrix, kept = build_holdings(books, universe)
    observer_only = set(observer_only)
    unknown = observer_only - set(tickers)
    if unknown:
        raise ValueError(
            f"observer-only names are not in the CUSIP universe: {sorted(unknown)}"
        )
    return {
        "funds": funds,
        # which rows of the original manager list survived. anything that
        # builds a per-fund vector off that list has to subset it by this or
        # a dropped manager slides every later parameter onto its neighbour.
        "fund_indices": kept,
        "tickers": tickers,
        "holdings": matrix.tolist(),
        "adv": [float(adv_by_ticker[t]) * _MILLION for t in tickers],
        "adv_units": "USD",
        "quarter": quarter,
        "source": "SEC 13F-HR",
        # A portfolio security can be directly stressed even when none of the
        # selected 13F managers owns it. It is included in portfolio loss, but
        # has no manager sale to feed back through the institutional network.
        "observer_only": [ticker for ticker in tickers if ticker in observer_only],
    }


def manager_ciks(config):
    """manager name -> the list of CIKs whose books make up that manager.

    One firm can run several registrants. Two Sigma Investments (1179392) and
    Two Sigma Advisers (1478735) both file a 13F-HR for the same quarter under
    separate CIKs, so reading one of them and calling it Two Sigma leaves a
    whole book out of the system — the row is too small and its weights are
    whatever the half we happened to pick was holding.

    Config writes either a bare CIK or a list of them. Positions across a
    manager's CIKs are summed into one row, which is only safe if no CIK is
    claimed twice, so that's checked here rather than discovered as a fund
    that somehow doubled in size.
    """
    groups, owner = {}, {}
    for name, entry in config["managers"].items():
        ciks = [entry] if isinstance(entry, (int, str)) else list(entry)
        ciks = [int(cik) for cik in ciks]
        if not ciks:
            raise ValueError(f"{name} has no CIK — nothing to fetch")
        for cik in ciks:
            if cik in owner:
                raise ValueError(
                    f"CIK {cik} is listed under both {owner[cik]} and {name}; "
                    "it would be counted twice"
                )
            owner[cik] = name
        groups[name] = ciks
    return groups


def load_dataset(refresh=False):
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())

    config = json.loads(UNIVERSE.read_text())
    books, periods, missing = {}, {}, []

    for name, ciks in manager_ciks(config).items():
        # every CIK listed for a manager is an assertion that it files. one
        # going quiet is the undercount we're fixing, so it's an error, not
        # a book that silently shrinks.
        merged = {}
        for cik in ciks:
            _, period, filings = latest_filings(cik)
            if not filings:
                missing.append(f"{name} (CIK {cik})")
                continue
            # a RESTATEMENT comes back alone; originals plus NEW HOLDINGS
            # supplements come back together and get summed
            for filing in filings:
                for cusip, value in fetch_positions(cik, filing["accession"]).items():
                    # SUMMED, which is right if a NEW HOLDINGS supplement only
                    # ever carries positions the original did not have — the
                    # rule thirteenf.py states, and which this repo has never
                    # checked against the primary source. If a supplement can
                    # instead RESTATE a line that already exists, summing
                    # double-counts it and this should take the supplement's
                    # value rather than add to it.
                    #
                    # Not reachable in the committed data: replaying the ingest
                    # offline, every one of the six registrants resolves to a
                    # single filing, so this loop never runs twice for anybody
                    # and no CUSIP is seen from two filings. Left as a sum and
                    # written down rather than changed, because choosing
                    # between two merges on an unread source is how you get a
                    # confident wrong number — which is the failure this file's
                    # whole history is about. Read FAQ 58 before touching it.
                    merged[cusip] = merged.get(cusip, 0.0) + value
            periods[f"{name} (CIK {cik})"] = period
        books[name] = merged

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
        books, config["cusips"], config["adv_usd_millions"], distinct.pop(),
        observer_only=config.get("observer_only", ()),
    )
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2))
    return data
