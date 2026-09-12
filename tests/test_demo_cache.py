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
    # judges drag sliders. 5.37 is not on the recorded grid.
    result = api.handle("/api/break?leverage=5.37&gamma=0.23&breaches=3&demo=1", {})

    assert result["cached"] is True
    assert result["found"] is True
    assert result["asset"] in result["tickers"]


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
    payload saying the answer belonged to a different question."""
    live = api.handle("/api/break?leverage=40&gamma=9&breaches=5", {})
    demo = api.handle("/api/break?leverage=40&gamma=9&breaches=5&demo=1", {})

    if demo["cached"]:
        assert demo["cached_for"] != {"leverage": 40.0, "gamma": 9.0, "breaches": 5.0}
        assert demo["cached_exact"] is False
    else:
        assert demo.get("magnitude") == live.get("magnitude")


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

    assert result["cached"] is True
    if result["cached_for"] != {"leverage": 6.4, "gamma": 0.35, "breaches": 3.0}:
        assert result["cached_exact"] is False, (
            f"served a recording for {result['cached_for']} and called it exact"
        )


def test_a_recording_of_the_asked_for_settings_is_exact():
    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&demo=1", {})

    assert result["cached"] is True
    assert result["cached_exact"] is True
    assert result["cached_for"] == {"leverage": 5.0, "gamma": 0.2, "band": 1.05, "breaches": 3.0}
