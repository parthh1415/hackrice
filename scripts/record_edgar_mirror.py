#!/usr/bin/env python3
"""Record the EDGAR responses the ingest path reads, for offline replay.

    PYTHONPATH=src python3 scripts/record_edgar_mirror.py

Writes tests/fixtures_edgar/<host>/<path>.gz — one file per URL, gzipped,
named by the URL rather than by a hash so a re-record is reviewable in a
diff. About 26 MB of XML becomes about 1.5 MB on disk.

Run this when the quarter moves, in the same breath as
scripts/refresh_dataset.py — the recording and data/cache/dataset.json are a
matched pair and tests/test_ingest_replays_offline.py asserts they agree.

It deliberately records more than one run needs. Besides everything
load_dataset() touches, it walks the cover pages a `13F-HR`-only scan would
reach, so that reverting the form filter makes the replay test disagree about
the HOLDINGS rather than error on a missing fixture. A test that passes, or
fails for the wrong reason, because a fixture is absent is worse than no test.
"""

import gzip
import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, "src")

from minima import thirteenf
from minima.dataset import UNIVERSE, manager_ciks

MIRROR = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures_edgar"

_live = thirteenf._fetch
_written = {}


def _recording(url):
    parts = urllib.parse.urlsplit(url)
    path = MIRROR / parts.netloc / parts.path.lstrip("/")
    path = path.with_name(path.name + ".gz")
    if url not in _written:
        text = _live(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = gzip.compress(text.encode("utf-8"), 9)
        path.write_bytes(body)
        _written[url] = len(body)
        print(f"  {len(body) / 1e6:6.2f} MB  {url}", flush=True)
    return gzip.decompress(path.read_bytes()).decode("utf-8", "replace")


def main():
    thirteenf._fetch = _recording
    config = json.loads(UNIVERSE.read_text())

    for name, ciks in manager_ciks(config).items():
        for cik in ciks:
            print(f"== {name} (CIK {cik})", flush=True)
            _, period, filings = thirteenf.latest_filings(cik)
            for filing in filings:
                thirteenf.fetch_positions(cik, filing["accession"])

            recent = json.loads(
                _recording(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
            )["filings"]["recent"]

            # Every filing for the chosen quarter, not just the ones we picked
            # — including the originals a restatement supersedes. Recording
            # only the chosen ones is the bug this script had first: reverting
            # the form filter then read Citadel's original information table,
            # which was not in the recording, so the replay test died on a
            # missing fixture instead of disagreeing about the holdings. See
            # the module docstring; the whole point is to fail for the right
            # reason.
            #
            # The `13F-HR`-only cover pages come along for the same reason:
            # that scan walks eight filings back and reaches quarters the
            # amendment-aware scan never asks for.
            latest = thirteenf._sortable(period)
            seen = 0
            for i, form in enumerate(recent["form"]):
                if form not in ("13F-HR", "13F-HR/A"):
                    continue
                accession = recent["accessionNumber"][i].replace("-", "")
                if recent["reportDate"][i] == latest:
                    thirteenf.fetch_positions(cik, accession)
                if form == "13F-HR" and seen < 8:
                    thirteenf._cover_page(cik, accession)
                    seen += 1

    total = sum(_written.values())
    print(f"\n{MIRROR} — {len(_written)} files, {total / 1e6:.2f} MB gzipped")


if __name__ == "__main__":
    main()
