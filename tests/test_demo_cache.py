"""The offline path. If the wifi dies at 2pm the demo still has to run.

These tests record the golden path once per module and then hammer the two
ways we serve it: ?demo=1 on purpose, and a dead engine by accident.

The recording goes to a scratch directory, not to data/cache/golden. Writing
to the real one meant every `pytest` run rewrote the committed recordings —
`solve_ms` is a wall clock, so the file came back with a one-millisecond diff
and the working tree was dirty for no reason anyone could see. The committed
set is the demo's insurance; tests read it, they don't overwrite it.
"""

import os

import pytest

from firebreak import api

# grabbed at import time, before the fixture below points api.GOLDEN elsewhere
SHIPPED_GOLDEN = api.GOLDEN


@pytest.fixture(scope="module", autouse=True)
def golden(tmp_path_factory):
    """Record the golden path once, so the tests below have something to serve."""
    shipped = api.GOLDEN
    api.GOLDEN = tmp_path_factory.mktemp("golden")
    try:
        api.record_golden()
        yield
    finally:
        api.GOLDEN = shipped
        os.environ.pop("FIREBREAK_DEMO", None)


def test_the_committed_recordings_still_load_and_cover_the_demo_spots():
    """The insurance itself, not the copy this run just made.

    Everything else here records first and then serves what it recorded, which
    passes just as happily against an empty repo. This is the one that notices
    if data/cache/golden ever stops being shipped.
    """
    scratch, api.GOLDEN = api.GOLDEN, SHIPPED_GOLDEN
    try:
        for route in ["/api/health", "/api/dataset", "/api/break",
                      "/api/stabilise", "/api/boundary"]:
            for spot in api.GOLDEN_SPOTS:
                params = {k: str(v) for k, v in spot.items()}
                cached = api.load_golden(route, params)
                assert cached is not None, f"nothing recorded for {route}"
                assert cached["cached"] is True
                assert cached["cached_near"], f"{route} at {spot} is not covered"
    finally:
        api.GOLDEN = scratch


def key_shape(value):
    """Strip a payload down to the keys the frontend reaches for.

    Lists collapse to their first element: a 16-long trajectory and a 3-long
    one are the same shape as far as app.js is concerned, but a trajectory
    entry missing `prices` is not.
    """
    if isinstance(value, dict):
        return {k: key_shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [key_shape(value[0])] if value else []
    return None


# --- demo mode serves the recording ---------------------------------------


@pytest.mark.parametrize("route", ["/api/health", "/api/dataset", "/api/break",
                                   "/api/stabilise", "/api/boundary"])
def test_demo_mode_serves_every_endpoint_from_cache(route):
    result = api.handle(route + "?demo=1", {})

    assert result["cached"] is True
    assert "error" not in result


def test_demo_flag_survives_alongside_the_real_sliders():
    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&demo=1", {})

    assert result["cached"] is True
    assert result["found"] is True
    assert result["asset"] in result["tickers"]
    assert result["trajectory"], "the UI animates this, it can't be empty"


def test_env_var_puts_the_whole_server_in_demo_mode():
    os.environ["FIREBREAK_DEMO"] = "1"
    try:
        result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})
    finally:
        os.environ.pop("FIREBREAK_DEMO", None)

    assert result["cached"] is True


# --- the flag has to be honest --------------------------------------------


def test_live_responses_say_they_are_live():
    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})

    assert result["cached"] is False


def test_health_carries_the_flag_too():
    assert api.handle("/api/health", {})["cached"] is False
    assert api.handle("/api/health?demo=1", {})["cached"] is True


# --- shape parity ---------------------------------------------------------


def test_cached_break_has_the_same_key_shape_as_a_live_one():
    # this is the one that breaks silently: a missing key doesn't throw, it
    # just renders an empty panel and nobody notices until the judges do.
    live = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})
    cached = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&demo=1", {})

    assert key_shape(cached) == key_shape(live)


def test_cached_stabilise_has_the_same_key_shape_as_a_live_one():
    live = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})
    cached = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3&demo=1", {})

    assert key_shape(cached) == key_shape(live)


def test_cached_boundary_grid_is_still_a_full_grid():
    cached = api.handle("/api/boundary?leverage=5&gamma=0.2&demo=1", {})

    assert len(cached["grid"]) == cached["rows"]
    assert all(len(row) == cached["cols"] for row in cached["grid"])


def test_cached_values_are_the_recorded_ones_not_a_stub():
    live = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})
    cached = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&demo=1", {})

    assert cached["asset_index"] == live["asset_index"]
    assert cached["metrics"]["amplification"] == live["metrics"]["amplification"]


