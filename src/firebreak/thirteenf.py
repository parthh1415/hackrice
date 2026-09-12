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

    `universe` maps CUSIP prefix -> ticker and fixes the column order.
    Funds with nothing in the universe are dropped rather than carried as a
    row of zeros, which would break the leverage arithmetic.
    """
    cusips = list(universe)
    tickers = [universe[c] for c in cusips]

    funds, rows = [], []
    for name, positions in books.items():
        row = [positions.get(cusip, 0.0) for cusip in cusips]
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


def latest_filing(cik):
    """(manager name, accession without dashes, filing date) for the newest 13F-HR."""
    listing = json.loads(_fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    recent = listing["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "13F-HR":
            return (
                listing.get("name"),
                recent["accessionNumber"][i].replace("-", ""),
                recent["filingDate"][i],
            )
    return listing.get("name"), None, None


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
