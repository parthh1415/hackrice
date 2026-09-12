"""Every recording must still be what the engine produces.

A recording is a claim about the engine's behaviour, and it stops being
true the moment the engine changes. Demo mode is the mode the demo
actually runs in, so a stale recording is not a stale fixture — it is a
wrong answer on stage, served confidently, with `cached: true` next to it.

This has bitten twice. The stabiliser's answer changed and ten recordings
went on serving the old fix. `/api/boundary` dropped two top-level keys
and ten more recordings kept sending them.

A review agent had a differ that would have caught both, but it lived in
a scratch directory and only ran when someone remembered to ask. Worse,
it had been carrying a `solve_ms` exclusion — which is precisely what hid
the drift, because every re-record rewrote every file for a changed
stopwatch reading and nothing else could be seen past it.
"""

import json

import pytest

from firebreak import api

# What a recording is allowed to differ by, and nothing else.
#
# The `cached*` envelope is written by record_golden and has no live
# counterpart. `engine.solve_ms` is the one field where the two are SUPPOSED
# to disagree: the recording stores null because it has no honest duration to
# report, and a live call measures one. That makes it the field a differ must
# special-case rather than strip — stripping it is the mistake that hid the
# drift for as long as it did.
ENVELOPE = {"cached", "cached_for", "cached_exact", "cached_near"}
EXPECTED_TO_DIFFER = {("engine", "solve_ms")}


def differences(golden, live, path=()):
    if path in EXPECTED_TO_DIFFER:
        return
    if isinstance(golden, dict) and isinstance(live, dict):
        keys = set(golden) | set(live)
        if len(path) == 0:
            keys -= ENVELOPE
        for k in sorted(keys):
            if k not in golden:
                yield f"/{'/'.join(path + (k,))}: missing from recording (live has it)"
            elif k not in live:
                yield f"/{'/'.join(path + (k,))}: recording has it, endpoint no longer sends it"
            else:
                yield from differences(golden[k], live[k], path + (k,))
    elif isinstance(golden, list) and isinstance(live, list):
        if len(golden) != len(live):
            yield f"/{'/'.join(path)}: length {len(golden)} recorded vs {len(live)} live"
        else:
            for i, (g, l) in enumerate(zip(golden, live)):
                yield from differences(g, l, path + (str(i),))
    elif golden != live:
        yield f"/{'/'.join(path)}: recorded {golden!r} vs live {live!r}"


@pytest.mark.parametrize("route,knobs", api.golden_specs(),
                         ids=lambda v: api.slug(v[0], {k: str(x) for k, x in v[1].items()})
                         if isinstance(v, tuple) else str(v))
def test_each_recording_still_matches_a_live_run(route, knobs):
    params = {name: str(value) for name, value in knobs.items()}
    path = api.GOLDEN / (api.slug(route, params) + ".json")
    assert path.exists(), f"{path.name} is not recorded — run scripts/record_golden.py"

    found = list(differences(json.loads(path.read_text()), api.ROUTES[route](params)))
    assert not found, (
        f"{path.name} no longer matches the engine:\n  " + "\n  ".join(found[:12])
        + ("\n  ... and more" if len(found) > 12 else "")
        + "\nRe-record with: PYTHONPATH=src python3 scripts/record_golden.py"
    )


def test_the_recordings_declare_no_stopwatch_of_their_own():
    """The null in solve_ms is load-bearing, so pin it."""
    for path in sorted(api.GOLDEN.glob("stabilise__*.json")):
        engine = json.loads(path.read_text()).get("engine", {})
        assert "solve_ms" in engine, f"{path.name} dropped solve_ms; a recording must keep live's key shape"
        assert engine["solve_ms"] is None, (
            f"{path.name} recorded solve_ms={engine['solve_ms']!r} — a duration measured on "
            "whatever machine last ran the recorder, replayed as this request's"
        )