# --- nearest match --------------------------------------------------------


def test_a_slider_position_we_never_recorded_still_answers():
    """Judges drag sliders. 5.37 is not on the recorded grid.

    This used to assert `cached is True` — that an off-grid position was
    answered FROM A RECORDING. That was the bug: the nearest recording to
    leverage 2.5 was the one made at 1.5, and serving it put a 3.1x error on
    screen (25.8x on /api/stabilise's sell instruction). The requirement was
    always "it still answers", never "it answers from disk", and it answers by
    computing — which costs 11-20ms and needs no network.
    """
    result = api.handle("/api/break?leverage=5.37&gamma=0.23&breaches=3&demo=1", {})

    assert result["found"] is True
    assert result["asset"] in result["tickers"]
    if result.get("cached"):
        assert result["cached_exact"], "served a recording of different settings"
    live = api.handle("/api/break?leverage=5.37&gamma=0.23&breaches=3", {})
    assert result["pct"] == pytest.approx(live["pct"], rel=1e-9)


def test_nearest_match_picks_the_closest_recording_not_just_any():
    low = api.handle("/api/break?leverage=3.1&gamma=0.2&breaches=3&demo=1", {})
    high = api.handle("/api/break?leverage=7.9&gamma=0.2&breaches=3&demo=1", {})

    assert low["magnitude"] != high["magnitude"], (
        "both ends of the slider returning the same recording means the "
        "distance function isn't looking at leverage"
    )


def test_nearest_match_never_crosses_routes():
    result = api.handle("/api/boundary?leverage=99&gamma=9&demo=1", {})

    assert "grid" in result and "trajectory" not in result


# --- a dead engine ---------------------------------------------------------


def test_a_blown_up_engine_falls_back_to_the_recording(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("edgar timed out")

    monkeypatch.setattr(api, "load_dataset", explode)
    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})

    assert result["cached"] is True
    assert "edgar timed out" in result["fallback_reason"]
    assert result["found"] is True


def test_the_fallback_payload_is_still_the_right_shape(monkeypatch):
    live = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})

    def explode(*args, **kwargs):
        raise ZeroDivisionError("float division by zero")

    monkeypatch.setattr(api, "run_cascade", explode)
    broken = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})

    assert broken["cached"] is True
    assert key_shape({k: v for k, v in broken.items()
                      if k != "fallback_reason"}) == key_shape(live)


