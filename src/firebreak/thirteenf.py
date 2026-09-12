"""Reading 13F-HR information tables off EDGAR.

Everything that talks to the network lives at the bottom; everything above it
is pure so it can actually be tested.

Three things bite you here and none of them are obvious:

1. Options are in the same table as stock. Citadel's last filing was 16,127
   rows of which only 8,500 were actual shares — sum the `value` column
   blind and you overstate equity exposure by about half.
2. The XML carries default, n1: and xsi: namespaces, which makes
   ElementTree miserable. Regex over the record blocks is less clever and
   more reliable.
3. The same issuer shows up once per internal manager, so you have to
   aggregate by CUSIP or you'll count a position two or three times.
"""

import collections
import gzip
import json
import re
import urllib.request

import numpy as np

_RECORD = re.compile(r"<(?:\w+:)?infoTable>(.*?)</(?:\w+:)?infoTable>", re.S)
_CUSIP = re.compile(r"<(?:\w+:)?cusip>\s*([^<\s]+)", re.I)
_VALUE = re.compile(r"<(?:\w+:)?value>\s*([\d.]+)", re.I)
_PUTCALL = re.compile(r"<(?:\w+:)?putCall>\s*\w", re.I)
_AMT_TYPE = re.compile(r"<(?:\w+:)?sshPrnamtType>\s*(\w+)", re.I)

# CUSIPs are 9 chars but the 9th is a check digit; 8 is the issue-level key
_KEY_LEN = 8


def parse_info_table(xml_text):
    """CUSIP prefix -> total reported dollar value of *share* positions."""
    totals = collections.defaultdict(float)

    for match in _RECORD.finditer(xml_text):
        record = match.group(1)

        if _PUTCALL.search(record):
            continue  # an option on the name, not the name

        amount_type = _AMT_TYPE.search(record)
        if amount_type and amount_type.group(1).upper() != "SH":
            continue  # PRN is a principal amount, i.e. debt

        cusip = _CUSIP.search(record)
        value = _VALUE.search(record)
        if not (cusip and value):
            continue

        totals[cusip.group(1)[:_KEY_LEN].upper()] += float(value.group(1))

    return dict(totals)


def build_holdings(books, universe):
    """Stack per-fund position dicts into the matrix the engine wants.

    `universe` maps CUSIP prefix -> ticker, MANY-TO-ONE: an issuer with several
    share classes gets one CUSIP entry per class, all pointing at the same
    ticker, and they sum into a single column.

    That isn't a nicety. Alphabet files under four CUSIPs, and mapping only
    Class C captured 48% of Citadel's Alphabet but 15% of Millennium's. The
    undercount differs per manager, so it doesn't cancel — and because each
    fund is normalised within the universe, a short column silently reweights
    that fund's other nine, inventing dispersion in the overlap metric.

    Funds with nothing in the universe are dropped rather than carried as a
    row of zeros, which would break the leverage arithmetic. The retained fund
    names come back so callers can filter their per-fund parameter vectors to
    match — otherwise dropping fund 2 of 5 silently attaches every leverage
    from index 2 onward to the wrong fund.
    """
    tickers = list(dict.fromkeys(universe.values()))
    column = {ticker: i for i, ticker in enumerate(tickers)}

    funds, rows = [], []
    for name, positions in books.items():
        row = [0.0] * len(tickers)
        for cusip, value in positions.items():
            ticker = universe.get(cusip)
            if ticker is not None:
                row[column[ticker]] += value
        if sum(row) <= 0:
            continue
        funds.append(name)
        rows.append(row)

    return funds, tickers, np.array(rows, dtype=float)


# --------------------------------------------------------------------------
# network
# --------------------------------------------------------------------------

# SEC blocks anything without a real contact in the UA. Ten requests a second
# is their published ceiling; we're nowhere near it.
USER_AGENT = "Firebreak HackRice16 research contact@example.edu"


def _fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    )
    raw = urllib.request.urlopen(request, timeout=60).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def choose_filings(records):
    """Which filings actually make up the latest quarter's book.

    SEC Form 13F FAQ 58. A RESTATEMENT replaces the original outright; a
    NEW HOLDINGS amendment is a supplement carrying only the added rows and
    has to be unioned with the original. Apply the wrong one and you get
    either a 5%-sized portfolio or a double count, silently either way.

    Records need: accession, period, amendment_type (None if not an
    amendment), filing_date.
    """
    if not records:
        return []

    latest_period = max(r["period"] for r in records)
    current = [r for r in records if r["period"] == latest_period]

    restatements = [
        r for r in current if (r["amendment_type"] or "").upper() == "RESTATEMENT"
    ]
    if restatements:
        return [max(restatements, key=lambda r: (r["filing_date"], r["accession"]))]

    # originals plus any additive amendments
    return [
        r
        for r in current
        if r["amendment_type"] is None
        or (r["amendment_type"] or "").upper() == "NEW HOLDINGS"
    ]


_PERIOD = re.compile(r"<(?:\w+:)?periodOfReport>\s*([^<\s]+)", re.I)
_AMEND_TYPE = re.compile(r"<(?:\w+:)?amendmentType>\s*([^<]+)", re.I)


def _cover_page(cik, accession):
    """periodOfReport and amendmentType off a filing's primary_doc.xml."""
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/primary_doc.xml"
    raw = _fetch(url)
    period = _PERIOD.search(raw)
    kind = _AMEND_TYPE.search(raw)
    return (
        period.group(1) if period else "",
        kind.group(1).strip() if kind else None,
    )


def latest_filings(cik, look_back=8):
    """(manager name, period, [filings]) making up the most recent quarter.

    Scans the most recent 13F-HR *and* 13F-HR/A entries — the old version
    tested `form == "13F-HR"`, which never matches an amendment, so it read
    superseded data whenever a manager restated.
    """
    listing = json.loads(_fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    recent = listing["filings"]["recent"]
    name = listing.get("name")

    candidates = []
    for i, form in enumerate(recent["form"]):
        if form not in ("13F-HR", "13F-HR/A"):
            continue
        accession = recent["accessionNumber"][i].replace("-", "")
        period, kind = _cover_page(cik, accession)
        candidates.append(
            {
                "accession": accession,
                "period": _sortable(period),
                "raw_period": period,
                "amendment_type": kind,
                "filing_date": recent["filingDate"][i],
            }
        )
        if len(candidates) >= look_back:
            break

    chosen = choose_filings(candidates)
    period = chosen[0]["raw_period"] if chosen else ""
    return name, period, chosen


def _sortable(period):
    """EDGAR writes MM-DD-YYYY on the cover page; sort as YYYY-MM-DD."""
    parts = period.split("-")
    return f"{parts[2]}-{parts[0]}-{parts[1]}" if len(parts) == 3 else period


def fetch_positions(cik, accession):
    """Pull and parse one filing's information table."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"
    index = json.loads(_fetch(f"{base}/index.json"))
    name = next(
        (
            item["name"]
            for item in index["directory"]["item"]
            if item["name"].lower().endswith(".xml")
            and "primary_doc" not in item["name"].lower()
        ),
        None,
    )
    if name is None:
        return {}
    return parse_info_table(_fetch(f"{base}/{name}"))
