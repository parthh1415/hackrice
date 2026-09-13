"""The cache has to key on every knob that changes the answer.

`KNOBS` listed leverage, gamma and breaches. The breach band was added later
and never added here — so in demo mode every band value got the same
recording, served under `cached_exact: true`.

That's the worst version of this bug: the band is the single most influential
parameter in the model (1.05 gives −5.27%, 1.30 gives −27.33%), demo mode is
the offline-insurance path the recordings exist for, and the payload asserted
the answer was an exact match for settings it had never been computed at.
"""

import pytest

from firebreak import api


def test_the_cache_key_covers_every_knob_that_moves_the_answer():
    for route in ("/api/break", "/api/stabilise", "/api/boundary"):
        assert "band" in api.KNOBS[route], f"{route} cache key ignores band"


def test_demo_mode_does_not_serve_one_band_for_another():
    low = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&band=1.05&demo=1", {})
    high = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&band=1.30&demo=1", {})

    # either it has a recording at that band, or it says the one it served
    # was for different settings — what it must never do is both differ and
    # claim exactness
    for served, asked in ((low, 1.05), (high, 1.30)):
        if served.get("cached") and served.get("cached_exact"):
            assert served["cached_for"]["band"] == asked, (
                f"claimed exact for band {asked} while serving "
                f"{served['cached_for']['band']}"
            )

    assert low["pct"] != high["pct"], "band must move the answer in demo mode too"


def test_the_golden_path_records_more_than_one_band():
    bands = {spec.get("band", 1.05) for _, spec in api.golden_specs() if "band" in spec}

    assert len(bands) >= 2, f"only recorded bands {bands}"


@pytest.mark.parametrize("route,query,knob,given,used", [
    ("/api/boundary", "leverage=12", "leverage", 12.0, 8.0),
    ("/api/boundary", "gamma=5", "gamma", 5.0, 1.0),
    ("/api/boundary", "band=3", "band", 3.0, 1.5),
    ("/api/break", "leverage=99&breaches=3", "leverage", 99.0, 8.0),
    ("/api/stabilise", "gamma=-4&breaches=3", "gamma", -4.0, 0.0),
])
def test_a_served_recording_still_reports_this_requests_clamp(route, query, knob, given, used):
    """A recording's `clamped` describes the request that MADE it.

    That request was in range by construction, so its record is empty. This
    request may not have been: ask for leverage=12, the guard pulls it to 8.0,
    and if a recording exists AT 8.0 it is served — carrying `clamped: []`, so
    the payload states that nothing was adjusted about a request where
    something was.

    Reported by a reviewer, dismissed by me after testing `api.handle` directly
    — which computes live and reports correctly. It only appears under demo
    mode, over HTTP, which is the path a judge dragging a slider takes.
    """
    for suffix in ("", "&demo=1"):
        out = api.handle(f"{route}?{query}{suffix}", {})
        entry = [c for c in out["params"].get("clamped", []) if c["name"] == knob]
        assert entry, (
            f"{route}?{query}{suffix} used {out['params'][knob]} for a requested "
            f"{given} and reported {out['params'].get('clamped')} "
            f"(cached={out.get('cached')})"
        )
        assert entry[0]["given"] == pytest.approx(given)
        assert entry[0]["used"] == pytest.approx(used)
        assert out["params"][knob] == pytest.approx(used)


def test_an_in_range_request_reports_no_clamp_either_way():
    """The guard must not start inventing clamps that did not happen."""
    for suffix in ("", "&demo=1"):
        out = api.handle(f"/api/boundary?leverage=5&gamma=0.2&band=1.05{suffix}", {})
        assert out["params"]["clamped"] == []