def test_every_endpoint_survives_a_dead_dataset(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(api, "load_dataset", explode)
    for route in ["/api/dataset", "/api/break", "/api/stabilise", "/api/boundary"]:
        result = api.handle(route, {})
        assert result["cached"] is True, route
        assert result["fallback_reason"], route


def test_unknown_routes_are_still_a_404_even_in_demo_mode():
    with pytest.raises(api.NotFound):
        api.handle("/api/nope?demo=1", {})


# --- the recorder ----------------------------------------------------------


def test_recorder_writes_one_file_per_endpoint_and_says_so():
    written = api.record_golden()

    assert len(written) >= 5
    assert all(path.exists() for path in written)
    assert any(path.name.startswith("break__") for path in written)
    assert any(path.name == "health.json" for path in written)


def test_recordings_are_stored_with_the_flag_already_flipped():
    import json

    path = api.GOLDEN / "break__band=1.05__breaches=3__gamma=0.2__leverage=5.json"
    payload = json.loads(path.read_text())

    assert payload["cached"] is True


# --- nearest-match has to stay honest about what it matched ---------------


def test_a_recording_says_which_sliders_produced_it():
    """`cached: true` tells you it came off disk, not what it came off disk for."""
    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&demo=1", {})

    assert result["cached_for"] == {"leverage": 5.0, "gamma": 0.2, "band": 1.05, "breaches": 3.0}
    assert result["cached_exact"] is True


def test_settings_nowhere_near_a_recording_are_computed_rather_than_faked():
    """Dragging leverage to 40 and asking for 5 breaches used to serve the
    leverage-7 / 3-breach recording, hero number and all, with nothing in the
    payload saying the answer belonged to a different question.

    The assertion that used to live here could not fail. It compared
    `cached_for` against a three-key dict — `{leverage, gamma, breaches}` —
    and `cached_for` gained a fourth key when `band` joined KNOBS. So the
    `!=` held for structural reasons, whatever the values were, and the whole
    branch was inert twice over: `cached` is False at HEAD, so it was not even
    taken. Third test found tonight that passes because it stopped being able
    to fail.

    What it should say is that the answer belongs to the question asked.
    """
    q = "leverage=40&gamma=9&breaches=5"
    live = api.handle(f"/api/break?{q}", {})
    demo = api.handle(f"/api/break?{q}&demo=1", {})

    if not demo["cached"]:
        assert demo.get("magnitude") == live.get("magnitude")
        return

    assert demo["cached_exact"] is False
    for knob, asked in (("leverage", 40.0), ("gamma", 9.0), ("breaches", 5.0)):
        assert demo["cached_for"][knob] != asked, (
            f"served a recording claiming to be for {knob}={asked}, which is "
            "not a setting anything was ever recorded at"
        )
    assert demo["magnitude"] != live["magnitude"], (
        "if the recording matched the live answer there would be nothing to "
        "warn about; this test is checking the case where it does not"
    )


def test_the_near_enough_threshold_is_held_from_above_as_well_as_below():
    """`_NEAR_ENOUGH` decides whether to answer a different question at all.

    Nothing constrained it upward. A review agent widened it from 0.0625 to
    1.0, 16, 100 and even 110 with all 218 tests green — at 110 the leverage-40
    recording is close enough to serve. The cost at every slider on an end
    (leverage 8, gamma 1.0, band 1.5, breaches >=5, all reachable by dragging):

        HEAD    computes live          -> hero NVDA 14.38%
        widened serves a recording     -> hero NVDA 27.33%

    A 1.9x error on the headline, in the mode the demo actually runs in. The
    badge does name the settings it fell back to, so it is labelled rather
    than hidden — but labelling is not the job of this threshold. Its job is
    to not answer a different question in the first place.
    """
    from firebreak.api import _NEAR_ENOUGH, _distance

    # The distance is a sum of squared, scale-normalised knob differences, so
    # 1.0 means "one full scale-unit away on one knob, or the equivalent
    # spread across several". Serving a recording from further than that is
    # answering a different question, whatever the badge says. This is the
    # bound that was missing: 1.0, 16, 100 and 110 all passed the suite.
    assert _NEAR_ENOUGH < 1.0, (
        f"_NEAR_ENOUGH is {_NEAR_ENOUGH}; at or above 1.0 a recording a whole "
        "scale-unit away counts as near enough, and at 110 the leverage-40 "
        "recording does"
    )

    # And a concrete one. It has to be a point the guards will not CLAMP into
    # range, which is what made the old leverage=40 case unreachable: 40 is
    # pulled back to 8, and 8 is recorded, so the branch it was testing never
    # ran. This is the farthest point inside the sliders' own limits.
    asked = {"leverage": 1.0, "gamma": 1.0, "band": 1.5, "breaches": 5.0}
    nearest = min(
        _distance("/api/break", asked, {k: float(v) for k, v in knobs.items()})
        for route, knobs in api.golden_specs() if route == "/api/break"
    )
    assert nearest > _NEAR_ENOUGH, (
        f"the farthest reachable slider position is {nearest:.3f} from its "
        f"nearest recording and _NEAR_ENOUGH is {_NEAR_ENOUGH}"
    )
    # `cached` is the field that means something here. `cached_near` and
    # `cached_exact` describe the recording that WAS served, so on a live
    # response they are trivially true — asserting on them was checking a
    # field that had no recording to be about.
    far = api.handle(
        "/api/break?leverage=1&gamma=1.0&band=1.5&breaches=5&demo=1", {})
    assert far["cached"] is False, (
        "demo mode served a recording at the farthest reachable settings; "
        f"cached_for={far.get('cached_for')}"
    )
    near = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&demo=1", {})
    assert near["cached"] is True, (
        "and it must still serve one at a setting it was recorded at, or this "
        "test would pass with the cache switched off entirely"
    )


def test_a_dead_engine_falls_back_but_names_the_settings_it_fell_back_to(monkeypatch):
    """When the engine genuinely cannot answer, a recording is the right call —
    as long as it says so.

    This used to force the failure with `leverage=0.5`, which made the engine
    refuse because target leverage fell below 1. Parameter guards now clamp
    that before it reaches the engine, so the crash path isn't reachable from
    a URL any more — which is the point of the guards. Break the engine for
    real instead.
    """
    def boom(*args, **kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(api, "run_cascade", boom)

    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})

    assert result["cached"] is True
    assert result["fallback_reason"]
    assert "engine exploded" in result["fallback_reason"]


