"""The cache has to key on every knob that changes the answer.

`KNOBS` listed leverage, gamma and breaches. The breach band was added later
and never added here — so in demo mode every band value got the same
recording, served under `cached_exact: true`.

That's the worst version of this bug: the band is the single most influential
parameter in the model (1.05 gives −5.27%, 1.30 gives −27.33%), demo mode is
the offline-insurance path the recordings exist for, and the payload asserted
the answer was an exact match for settings it had never been computed at.
"""

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
