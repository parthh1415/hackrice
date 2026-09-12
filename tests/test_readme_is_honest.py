"""The README's test count has been wrong three times in one night.

It said 140 when there were 146, then 146 when there were 149 — and it is
the one number in that file a judge can check in four seconds, by running
the command printed directly above it. Editing it by hand has now failed
often enough to stop doing that and let the suite own it instead.
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def collected_count():
    """Ask pytest how many tests it can see, without running them."""
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"],
        cwd=ROOT, capture_output=True, text=True, timeout=120).stdout
    m = re.search(r"(\d+) tests? collected", out)
    assert m, f"could not read a collection count from pytest:\n{out[-500:]}"
    return int(m.group(1))


def test_the_readme_states_the_real_test_count():
    text = README.read_text()
    claimed = re.findall(r"#\s*(\d+)(?:\s+passing|,\s*no network)", text)
    assert claimed, "README no longer states a test count next to its pytest command"

    actual = collected_count()
    wrong = sorted({int(c) for c in claimed if int(c) != actual})
    assert not wrong, (
        f"README claims {wrong} test(s) where pytest collects {actual}. "
        "Update both comments next to the `pytest` commands in README.md."
    )


def test_the_readme_counts_the_golden_recordings_it_promises():
    text = README.read_text()
    m = re.search(r"(\d+) recorded answers in `data/cache/golden/`", text)
    assert m, "README no longer states how many golden recordings ship"
    actual = len(list((ROOT / "data" / "cache" / "golden").glob("*.json")))
    assert int(m.group(1)) == actual, (
        f"README promises {m.group(1)} recordings, {actual} are committed"
    )


def test_the_readme_is_right_about_which_routes_are_cached():
    """It used to say "every /api/ response" comes off disk under the flag.

    Four of them do not, and they are the ones the product loop is built from
    — the path anybody following the README actually walks. The sentence read
    as a promise about the whole app and was true of a third of it.
    """
    import os
    from unittest import mock

    from firebreak import api

    cached_routes = ["/api/break?leverage=5"]
    live_routes = ["/api/portfolio/demo", "/api/portfolio/full?limit=0.10",
                   "/api/cascade?asset=NVDA&magnitude=0.2"]

    with mock.patch.dict(os.environ, {"FIREBREAK_DEMO": "1"}):
        for route in cached_routes:
            assert api.handle(route, {}).get("cached") is True, route
        for route in live_routes:
            assert api.handle(route, {}).get("cached") is False, (
                f"{route} is cached now. The README says the portfolio routes "
                "compute live every time; update it or this."
            )

    text = README.read_text()
    assert "Every `/api/` response then comes off disk" not in text, (
        "that sentence is false for /api/portfolio/* and /api/cascade"
    )
    assert "not\nin that machinery" in text or "**not**" in text, (
        "the README has to say somewhere that the portfolio routes are not cached"
    )