def test_guards_stop_a_url_from_reaching_the_crash_path():
    """The old way of killing the engine is now unreachable, deliberately."""
    result = api.handle("/api/break?leverage=0.5&gamma=0.2&breaches=3", {})

    assert result["cached"] is False, "guards should have made this computable"
    assert result["params"]["leverage"] >= 1.0


def test_exact_means_exact_not_merely_close():
    """`cached_exact` drives whether the UI says "cached run" or names the
    settings it actually served. Calling a near miss exact makes the hero
    number look like an answer to the question that was asked.

    Distance was normalised by slider span against a 0.25 threshold, so
    leverage 6.0 standing in for 6.4 AND gamma 0.2 standing in for 0.35 both
    scored inside it and the payload claimed exactness.
    """
    result = api.handle("/api/break?leverage=6.4&gamma=0.35&breaches=3&demo=1", {})

    # Demo mode no longer serves a recording that is not of these settings, so
    # the near-miss-called-exact case is now unreachable from here. The
    # invariant is what matters and it is stated either way: anything served
    # from disk is OF the settings asked for.
    if result.get("cached"):
        assert result["cached_exact"] is True, (
            f"served a recording for {result['cached_for']} and called it exact"
        )
        assert result["cached_for"] == {"leverage": 6.4, "gamma": 0.35, "breaches": 3.0}


def test_a_recording_of_the_asked_for_settings_is_exact():
    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&demo=1", {})

    assert result["cached"] is True
    assert result["cached_exact"] is True
    assert result["cached_for"] == {"leverage": 5.0, "gamma": 0.2, "band": 1.05, "breaches": 3.0}


# The slider positions that bit: each sits between two recordings, close
# enough for the old threshold to serve one, far enough that the served answer
# is a different answer. (route, knobs, what the recording claimed, the truth)
OFF_GRID = [
    ("/api/break", {"leverage": 2.5, "breaches": 3}),
    ("/api/break", {"leverage": 2.75, "breaches": 3}),
    ("/api/break", {"leverage": 2.76, "breaches": 3}),
    ("/api/break", {"leverage": 3.0, "breaches": 3}),
    ("/api/stabilise", {"leverage": 3.0, "breaches": 3}),
    ("/api/stabilise", {"leverage": 2.5, "breaches": 3}),
    ("/api/break", {"band": 1.01, "breaches": 3}),
    ("/api/break", {"band": 1.40, "breaches": 3}),
]


@pytest.mark.parametrize("route,knobs", OFF_GRID)
def test_demo_mode_computes_rather_than_serving_a_neighbours_answer(route, knobs):
    """A recording may only stand in for the settings it was recorded at.

    `_NEAR_ENOUGH` was an rms quarter-of-a-slider, which sounds tight until you
    notice the leverage axis is recorded at 1.5 and then not again until 4.0.
    Everything in that 2.5-turn hole was "near" something, so demo mode served
    it:

        /api/break?leverage=2.5&breaches=3     demo 51.527%   live 16.832%
        /api/stabilise?leverage=3&breaches=3   demo sell $1,327,529
                                               live sell $51,406

    25.8x, on the one line in the whole product that tells somebody to do
    something. And the error changes sign across the hole, so it was not even
    conservative: at leverage 3.0 the demo understates the break point.

    There was a cliff at the midpoint too — leverage 2.75 served the 1.5
    recording and 2.76 served the 4.0 one, a 6.8x jump from a nudge of the
    slider, both labelled `cached_near: true`.

    Computing is cheap and always available: the dataset is committed, so
    nothing here needs a network. A recording is served when it is OF these
    settings, and otherwise we do the arithmetic.
    """
    query = "&".join(f"{k}={v}" for k, v in knobs.items())
    served = api.handle(f"{route}?{query}&demo=1", {})
    live = api.handle(f"{route}?{query}", {})

    if served.get("cached"):
        assert served.get("cached_exact"), (
            f"{route} at {knobs} served a recording made at "
            f"{served.get('cached_for')}, which is a different question"
        )

    # and the number has to be the number
    assert served["pct"] == pytest.approx(live["pct"], rel=1e-9), (
        f"demo mode answers {served['pct']:.3f}% where the engine says "
        f"{live['pct']:.3f}%"
    )


def test_a_recorded_spot_is_still_served_from_disk():
    """The tightening must not turn demo mode off — that is the whole feature."""
    spot = api.GOLDEN_SPOTS[0]
    query = "&".join(f"{k}={v}" for k, v in spot.items())
    out = api.handle(f"/api/break?{query}&demo=1", {})
    assert out.get("cached") is True, "a recorded spot stopped being served"
    assert out.get("cached_exact") is True
