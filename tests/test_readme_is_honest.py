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

import pytest

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
    claimed = re.findall(r"#\s*(\d+)(?:\s+collected|\s+passing|,\s*no network)", text)
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

    from minima import api

    cached_routes = ["/api/break?leverage=5"]
    live_routes = ["/api/portfolio/demo", "/api/portfolio/full?limit=0.10",
                   "/api/cascade?asset=NVDA&magnitude=0.2"]

    with mock.patch.dict(os.environ, {"MINIMA_DEMO": "1"}):
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
    # The nearest-recording behaviour was deleted for answering a question at
    # leverage 2.5 with a recording made at 1.5. The README must not still
    # advertise it.
    assert "serves the nearest recording" not in text, (
        "the README still describes nearest-match serving, which was removed: "
        "it produced a 25.8x error on /api/stabilise's sell instruction"
    )
    # Substance rather than markup: the paragraph that names the portfolio
    # routes has to be the one that says they are not cached. Matching on bold
    # asterisks made this fail on an edit that only improved the wording.
    paragraphs = [p for p in text.split("\n\n") if "/api/portfolio/" in p]
    assert any("cached: false" in p or "not in that machinery" in p.replace("\n", " ")
               for p in paragraphs), (
        "no paragraph mentioning the portfolio routes says they are not cached"
    )


def test_the_docs_quote_the_resolution_the_api_actually_reports():
    """`resolution_pct` is TWICE the search tolerance, on purpose.

    `bought` is the difference of two independently bisected searches, so each
    carries its own error and the bar the difference must clear is 2x. The
    pitch, the video script and the design spec all quoted the single-search
    figure of 0.005pp against that two-search quantity. The conclusion survived
    — 0.0039pp is inside 0.01pp just as it was inside 0.005pp — but a judge
    checking the arithmetic finds the stated bar is half the real one.
    """
    import pathlib

    from minima import api

    out = api.handle("/api/stabilise?leverage=5&gamma=0.2&band=1.05&breaches=3", {})
    reported = out["bought"]["resolution_pct"]

    root = pathlib.Path(__file__).resolve().parents[1]
    devpost = (root / "docs" / "devpost.md").read_text()
    assert f"resolution of {reported}pp" in devpost, (
        f"devpost quotes a resolution other than the {reported}pp the API reports"
    )

    # and the half-figure must not reappear anywhere it is describing `bought`
    half = f"{reported / 2:g}pp"
    for name in ["docs/devpost.md", "docs/video-script.md"]:
        text = (root / name).read_text()
        assert f"resolves to ±{half}" not in text, (
            f"{name} still quotes the single-search {half} for a quantity that is "
            "the difference of two searches"
        )


def test_the_pitch_quotes_the_fix_size_the_engine_returns():
    """devpost said $1.7M in one paragraph and $3.7M four paragraphs later.

    The second figure was also the spoken line of a video shot the script says
    not to cut.
    """
    import pathlib

    from minima import api

    out = api.handle("/api/stabilise?leverage=5&gamma=0.2&band=1.05&breaches=3", {})
    sell = out["fix"]["sell_usd"]
    millions = f"${sell / 1e6:.2f}M"

    devpost = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "devpost.md").read_text()
    assert millions in devpost, f"devpost does not quote {millions}; the fix is ${sell:,.2f}"
    assert "$3.7M" not in devpost, "the contradictory figure is back"


def test_every_mutation_anchor_still_exists_in_the_code_it_targets():
    """A drifted anchor means that mutation measured nothing.

    scripts/mutate.py only proves a test can fail if the edit it makes is
    actually applied. An anchor that no longer matches applies nothing, and the
    suite comes back green for a mutant identical to the original — the exact
    bug the harness exists to find, in the harness.

    It used to raise on drift, which is loud but total: one stale anchor
    aborted the run and took the other seventy mutations' results with it. Two
    drifted in a single evening's refactoring of one file, and neither was
    noticed until a traceback replaced the summary. This catches them in the
    normal suite, which runs in twelve seconds, instead of at the end of a
    twenty-minute mutation run.
    """
    import importlib.util
    import os
    import pathlib

    if os.environ.get("MINIMA_MUTANT"):
        pytest.skip(
            "running inside a mutant: the mutation has by definition changed "
            "the line its own anchor points at, so this test would fail for "
            "every mutation and hand each one a catch it did not earn"
        )

    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("_mutate", root / "scripts" / "mutate.py")
    mutate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mutate)

    assert len(mutate.MUTATIONS) > 50, "the mutation set has shrunk unexpectedly"

    drifted = []
    for name, (path, anchor, _replacement) in mutate.MUTATIONS.items():
        if anchor not in (root / path).read_text():
            drifted.append(f"{name} ({path})")
    assert not drifted, (
        "these mutations no longer match the code they target, so they measure "
        "nothing: " + ", ".join(drifted)
    )


def test_every_ui_mutation_is_a_mutation():
    """UI_MUTATIONS routes a name to the page harness instead of pytest.

    A name in that set with no entry in MUTATIONS is never run at all, and a
    frontend mutation left OUT of the set is run under pytest — which does not
    load a page, so it reports CAUGHT or GREEN on evidence that has nothing to
    do with the change.
    """
    import importlib.util
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("_mutate", root / "scripts" / "mutate.py")
    mutate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mutate)

    orphans = sorted(mutate.UI_MUTATIONS - set(mutate.MUTATIONS))
    assert not orphans, f"named in UI_MUTATIONS but not defined: {orphans}"

    misrouted = sorted(
        name for name, (path, _, _) in mutate.MUTATIONS.items()
        if path.startswith("web/") and name not in mutate.UI_MUTATIONS
    )
    assert not misrouted, (
        "these mutate a file in web/ but are run under pytest, which never "
        f"loads a page: {misrouted}"
    )


def test_the_pitch_does_not_promise_a_control_the_app_disables():
    """devpost's first sentence said "You connect or upload a portfolio".

    index.html's Connect brokerage button is `disabled` and carries the text
    "Brokerage credentials are not included in this build, so that button is
    disabled rather than pretending" — so the pitch was claiming a capability
    the product explicitly disclaims on its own first screen. The app was more
    honest than the document selling it.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    index = (root / "web" / "index.html").read_text()
    devpost = (root / "docs" / "devpost.md").read_text()

    if "connectBtn" in index or "Connect brokerage" in index:
        assert "disabled" in index, "the brokerage button is no longer disabled"
        assert "You connect or upload a portfolio" not in devpost, (
            "the pitch promises a brokerage connection the app disables"
        )


def test_the_docs_do_not_describe_a_mode_toggle_that_does_not_exist():
    """"Risk Desk Mode … one button away" survived the six-page rewrite.

    The engine-level claim is true — the institutional question is the same
    search with a different failure condition — but there is no switch. A
    reader opens the app and looks for one.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    web = "\n".join(p.read_text() for p in (root / "web").glob("*.html"))
    has_toggle = "risk desk" in web.lower()

    for name in ["README.md", "docs/devpost.md"]:
        text = (root / name).read_text()
        if not has_toggle:
            assert "one button away" not in text, (
                f"{name} says the institutional mode is one button away; there is "
                "no such button in web/"
            )
