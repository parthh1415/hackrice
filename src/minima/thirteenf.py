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
    row of zeros, which would break the leverage arithmetic. Dropping a row
    is why the fourth return value exists: `kept` is the index each surviving
    row had in `books`, so a caller holding a per-manager leverage vector can
    subset it the same way. Names alone aren't enough — a caller that builds
    its vector from the original manager list has nothing to match names
    against, and dropping fund 2 of 5 then slides every leverage from index 2
    onward onto the wrong fund, silently.
    """
    tickers = list(dict.fromkeys(universe.values()))
    column = {ticker: i for i, ticker in enumerate(tickers)}

    funds, rows, kept = [], [], []
    for index, (name, positions) in enumerate(books.items()):
        row = [0.0] * len(tickers)
        for cusip, value in positions.items():
            ticker = universe.get(cusip)
            if ticker is not None:
                row[column[ticker]] += value
        if sum(row) <= 0:
            continue
        funds.append(name)
        rows.append(row)
        kept.append(index)

    return funds, tickers, np.array(rows, dtype=float), kept


# --------------------------------------------------------------------------
# network
# --------------------------------------------------------------------------

# SEC blocks anything without a real contact in the UA. Ten requests a second
# is their published ceiling; we're nowhere near it.
USER_AGENT = "Minima HackRice16 research contact@example.edu"


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

    Records need: accession, period, filing_date, `is_amendment` (from the
    form string, which is authoritative), and amendment_type (None if the
    cover page did not say).
    """
    if not records:
        return []

    latest_period = max(r["period"] for r in records)
    current = [r for r in records if r["period"] == latest_period]

    # An amendment we cannot classify is not an original. This used to decide
    # by amendment_type alone, so a 13F-HR/A whose cover page omits
    # <amendmentType> read as `None`, which meant "original", and got SUMMED
    # with the filing it was amending. Deleting that one element from
    # Citadel's real restatement doubles its book — $14.6B to $29.2B, gross
    # $40.9B to $55.5B — and moves the demo from 4 funds breaching to all
    # five, amplification 1.87 to 2.37. No error, no warning, and the filing
    # still says <isAmendment>true</isAmendment> two lines above the element
    # we deleted. The form string says "/A" too; we were throwing it away.
    #
    # So: the form decides whether something is an amendment, and an
    # amendment whose type we do not recognise raises. Guessing is what put a
    # doubled book on screen with a straight face.
    for r in current:
        if not r.get("is_amendment"):
            continue
        kind = (r["amendment_type"] or "").strip().upper()
        if kind not in _AMENDMENT_KINDS:
            raise ValueError(
                f"{r['accession']}: 13F-HR/A with amendment type "
                f"{r['amendment_type']!r}, which is not one of "
                f"{sorted(_AMENDMENT_KINDS)}. Refusing to guess whether it "
                "replaces the original or supplements it — those differ by a "
                "factor of two in the resulting book."
            )

    def kind_of(r):
        return (r["amendment_type"] or "").strip().upper() if r.get("is_amendment") else ""

    restatements = [r for r in current if kind_of(r) == "RESTATEMENT"]
    if restatements:
        newest = max(restatements, key=lambda r: (r["filing_date"], r["accession"]))
        # A supplement filed AFTER the restatement supplements the RESTATED
        # report, so it still counts. The old code returned here and dropped
        # it. Not present in the real data — logic-level fix only.
        later_supplements = [
            r for r in current
            if kind_of(r) == "NEW HOLDINGS"
            and (r["filing_date"], r["accession"]) > (newest["filing_date"], newest["accession"])
        ]
        return [newest] + later_supplements

    # originals plus any additive amendments
    chosen = [r for r in current
              if not r.get("is_amendment") or kind_of(r) == "NEW HOLDINGS"]
    # A supplement carries the rows that were ADDED, not the book. On its own
    # it becomes the fund's entire position set — a portfolio a fraction of its
    # real size, reported without complaint. Reachable whenever the original
    # falls outside the look-back window, which counts candidate filings rather
    # than distinct periods, so a heavily-amended quarter pushes it out.
    #
    # This is the same silent factor-of-N the type check above refuses to guess
    # at, and unlike the question of how to merge a repeated CUSIP it does not
    # turn on any reading of FAQ 58: a supplement without the thing it
    # supplements is not a portfolio.
    if chosen and all(kind_of(r) == "NEW HOLDINGS" for r in chosen):
        raise ValueError(
            f"period {latest_period}: the only filings available are NEW HOLDINGS "
            f"supplements ({', '.join(r['accession'] for r in chosen)}) with no "
            "original or restatement to supplement. A supplement carries the "
            "added rows, not the book, so using it alone would report a fraction "
            "of this manager's positions as all of them. Widen the look-back."
        )
    return chosen


# The types SEC Form 13F FAQ 58 defines. Anything else is a filing we do not
# know how to apply, and applying it wrongly is a silent factor-of-two.
_AMENDMENT_KINDS = frozenset({"RESTATEMENT", "NEW HOLDINGS"})

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
                # The form string is the authoritative answer to "is this an
                # amendment". The cover page's <amendmentType> is a detail
                # ABOUT an amendment and can be missing; the "/A" cannot.
                "is_amendment": form.endswith("/A"),
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
