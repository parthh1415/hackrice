"""Rebuild the committed dataset from recorded EDGAR bytes, with no network.

(Provenance note: these fixtures, this test and scripts/record_edgar_mirror.py
were written by a review agent and landed in commit ac6fda0, whose message is
about the devpost and does not mention them — a `git add -A` of mine swept an
agent's in-progress work into an unrelated commit. See commit ce0d0e1 for the
record. Nothing here is my work but the apology.)

`scripts/refresh_dataset.py` was the one thing in this repo that every printed
number depends on and that nothing could exercise. The goldens do not cover it:
they pin the engine's OUTPUT, so a corrupted CUSIP map that gets refreshed and
re-recorded takes the recordings with it, and the suite goes quiet. Measured —
reverting the Alphabet map to Class A only and refreshing turns 33 golden tests
red, and re-recording them, which `refresh_dataset.py` tells you to do, drops
that to 2 incidental failures about search resolution.

So this pins the INPUT instead. The artefact is re-derived from the filing
bytes SEC actually served, which means a wrong CUSIP map, a wrong unit
conversion or a wrong amendment rule disagrees with data/cache/dataset.json
here, with the committed cache left exactly where it is and no refresh needed.

Two things the next person should know before trusting it.

First, the maintenance burden is symmetrical to the goldens. When the quarter
moves, `scripts/record_edgar_mirror.py` has to run alongside
`scripts/refresh_dataset.py`, and a lazy re-record — regenerating both halves
and committing whatever comes out — hides exactly the class of error this test
exists to catch, in exactly the way re-recording the goldens does. The
protection is in reading the diff, not in the test being present.

Second, the recording deliberately covers both scan paths: the cover pages a
`13F-HR`-only filter would read as well as the ones `13F-HR` + `13F-HR/A`
reads. That is on purpose. If it covered only the current path, reverting the
form filter would fail on a missing fixture rather than on the holdings being
wrong, and a test that fails for the wrong reason teaches the next person to
distrust it. A test that PASSES because a fixture is missing is worse still,
which is why an un-mirrored URL raises below rather than skipping.
"""

import gzip
import json
import pathlib
import urllib.parse

import pytest

from firebreak import dataset, thirteenf

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIRROR = pathlib.Path(__file__).resolve().parent / "fixtures_edgar"


def _replay(url):
    parts = urllib.parse.urlsplit(url)
    path = MIRROR / parts.netloc / parts.path.lstrip("/")
    path = path.with_name(path.name + ".gz")
    if not path.exists():
        raise AssertionError(
            f"{url} is not in the recording, so this replay proves less than "
            "it claims to. Re-record with scripts/record_edgar_mirror.py."
        )
    return gzip.decompress(path.read_bytes()).decode("utf-8", "replace")


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """Replay the recording, and write the rebuilt artefact somewhere harmless.

    Pointing CACHE at tmp_path matters: load_dataset(refresh=True) writes what
    it builds, and a test that overwrites data/cache/dataset.json would make
    itself pass by moving the thing it is checking against.
    """
    monkeypatch.setattr(thirteenf, "_fetch", _replay)
    monkeypatch.setattr(dataset, "CACHE", tmp_path / "dataset.json")
    return tmp_path


def test_the_committed_dataset_is_what_these_filings_actually_say(offline):
    committed = json.loads((ROOT / "data" / "cache" / "dataset.json").read_text())

    rebuilt = dataset.load_dataset(refresh=True)

    assert rebuilt == committed


def test_the_replay_never_touches_the_network(offline, monkeypatch):
    # Otherwise a gap in the recording could be papered over by a live fetch on
    # the machine that recorded it, and the suite would need EDGAR everywhere
    # else. This is the assertion that makes "no network required" true.
    def explode(*args, **kwargs):
        raise AssertionError("the offline replay opened a socket")

    monkeypatch.setattr("urllib.request.urlopen", explode)

    dataset.load_dataset(refresh=True)


def test_citadels_restatement_is_the_filing_that_gets_read(offline):
    # 13F-HR/A 0001104659-26-104387 restated Q2 2026 and supersedes
    # 0001104659-26-097200. Reading the original is the bug that shipped, and
    # the whole-book difference is only $84.5M — none of it inside the ten
    # names — so nothing downstream would have told us.
    _, period, filings = thirteenf.latest_filings(1423053)

    assert period == "06-30-2026"
    assert [f["accession"] for f in filings] == ["000110465926104387"]
