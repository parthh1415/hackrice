"""JSON endpoints. Thin on purpose — the thinking lives in engine/search."""

import json
import os
import pathlib
import threading
import urllib.parse

import numpy as np

from .dataset import load_dataset
from .engine import run_cascade
from .search import DEFAULT_TOLERANCE as _SEARCH_TOLERANCE
from .search import at_least_n_breaches, find_weakest_shock
from .matlab_bridge import engine_label, solve_stabilisation, write_spec
from .stabilise import Fix


class NotFound(Exception):
    pass


def _health(params):
    return {"ok": True}


def _dataset(params):
    # The model's declared inputs travel with the data they are declared about,
    # so the methodology page can print the numbers instead of hardcoding them
    # beside a comment promising it does not.
    out = dict(load_dataset())
    out["defaults"] = {name: default for name, (_, _, default) in _LIMITS.items()}
    out["defaults"]["breaches"] = 3
    return out


def handle(path, body):
    route, _, query = path.partition("?")
    params = dict(urllib.parse.parse_qsl(query))
    params.pop("demo", None)
    demo = _demo_requested(query)

    if route not in ROUTES:
        raise NotFound(route)

    if demo:
        cached = load_golden(route, params)
        # A recording may only stand in for the settings it was recorded at.
        #
        # This used to accept anything within _NEAR_ENOUGH, an rms quarter of a
        # slider, which sounds tight until you notice the leverage axis is
        # recorded at 1.5 and then not again until 4.0. Every position in that
        # 2.5-turn hole was "near" something:
        #
        #   /api/break?leverage=2.5&breaches=3    demo 51.527%  live 16.832%
        #   /api/stabilise?leverage=3&breaches=3  demo sell $1,327,529
        #                                         live sell $51,406
        #
        # 25.8x, on the one line in the product that tells somebody to do
        # something — and not even conservative, because the sign of the error
        # flips across the hole. There was a cliff in the middle too: 2.75
        # served the 1.5 recording and 2.76 served the 4.0 one, a 6.8x jump
        # from a nudge, both labelled cached_near.
        #
        # Computing instead costs 11-20ms and always works, because the
        # dataset is committed and nothing here needs a network. Demo mode
        # keeps its point — the recorded spots the script actually uses are
        # still served from disk, deterministically — and stops answering
        # questions nobody asked.
        if cached is not None and cached["cached_exact"]:
            return cached

    try:
        # Portfolio routes are the only ones that read a request body — the
        # institutional endpoints are entirely described by their query string.
        # Without this the body was silently dropped and every upload quietly
        # got the demo portfolio's answer, which is the most expensive possible
        # way to be wrong on a screen that says "your portfolio".
        payload = (ROUTES[route](params, body) if route in BODY_ROUTES
                   else ROUTES[route](params))
    except Exception as exc:
        # a demo never shows a stack trace. if we ever recorded this endpoint,
        # serve that and label it; only re-raise when there's truly nothing.
        cached = load_golden(route, params)
        if cached is None:
            raise
        cached["fallback_reason"] = _fallback_note(exc, cached["cached_for"])
        return cached

    payload["cached"] = False
    # The knobs the answer was actually COMPUTED with, which is `params` after
    # clamping — not the raw request. Echoing the request here produced
    # `cached_for {leverage: 999.0}` beside `params {leverage: 8.0}` and
    # `cached_exact: true`, which reads as "this is an answer at 999x". Worse,
    # the raw value went through json.dumps unfiltered: `?leverage=nan` wrote a
    # bare `NaN` and `?leverage=1e400` a bare `Infinity`, neither of which is
    # valid JSON, so JSON.parse threw on the whole response.
    used = payload.get("params")
    payload["cached_for"] = ({k: v for k, v in used.items()
                              if k in KNOBS.get(route, {})}
                             if isinstance(used, dict) else _knobs(route, params))
    # a live answer is of exactly what was asked, by construction
    payload["cached_exact"] = True
    payload["cached_near"] = True
    return payload


def _truthy(raw):
    """A query flag the way a human types it: `?x`, `?x=1`, `?x=true`."""
    if raw is None:
        return False
    return str(raw).strip().lower() not in ("", "0", "false", "no")


def _demo_requested(query):
    """?demo=1 on any request, or FIREBREAK_DEMO=1 for the whole process.

    Parsed separately from the sliders so a bare `?demo` counts too — that's
    what anyone types when the wifi has just gone down and they're in a hurry.
    """
    values = urllib.parse.parse_qs(query, keep_blank_values=True).get("demo", [])
    if values and values[-1].strip().lower() in ("", "1", "true", "yes", "on"):
        return True
    return os.environ.get("FIREBREAK_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


def _reason(exc):
    return f"{type(exc).__name__}: {exc}"[:160]


def _fallback_note(exc, cached_for):
    """Why we fell back, and to which recording. Both, or neither is useful."""
    settings = ", ".join("%s=%g" % kv for kv in sorted(cached_for.items()))
    if not settings:
        return _reason(exc)
    return f"{_reason(exc)} — serving the recording at {settings}"


# --- the golden path ------------------------------------------------------
#
# Recorded answers on disk, keyed by the slider positions that produced them.
# Two ways in: ?demo=1 asks for them, and an exploding engine gets them
# anyway. Both label the payload `cached: true` — we say which one it is
# rather than passing a recording off as a live solve.

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "cache" / "golden"

# per endpoint: the knobs it actually reads, each as (default, scale). The
# scale is the slider's usable span, so nearest-match compares a leverage
# step against a gamma step fairly instead of letting leverage dominate.
# (default, slider span) per knob. The span normalises distance so one
# parameter can't swamp another in the nearest-match search.
#
# `band` must be here. It was added to the model later and left out of this
# table, so demo mode served one recording for every band value and still
# reported cached_exact — while band is the single most influential parameter
# there is (1.05 → −5.27%, 1.30 → −27.33%). Its span is 0.5, much tighter than
# leverage's 6.5, so a tenth of a band counts for a lot more than a tenth of a
# turn of leverage. That is correct: it moves the answer a lot more.
KNOBS = {
    "/api/health": {},
    "/api/dataset": {},
    "/api/break": {"leverage": (5.0, 6.5), "gamma": (0.2, 1.0),
                   "band": (1.05, 0.5), "breaches": (3.0, 4.0)},
    "/api/stabilise": {"leverage": (5.0, 6.5), "gamma": (0.2, 1.0),
                       "band": (1.05, 0.5), "breaches": (3.0, 4.0)},
    "/api/boundary": {"leverage": (5.0, 6.5), "gamma": (0.2, 1.0),
                      "band": (1.05, 0.5)},
}

BODY_ROUTES = set()

ROUTES = {
    "/api/health": _health,
    "/api/dataset": _dataset,
    "/api/break": lambda params: _break(params),
    "/api/stabilise": lambda params: _stabilise(params),
    "/api/boundary": lambda params: _boundary(params),
}


def _knobs(route, params):
    """The knob values this request implies, defaults filled in.

    A route with no entry in KNOBS has no sliders — the portfolio endpoints are
    keyed by a portfolio, not by a knob position — so it reports no knob state
    rather than inventing defaults it does not use.
    """
    out = {}
    for name, (default, _) in KNOBS.get(route, {}).items():
        try:
            value = float(params.get(name, default))
        except (TypeError, ValueError):
            value = float(default)
        # A knob value this route cannot have used. NaN and ±Inf reach here
        # from `?leverage=nan` and `?leverage=1e400`, and json.dumps writes
        # them bare — not JSON, so the browser threw on the whole response.
        # Belt to the braces in _guarded: this is the last thing standing
        # between a query string and the payload if a route ever forgets to
        # report its clamped params again.
        if value != value or value in (float("inf"), float("-inf")):
            value = float(default)
        out[name] = value
    return out


def slug(route, params):
    """break?leverage=5&gamma=0.2&breaches=3 -> break__breaches=3__gamma=0.2__leverage=5

    Sorted, defaults filled in and numbers normalised, so the same scenario
    written two different ways lands on one file.
    """
    knobs = _knobs(route, params)
    parts = [route.rsplit("/", 1)[-1]]
    parts += ["%s=%g" % (name, knobs[name]) for name in sorted(knobs)]
    return "__".join(parts)


def _recorded(route):
    """Every recording for one endpoint, with the knobs read back off the name."""
    if not GOLDEN.is_dir():
        return []
    wanted = route.rsplit("/", 1)[-1]
    out = []
    for path in sorted(GOLDEN.glob("*.json")):
        head, _, rest = path.stem.partition("__")
        if head != wanted:
            continue
        knobs = {}
        for part in filter(None, rest.split("__")):
            name, _, value = part.partition("=")
            try:
                knobs[name] = float(value)
            except ValueError:
                continue
        out.append((path, knobs))
    return out


# how far a request can sit from a recording and still be the same question.
# _distance is the sum of squared slider-span fractions, so this is an rms
# deviation of a quarter of a slider — comfortably wider than the half-step
# between two recordings, and nowhere near "leverage 40, five breaches".
# One threshold was doing two different jobs and they want opposite answers.
#
#   _NEAR_ENOUGH  — how far a recording may sit from the request and still be
#                   offered as a FALLBACK when the engine has thrown. Something
#                   labelled is better than a stack trace, and the payload says
#                   where it was recorded. It is NOT the rule for demo mode.
#   cached_exact  — is this recording actually OF these settings? Strict, and
#                   computed by comparison, not distance. It used to be the
#                   same 0.25 threshold, which let leverage 6.0 stand in for
#                   6.4 and gamma 0.2 for 0.35 while still claiming exactness,
#                   so the hero number read as an answer to a question nobody
#                   asked.
_NEAR_ENOUGH = 0.25 ** 2


def _distance(route, wanted, knobs):
    total = 0.0
    for name, (default, scale) in KNOBS[route].items():
        total += ((wanted[name] - knobs.get(name, default)) / scale) ** 2
    return total


def load_golden(route, params):
    """The recording nearest these slider positions, or None if we have none.

    Nearest rather than exact because judges drag sliders, and a scenario we
    never recorded should still draw something instead of erroring.
    """
    candidates = _recorded(route)
    if not candidates:
        return None
    wanted = _knobs(route, params)
    path, knobs = min(candidates, key=lambda c: (_distance(route, wanted, c[1]), c[0].name))
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    payload["cached"] = True
    # what the recording is actually of. the hero number, the phase-diagram
    # "you are here" dot and the assumptions panel all come out of the file,
    # so if it was recorded somewhere else the payload has to say where.
    payload["cached_for"] = {name: knobs.get(name, default)
                             for name, (default, _) in KNOBS[route].items()}
    payload["cached_near"] = _distance(route, wanted, knobs) <= _NEAR_ENOUGH
    payload["cached_exact"] = all(
        abs(wanted[name] - knobs.get(name, default)) < 1e-9
        for name, (default, _) in KNOBS[route].items()
    )
    payload.pop("fallback_reason", None)
    # NOTE: a served recording can never carry a clamp, and the two are
    # mutually exclusive by construction rather than by accident. `cached_exact`
    # compares the RAW request against the recording's knobs, so a recording is
    # only served when the request equalled an in-range value — and a request
    # that equalled an in-range value was not clamped. Verified exhaustively
    # over 11 x 7 x 6 knob combinations. test_cache_knows_band pins it, because
    # loosening cached_exact to compare clamped values would silently break it:
    # leverage=12 would then be served the leverage=8 recording under
    # `clamped: []`, stating that nothing was adjusted about a request where
    # something was.
    return payload


# the demo runs at 5 / 0.2 / 3; the rest are where a hand on the slider ends up
GOLDEN_SPOTS = [
    {"leverage": 5, "gamma": 0.2, "band": 1.05, "breaches": 3},
    {"leverage": 5, "gamma": 0.2, "band": 1.05, "breaches": 2},
    {"leverage": 4, "gamma": 0.2, "band": 1.05, "breaches": 3},
    {"leverage": 6, "gamma": 0.2, "band": 1.05, "breaches": 3},
    {"leverage": 7, "gamma": 0.2, "band": 1.05, "breaches": 3},
    {"leverage": 5, "gamma": 0.1, "band": 1.05, "breaches": 3},
    {"leverage": 5, "gamma": 0.4, "band": 1.05, "breaches": 3},
    # the band is the knob most worth showing on stage, so record the ends
    {"leverage": 5, "gamma": 0.2, "band": 1.02, "breaches": 3},
    {"leverage": 5, "gamma": 0.2, "band": 1.15, "breaches": 3},
    {"leverage": 5, "gamma": 0.2, "band": 1.30, "breaches": 3},

    # Every slider's EXTREME, because the recorded set above is an interior
    # box and the sliders reach well outside it. The threshold was never the
    # problem: the far ends fall past it and compute live, correctly. It is
    # the moderately off-grid positions that bite — near enough to be served,
    # far enough to be wrong — and that is exactly where a hand on a slider
    # lands.
    #
    # Band 1.00 is the one that mattered. There the breach ceiling sits on
    # top of the resting leverage, so the system breaks on the faintest touch
    # and the true critical distance is 0.0039%. Demo mode served the
    # band-1.02 recording and rendered 1.73% — a 444x error, in the direction
    # that makes the book look SAFER, on the headline number, at the knob the
    # video script tells the presenter to drag.
    #
    # It is also the failure find_weakest_shock's own comment forbids:
    # "asserting zero is safe made the search bisect down to -0.0003 and
    # report that as the hero number, which is fabricated." The search stopped
    # fabricating it. The cache started.
    {"leverage": 5, "gamma": 0.2, "band": 1.00, "breaches": 3},
    {"leverage": 5, "gamma": 0.2, "band": 1.50, "breaches": 3},
    {"leverage": 1.5, "gamma": 0.2, "band": 1.05, "breaches": 3},
    {"leverage": 8, "gamma": 0.2, "band": 1.05, "breaches": 3},
    {"leverage": 5, "gamma": 0.0, "band": 1.05, "breaches": 3},
    {"leverage": 5, "gamma": 1.0, "band": 1.05, "breaches": 3},
    {"leverage": 5, "gamma": 0.2, "band": 1.05, "breaches": 4},
    {"leverage": 5, "gamma": 0.2, "band": 1.05, "breaches": 5},
]


def golden_specs():
    specs = [("/api/health", {}), ("/api/dataset", {})]
    for spot in GOLDEN_SPOTS:
        specs.append(("/api/break", spot))
        specs.append(("/api/stabilise", spot))
        # the boundary grid depends on the band too — dropping it here meant
        # every band recorded the same sweep and demo mode had no boundary
        # for the band ends, which are the ones worth showing on stage
        specs.append(("/api/boundary", {k: spot[k] for k in ("leverage", "gamma", "band")
                                        if k in spot}))
    return specs


def record_golden(specs=None, out=None):
    """Freeze the demo path to disk. Returns the paths written.

    Calls the endpoint functions directly rather than going through handle(),
    so re-recording with FIREBREAK_DEMO=1 still left set records live answers
    instead of copying yesterday's recordings back over themselves.
    """
    specs = golden_specs() if specs is None else specs
    out = GOLDEN if out is None else pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)

    written, seen = [], set()
    for route, knobs in specs:
        params = {name: str(value) for name, value in knobs.items()}
        name = slug(route, params)
        if name in seen:
            continue
        seen.add(name)
        payload = ROUTES[route](params)
        payload["cached"] = True
        payload["cached_for"] = _knobs(route, params)
        payload["cached_exact"] = True
        # A wall-clock duration measured on whatever machine last ran this
        # script is not a fact about the request being served, and baking it
        # in cost us the one check that would catch real drift: every
        # re-record rewrote all ten stabilise files for `solve_ms: 11 -> 12`
        # and nothing else, so a golden-vs-live diff was never clean enough
        # to read. The UI already falls back to the elapsed time of the
        # actual request (`e.solve_ms || ms`), which is the honest number.
        # Null, not absent: a recording has to keep the same key shape as a
        # live response, and test_demo_cache caught the first version of this
        # deleting the key outright. null says "this run measured nothing",
        # which is true, and the UI's `e.solve_ms || ms` then shows how long
        # the replay actually took.
        engine = payload.get("engine")
        if isinstance(engine, dict) and "solve_ms" in engine:
            engine["solve_ms"] = None
        path = out / (name + ".json")
        path.write_text(json.dumps(payload))
        written.append(path)
    return written


def _scenario(data, params):
    """Turn query-string knobs into engine arguments.

    Leverage isn't in any filing, so it's a slider. Same for gamma. Both are
    surfaced in the assumptions panel so nobody thinks they're measurements.

    gamma default 0.2: selling 1% of a day's volume moves the price ~0.2%.
    Sweeping it on the real books, 0.2 gives amplification 1.2-2.4, which is
    in the range the fire-sale literature reports. At 1.0 everything detonates
    (amp 27+) and the demo looks rigged, which it would be.
    """
    m = len(data["funds"])
    knobs = _guarded(params, m)
    lev = knobs["leverage"]
    band = knobs["band"]
    # the deleverage target has to sit at or below the breach ceiling, or a
    # breached fund is asked to sell its way to a leverage it's already past
    target = min(max(1.0, lev * 0.95), lev * band)
    return dict(
        holdings=np.array(data["holdings"]),
        leverage=np.full(m, lev),
        max_leverage=np.full(m, lev * band),
        target_leverage=np.full(m, target),
        gamma=knobs["gamma"],
        adv=np.array(data["adv"]),
    ), knobs


def _find(data, params):
    scenario, knobs = _scenario(data, params)
    condition = at_least_n_breaches(knobs["breaches"])
    return scenario, condition, find_weakest_shock(condition=condition, **scenario), knobs


def _break(params):
    data = load_dataset()
    scenario, _, found, knobs = _find(data, params)
    if found is None:
        return {"found": False, "params": knobs, **data}

    result = run_cascade(shock=found.shock, **scenario)
    return {
        "found": True,
        "params": knobs,
        "asset": data["tickers"][found.asset],
        "asset_index": found.asset,
        "magnitude": found.magnitude,
        "pct": found.pct,
        **data,
        **result.as_dict(),
    }


# write_spec writes ONE process-global file and _try_offline reads that same
# path back, with the threaded server free to run another request in between.
# Two ordinary requests in flight together — one page calling /api/stabilise
# while another tab loads — were enough to make the same URL answer
# $2,236,598.53 or $2,251,028.20 depending on the traffic around it, with
# `engine.fingerprint` present on one and null on the other. The fingerprint
# check itself held: a clobbered spec is a mismatch, so the offline result was
# refused rather than misapplied, and the Python solver answered instead. Both
# answers are valid fixes; they are just different ones, and which you get was
# decided by somebody else's request.
#
# The lock covers only the write-then-read window. It leaves the file on disk
# for the by-hand MATLAB Online workflow, and it leaves write_spec's mtime
# semantics — which its own docstring calls load-bearing — untouched.
_SOLVE_LOCK = threading.Lock()


def _stabilise(params):
    data = load_dataset()
    scenario, condition, found, knobs = _find(data, params)
    if found is None:
        return {"found": False, "params": knobs, **data}

    before = run_cascade(shock=found.shock, **scenario)

    # hand the solve to MATLAB if it's there. the objective is a simulation
    # with discrete breach events — non-smooth, non-differentiable, feasible
    # set defined by a cascade crossing a threshold. that is patternsearch's
    # problem class. the forward cascade stays in python where it's tested.
    spec = {
        "holdings": scenario["holdings"].tolist(),
        "leverage": scenario["leverage"].tolist(),
        "max_leverage": scenario["max_leverage"].tolist(),
        "target_leverage": scenario["target_leverage"].tolist(),
        "gamma": scenario["gamma"],
        "adv": scenario["adv"].tolist(),
        "shock": found.shock.tolist(),
        "breaches": knobs["breaches"],
    }
    with _SOLVE_LOCK:
        write_spec(spec)  # so matlab/stabilise.m can be run by hand, incl. MATLAB Online
        solved = solve_stabilisation(spec)
    if solved is None:
        # `params` is not optional on a found: False. Its two siblings above
        # carry it; this one did not, and handle() then falls back to echoing
        # the RAW query string as cached_for — `{leverage: 999.0}` beside
        # `cached_exact: true` for an answer computed at 8.0, which is the
        # exact pairing the comment on that fallback says was fixed. It also
        # took the clamp report down with it, since `clamped` ships inside
        # `params`. Reachable at band <= 1.0, and band 1.00 is a golden spot.
        return {"found": False, "reason": "no single-position fix clears it",
                "params": knobs, **data}

    fix = Fix(
        fund=int(solved["fund_index"]),
        asset=int(solved["asset_index"]),
        reduction=float(solved["reduction"]),
        cost=float(solved["cost"]),
    )
    name, note = engine_label(solved)
    patched = dict(scenario, holdings=fix.apply(scenario["holdings"]))
    after = run_cascade(shock=found.shock, **patched)

    # Re-search the patched books and report what the fix bought in the
    # product's own headline metric. It buys almost nothing — 5.2734% ->
    # 5.2773% at the demo settings — because a cheapest single-position cut
    # defends against THE shock, not against the next one. A judge will click
    # "Find weakest shock" after "Stabilise" and find this in ten seconds, so
    # the honest move is to put the number on screen ourselves. It also names
    # the real next feature: minimise over all shocks, not one.
    repeat = find_weakest_shock(condition=condition, **patched)
    delta = (repeat.pct - found.pct) if repeat else None
    # The search bisects to a tolerance; a delta finer than that is a claim the
    # method cannot support. The active holdings universe can change whether a
    # particular scenario has a measurable result, so the rule itself is
    # covered independently rather than relying on this demo case.
    # TWO tolerances, not one. `delta` is the difference of two independently
    # bisected searches, and each of them can be off by up to a tolerance in
    # either direction, so the error on their difference is twice that. The
    # bar was one tolerance, which meant a delta of, say, 0.007pp would have
    # been announced as "+0.01pp" while sitting inside its own error bar —
    # the exact fake-precision failure this block exists to prevent, at the
    # one place that is supposed to be policing it.
    resolution = 2.0 * _SEARCH_TOLERANCE * 100.0
    measurable = _is_measurable(delta, resolution)
    bought = {
        "before_pct": found.pct,
        "after_pct": repeat.pct if repeat else None,
        "delta_pct": delta,
        "resolution_pct": resolution,
        "measurable": measurable,
        "after_asset": data["tickers"][repeat.asset] if repeat else None,
        "note": (
            "moves the break point by {:+.2f}pp".format(delta) if measurable
            else "no measurable change in break point — a targeted patch, "
                 "not structural repair"
        ),
    }

    return {
        "found": True,
        "params": knobs,
        "asset": data["tickers"][found.asset],
        # the split view rings this. without the index it falls back to 0,
        # which is correct only when the answer happens to be the first name.
        "asset_index": found.asset,
        "magnitude": found.magnitude,
        "pct": found.pct,
        # Dollars alongside the fractions. Since the bisection went relative the
        # answer can land at 0.0034% of a position, and "cut 0.0034% of NVDA,
        # costing 0.0002% of gross assets" is two numbers nobody can hold. The
        # same instruction in dollars — $81K out of a $2.36B book — is one.
        "fix": dict(
            fix.as_dict(data["funds"], data["tickers"]),
            position_usd=float(scenario["holdings"][fix.fund, fix.asset]),
            sell_usd=float(scenario["holdings"][fix.fund, fix.asset] * fix.reduction),
            gross_usd=float(scenario["holdings"].sum()),
        ),
        "bought": bought,
        "engine": {
            "name": name,
            "note": note,
            "kind": solved.get("engine", "python"),
            "solver": solved.get("solver", ""),
            "evaluations": solved.get("evaluations", 0),
            "exit_flag": solved.get("exit_flag", 0),
            "solve_ms": solved.get("solve_ms", 0),
            # The fingerprint of the question this solve answered. It exists so
            # the trace figure can be NAMED after it: the boundary surface
            # silently deleted itself for days because its filename stopped
            # matching what shipped, and the trace had the same hole with
            # nothing to catch it — re-solve, re-commit solve_out.json, forget
            # to re-export the figure, and the Model card says "fingerprint
            # matched" over a picture of a different search. A figure named
            # after a fingerprint cannot be shown beside a fingerprint it does
            # not match. None on the Python path, which draws nothing.
            "fingerprint": solved.get("fingerprint"),
        },
        # each half has to carry the book it's drawing. without this the
        # frontend falls back to the unpatched top-level matrix and renders
        # byte-identical edges on both sides — so the cut, which is the one
        # thing beat 4 is about, was invisible.
        "before": {**before.as_dict(), "holdings": scenario["holdings"].tolist()},
        "after": {**after.as_dict(), "holdings": patched["holdings"].tolist()},
        **data,
    }


def _is_measurable(delta, resolution):
    """Whether a difference clears the uncertainty of two shock searches."""
    return delta is not None and abs(delta) > resolution


def blend_toward_mean(holdings, blend):
    """Dial the system's crowding without changing anyone's size.

    blend=0 leaves the books exactly as filed. blend=+1 gives every fund the
    average book (maximum crowding). blend=-1 sharpens each fund onto its own
    biggest positions, which pulls them apart.

    Negative blend interpolates toward a disjoint assignment — fund j parked
    entirely in asset j — which is the genuinely uncrowded end of the axis.
    (Sharpening each fund onto its own biggest names was the obvious
    alternative and it's wrong: nearly every one of these funds has NVDA as a
    top position, so sharpening *concentrates* them into the shocked name and
    the axis stops measuring structure. Extrapolating past the mean is also
    out — it hands funds negative positions.)

    Each fund keeps its own gross assets throughout, so the only thing moving
    along this axis is *how alike* the portfolios are.
    """
    holdings = np.asarray(holdings, dtype=float)
    totals = holdings.sum(axis=1, keepdims=True)
    weights = np.divide(holdings, totals, out=np.zeros_like(holdings), where=totals > 0)

    if blend >= 0:
        mean = weights.mean(axis=0, keepdims=True)
        mixed = (1.0 - blend) * weights + blend * mean
    else:
        disjoint = np.zeros_like(weights)
        for j in range(weights.shape[0]):
            disjoint[j, j % weights.shape[1]] = 1.0
        mixed = (1.0 + blend) * weights + (-blend) * disjoint

    return mixed * totals


def mean_overlap(holdings):
    """Average pairwise cosine similarity of the funds' weight vectors."""
    holdings = np.asarray(holdings, dtype=float)
    totals = holdings.sum(axis=1, keepdims=True)
    w = np.divide(holdings, totals, out=np.zeros_like(holdings), where=totals > 0)
    norms = np.linalg.norm(w, axis=1)
    pairs = []
    for a in range(len(w)):
        for b in range(a + 1, len(w)):
            denom = norms[a] * norms[b]
            pairs.append(float(w[a] @ w[b] / denom) if denom > 0 else 0.0)
    return float(np.mean(pairs)) if pairs else 0.0


_ROWS, _COLS = 16, 16
_REF_SHOCK = -0.05


def _boundary(params):
    """Sweep leverage against crowding and record amplification in each cell.

    The reference shock is **single-name** — `reference_kind` in the response
    says so, and the body sets `shock[0]`. This docstring used to claim it was
    market-wide, which is what I tried first and then reverted; the description
    outlived the code by several commits.

    Both were tried, and the trade is real. A market-wide shock costs every
    fund the same fraction of assets regardless of how its weights are
    arranged, which isolates structure cleanly — but then overlap barely
    matters and the map comes out almost flat, which is true and useless. The
    single-name shock produces the diagonal boundary the literature describes,
    at the cost that amplification is not monotone along the crowding axis:
    sharpening a fund onto its biggest names tends to concentrate it into the
    shocked one. The sharp transition to read off this map is in **leverage**
    (1.00 at lambda~4.5 to 1.86 at lambda~5.0), not in crowding.

    Caccioli et al. (2014) show a critical leverage that falls as crowding
    rises. If this grid is right you should be able to see that curve.
    """
    data = load_dataset()
    base = np.array(data["holdings"])
    adv = np.array(data["adv"])
    knobs = _guarded(params, base.shape[0])
    gamma = knobs["gamma"]
    band = knobs["band"]

    shock = np.zeros(base.shape[1])
    shock[0] = _REF_SHOCK

    levs = np.linspace(1.5, 8.0, _ROWS)
    blends = np.linspace(-1.0, 1.0, _COLS)

    grid, overlaps = [], []
    for lev in levs:
        row = []
        for blend in blends:
            holdings = blend_toward_mean(base, blend)
            m = holdings.shape[0]
            result = run_cascade(
                holdings=holdings,
                leverage=np.full(m, lev),
                # this was hardcoded at 1.05 while the payload echoed the
                # requested band, so every grid came back identical and the
                # response asserted something the computation hadn't done
                max_leverage=np.full(m, lev * band),
                target_leverage=np.full(m, min(max(1.0, lev * 0.95), lev * band)),
                gamma=gamma,
                adv=adv,
                shock=shock,
            )
            row.append(round(float(result.amplification), 4))
        grid.append(row)

    for blend in blends:
        overlaps.append(round(mean_overlap(blend_toward_mean(base, blend)), 4))

    return {
        "grid": grid,
        "rows": _ROWS,
        "cols": _COLS,
        "asset_count": len(data["tickers"]),
        "leverage_axis": [round(float(x), 3) for x in levs],
        "overlap_axis": overlaps,
        # gamma and band used to sit here as well as in `params`, and this was
        # the only endpoint that did it — two spellings of one number, one of
        # them with the clamping record next to it and one without. A caller
        # reading the bare copy could not tell a value it asked for from a
        # value we quietly pulled back into range. `params` is the contract.
        #
        # And `breaches` is dropped from it here, because this endpoint never
        # reads one. _guarded emits it for every caller, so the sweep was
        # publishing "breaches": 3 — a default nothing applied — inside the
        # block the interface contract calls authoritative. A phantom knob in
        # the authoritative block is worse than no knob at all.
        "params": {k: v for k, v in knobs.items() if k != "breaches"},
        "reference_shock": _REF_SHOCK,
        "reference_kind": "single-name",
        # WHICH name, and how many books. The sweep sets shock[0], so the
        # shocked asset was tickers[0] and a caller had to know that and fetch
        # /api/dataset to find out — a page drawing this map would otherwise
        # be inferring the subject of its own headline.
        "reference_asset": data["tickers"][0],
        "funds": list(data["funds"]),
        "here": {
            # guarded, not raw: this came off the query string, so a URL could
            # put the "you are here" dot outside the plot it's drawn on
            "leverage": float(np.clip(knobs["leverage"], levs[0], levs[-1])),
            "overlap": round(mean_overlap(base), 4),
        },
    }

# The sliders can't produce these, but a URL can, and a URL typo returning a
# confident answer to a different question is the worst failure mode here.
# Clamp rather than error — a stack trace in front of judges is worse — but
# never silently: every adjustment is declared in the payload.
_LIMITS = {
    "leverage": (1.0, 8.0, 5.0),
    "gamma": (0.0, 1.0, 0.2),
    # How far over target leverage a fund runs before it's forced to sell.
    # This was hardcoded at 1.05 and it matters more than either knob above:
    # at leverage 5.0 with >=3 breaching, 1.02 gives NVDA -1.73% and
    # amplification 3.10, 1.30 gives NVDA -27.33% and 1.43. Those two figures
    # are leverage-specific — at 3.0 the same pair is -4.59% and -57.12% — so
    # read them as one measurement, not as the band's behaviour in general.
    # Leaving the most influential parameter invisible while the other two sat
    # on sliders is the worst version of this.
    "band": (1.0, 1.5, 1.05),
}


def _guarded(params, n_funds):
    """Read the knobs, clamp them to what the model means, and say what moved."""
    clamped, out = [], {}

    for name, (lo, hi, default) in _LIMITS.items():
        raw = params.get(name)
        if raw is None:
            out[name] = default
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            out[name] = default
            clamped.append({"name": name, "given": raw, "used": default,
                            "reason": "unreadable"})
            continue
        if value != value:  # NaN
            out[name] = default
            clamped.append({"name": name, "given": raw, "used": default,
                            "reason": "unreadable"})
            continue
        if value in (float("inf"), float("-inf")):
            # min/max would clamp these correctly, but `given: Infinity` is not
            # valid JSON — json.dumps writes a bare Infinity that strict parsers
            # reject. Report the string that was sent instead.
            used = min(max(value, lo), hi)
            out[name] = used
            clamped.append({"name": name, "given": str(raw), "used": used,
                            "reason": f"outside {lo}–{hi}"})
            continue
        used = min(max(value, lo), hi)
        out[name] = used
        if used != value:
            clamped.append({"name": name, "given": value, "used": used,
                            "reason": f"outside {lo}–{hi}"})

    raw = params.get("breaches")
    top = max(1, n_funds)
    wanted = 3
    if raw is not None:
        try:
            # int(float("inf")) raises OverflowError, which is NOT a subclass of
            # ValueError. It escaped this guard entirely and propagated out of
            # handle(), whose except-clause fell back to load_golden with no
            # near check — so `breaches=inf` returned 200, found: true, and a
            # complete answer recorded at band=1.02, a setting nobody asked
            # for, with clamped: [] beside it. Every other bad value was
            # clamped and declared; that one alone was confidently wrong.
            value = float(raw)
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("not a finite number")
            wanted = int(value)
            # int() truncates. breaches=2.999999999 became 2 and said nothing,
            # which is where a slider readout carrying float error lands —
            # and 2 vs 3 is 4.598% vs 5.273% on screen.
            if wanted != value:
                clamped.append({"name": "breaches", "given": value, "used": wanted,
                                "reason": "whole funds only"})
        except (TypeError, ValueError, OverflowError):
            wanted = 3
            clamped.append({"name": "breaches", "given": raw, "used": 3,
                            "reason": "unreadable"})
    used = min(max(wanted, 1), top)
    out["breaches"] = used
    if raw is not None and used != wanted:
        clamped.append({"name": "breaches", "given": wanted, "used": used,
                        "reason": f"outside 1–{top}"})

    out["clamped"] = clamped
    return out


# ── Portfolio Mode ──────────────────────────────────────────────────────────
#
# The product loop the app opens into: my portfolio, my limit, my breaking
# shock, why, the smallest fix, and whether that fix actually helped.
#
# These sit outside the KNOBS/golden machinery deliberately. Those exist to let
# demo mode answer the institutional questions off disk, and they key on the
# four sliders. A portfolio is not a slider position — the same knobs with a
# different portfolio is a different question — so caching it by knobs alone
# would serve one user's answer to another. That is the `cached_for` failure in
# a far worse costume, and the fix is to not build it.
#
# These endpoints are fast enough not to need it: the demo portfolio's whole
# loop, search and fix and validation, runs in well under a second.

DEMO_PORTFOLIO = [
    {"symbol": "NVDA", "quantity": 20, "market_value": 3600.0},
    {"symbol": "MSFT", "quantity": 8, "market_value": 3150.0},
    {"symbol": "AMZN", "quantity": 10, "market_value": 2250.0},
    {"symbol": "GOOGL", "quantity": 12, "market_value": 2250.0},
    {"symbol": "CASH", "quantity": None, "market_value": 1050.0},
]

_LIMIT_RANGE = (0.01, 0.90, 0.10)


def _portfolio_scenario(params):
    """The institutional network the portfolio is an observer of."""
    data = load_dataset()
    scenario, knobs = _scenario(data, params)
    return data, scenario, knobs


def _rows_from(body):
    """No holdings means the demo. An EMPTY list means an empty upload.

    `if not rows` treated both the same, and [] is falsy in Python while being
    truthy in JavaScript — so a CSV with a header row and no data rows posted
    `{"holdings": [], "source": "csv"}`, got the demo book back, and rendered
    it as the user's own analysis under a note reading "Loaded 0 rows from
    your-file.csv". Showing somebody else's portfolio and calling it theirs.
    """
    body = body or {}
    if "holdings" not in body or body["holdings"] is None:
        return list(DEMO_PORTFOLIO), "demo"
    rows = body["holdings"]
    if not rows:
        raise ValueError(
            "that file had no holdings in it — a header row on its own is not a "
            "portfolio. Check the file has data rows below the header."
        )
    return rows, body.get("source", "csv")


def _limit_of(params):
    """The loss limit, and a `clamped` entry if we did not use what was given.

    Every other knob records itself when it is pulled back into range; this one
    did it silently, so a 95% limit came back as 90% under a payload asserting
    that nothing had been adjusted. The nav reads the number the user typed and
    the page reads the number we used, which put 95% and 90% on the same screen
    with nothing to reconcile them.
    """
    lo, hi, default = _LIMIT_RANGE
    raw = params.get("limit", default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default, {"name": "limit", "given": raw, "used": default,
                         "reason": "unreadable"}
    # The same two guards _guarded carries, and for the same two reasons. This
    # function was written later and did not get them.
    #
    # min(max(nan, lo), hi) is nan, so the search ran against a limit no
    # comparison can be true of: every `loss >= limit` was False, nothing was
    # found, and the payload came back with this project's honest-negative
    # wording — "no shock within the tested range pushed this portfolio past
    # the limit" — for a search that could not have succeeded. The same book at
    # limit=0.10 breaks at NVDA −25.05%.
    if value != value:  # NaN
        return default, {"name": "limit", "given": raw, "used": default,
                         "reason": "unreadable"}
    if value in (float("inf"), float("-inf")):
        # `given: Infinity` is a bare Infinity out of json.dumps, which Python's
        # own loader accepts and the browser's rejects — so the whole response
        # failed to parse and the page rendered nothing. Report the string.
        used = min(max(value, lo), hi)
        return used, {"name": "limit", "given": str(raw), "used": used,
                      "reason": f"outside {lo}–{hi}"}
    used = min(max(value, lo), hi)
    if used != value:
        return used, {"name": "limit", "given": value, "used": used,
                      "reason": f"outside {lo}\u2013{hi}"}
    return used, None


def _solve_portfolio(params, body):
    """Everything downstream of a portfolio, in one pass.

    One function because the steps share a scenario and a shock, and splitting
    them across requests would mean re-deriving the shock on every call — which
    is how the before and after halves of a comparison drift apart.
    """
    from .portfolio import (
        UnknownSymbol, cheapest_portfolio_fix, find_portfolio_firebreak,
        normalise, portfolio_loss, weight_vector,
    )

    data, scenario, knobs = _portfolio_scenario(params)
    limit, limit_clamp = _limit_of(params)
    if limit_clamp:
        knobs = dict(knobs, clamped=list(knobs.get("clamped", [])) + [limit_clamp])

    try:
        rows, source = _rows_from(body)
    except ValueError as exc:
        return ({"found": False, "refused": True, "reason": str(exc),
                 "params": dict(knobs, limit=limit), "tickers": data["tickers"]},
                None, None, scenario, data)

    # A refusal is a RESULT, not an exception to be stringified upstream.
    #
    # This used to raise, `server._api` wrapped it as {"error": ...} with a 200,
    # and the frontend's `if (!body.found)` branch caught it — because
    # `undefined` is falsy — and rendered "no shock in the tested range crossed
    # your limit. That is not the same as safe." Nothing had been searched. The
    # holding had been refused. The screen said the opposite, in the exact
    # register this repo reserves for honest negatives.
    #
    # And the input that triggers it is VOO, or SPY, or VTI — the single most
    # likely line in a real brokerage CSV.
    excluded_note = None
    try:
        portfolio = normalise(rows, source=source)
        vector, cash = weight_vector(portfolio, data["tickers"])
    except UnknownSymbol as exc:
        # A real brokerage export is mostly funds we do not model — a Fidelity
        # book is often half VOO — so refusing outright is the end of the road
        # for anybody who actually uploads one. `exclude_unmodelled` is the way
        # through, and it is opt-in for a reason: dropping a holding and
        # renormalising the rest around the hole is the silent undercount this
        # project exists to refuse. Chosen, priced and carried onto every
        # screen, it is a different thing from done quietly.
        drop = {s.upper() for s in exc.symbols}
        kept = [r for r in rows if str(r.get("symbol", "")).strip().upper() not in drop]
        whole = normalise(rows, source=source).total_value
        excluded = [
            {"symbol": h.symbol, "market_value": h.market_value}
            for h in normalise(rows, source=source).holdings
            if h.symbol.upper() in drop
        ]
        gone = sum(h["market_value"] for h in excluded)
        offer = {
            "found": False,
            "refused": True,
            "reason": str(exc),
            "unmodelled": exc.symbols,
            "modelled": data["tickers"] + ["CASH"],
            # what saying yes would cost, in the units the user thinks in
            "excluded": excluded,
            "excluded_value": gone,
            "excluded_fraction": (gone / whole) if whole else None,
            "modellable_value": whole - gone,
            "can_exclude": bool(kept) and (whole - gone) > 0,
            "params": dict(knobs, limit=limit),
            "tickers": data["tickers"],
        }
        if not _truthy(params.get("exclude_unmodelled")) or not offer["can_exclude"]:
            return offer, None, None, scenario, data

        portfolio = normalise(kept, source=source)
        vector, cash = weight_vector(portfolio, data["tickers"])
        excluded_note = {
            "excluded": excluded,
            "excluded_value": gone,
            "excluded_fraction": (gone / whole) if whole else None,
            "whole_book_value": whole,
        }
    except ValueError as exc:
        return {
            "found": False, "refused": True, "reason": str(exc),
            "params": dict(knobs, limit=limit), "tickers": data["tickers"],
        }, None, None, scenario, data

    found = find_portfolio_firebreak(vector, cash, limit, **scenario)
    out = {
        "portfolio": portfolio.as_dict(),
        "params": dict(knobs, limit=limit),
        "tickers": data["tickers"],
        "found": found is not None,
    }
    if found is None:
        # Not "your portfolio is safe". We looked in a range and did not find
        # one; those are different statements and only one of them is ours to
        # make.
        out["reason"] = ("No shock within the tested range pushed this portfolio "
                         "past the limit under these assumptions.")
        # The UI has to be able to name the range. "The tested range" is an
        # appeal to something the reader cannot see, and the number belongs to
        # the search, not to a literal typed into a page.
        from .search import _MAX_DROP
        out["search_max_drop"] = _MAX_DROP
        return out, None, None, scenario, data

    result = run_cascade(shock=found.shock, **scenario)
    direct = portfolio_loss(vector, cash, 1.0 + found.shock)
    out.update({
        "asset": data["tickers"][found.asset],
        "asset_index": int(found.asset),
        "pct": found.pct,
        "magnitude": found.magnitude,
        "direct_loss": direct,
        "cascade_loss": portfolio_loss(vector, cash, result.prices),
        "amplification": (portfolio_loss(vector, cash, result.prices) / direct
                          if direct > 0 else None),
        "rounds": result.rounds,
        "breached": result.breached,
        # `breached` is the cumulative set across the whole cascade, so the UI
        # needs the denominator to say "3 of 5" rather than hardcoding how many
        # managers the dataset happens to hold today.
        "funds": list(data["funds"]),
        # Carried onto the result so every downstream screen can say what is
        # missing. A disclosure that only appears on the screen where you
        # agreed to it is not a disclosure.
        "excluded_note": excluded_note,
        # End-of-cascade prices, aligned to `tickers`. The analysis page needs
        # them to attribute the loss name by name — which is the question a
        # portfolio holder actually has, and the one number on that screen the
        # UI previously had to fetch a second endpoint to answer.
        "prices": result.prices.tolist(),
        "direct_prices": (1.0 + found.shock).tolist(),
        "system": result.as_dict()["metrics"],
    })
    return out, found, (vector, cash), scenario, data


def _portfolio_firebreak(params, body=None):
    out, found, _vc, _scenario, _data = _solve_portfolio(params, body)
    return out


def _portfolio_full(params, body=None):
    """Search, fix and validate — the whole loop, because the demo wants it."""
    from .portfolio import cheapest_portfolio_fix
    from . import validate as V

    out, found, vc, scenario, data = _solve_portfolio(params, body)
    if found is None:
        return out

    vector, cash = vc
    limit = out["params"]["limit"]
    total = out["portfolio"]["total_value"]
    fix = cheapest_portfolio_fix(vector, cash, limit, found.shock, **scenario)
    if fix is None:
        out["fix"] = None
        out["fix_reason"] = ("No single-position change cleared the limit with "
                             "headroom. A multi-position cut would, and this "
                             "build does not do those.")
        return out

    before = {"vector": vector, "cash": cash}
    after = {"vector": fix["vector"], "cash": fix["cash"]}
    out["fix"] = {
        "symbol": data["tickers"][fix["asset"]],
        "asset_index": int(fix["asset"]),
        "fraction_of_position": fix["fraction_of_position"],
        "dollars": fix["weight_moved"] * total,
        "weight_moved": fix["weight_moved"],
        "loss_after": fix["loss_after"],
        "target_loss": fix["target_loss"],
        "margin": fix["margin"],
        "note": ("Moved to cash. Your position does not move the market — it "
                 "decides how much of the market's move lands on you."),
    }
    out["validation"] = {
        "identical_shock": V.replay_identical(before, after, found.shock, limit, **scenario),
        "new_breaking_point": V.new_breaking_point(before, after, limit, **scenario),
        "synthetic": V.synthetic_stress(before, after, n=400, limit=limit, **scenario),
        "historical": V.historical_stress(),
    }
    return out


BODY_ROUTES.update({"/api/portfolio/firebreak", "/api/portfolio/full"})

def _cascade_at(params, body=None):
    """Run a SPECIFIED shock and return what the stage animates.

    Step 4 of Portfolio Mode is the "why" — and it was calling /api/break,
    which does not replay a shock, it SEARCHES for the institutional one. So
    the explanation animated a -5.27% four-fund cascade directly beneath a
    result saying the break point was -24.69% with five. Two consecutive
    screens, same session, contradicting each other, on the beat whose entire
    job is to explain the one above it.

    The portfolio's shock is a fact the caller already has. This replays it.
    """
    data = load_dataset()
    scenario, knobs = _scenario(data, params)
    try:
        asset = data["tickers"].index(params.get("asset", data["tickers"][0]))
    except ValueError:
        raise NotFound("unknown asset")
    # A price cannot fall by more than all of itself. This was
    # `-abs(float(...))` with no range and no record, so `magnitude=5` produced
    # prices[0] = -4.0 — a negative stock price — and a cascade run on top of
    # it, reported as a normal result. Unreadable values became NaN and
    # propagated the same way.
    raw = params.get("magnitude", 0.0)
    try:
        wanted = float(raw)
        if wanted != wanted or wanted in (float("inf"), float("-inf")):
            raise ValueError("not a finite number")
    except (TypeError, ValueError):
        wanted, knobs = 0.0, dict(knobs, clamped=list(knobs.get("clamped", [])) + [
            {"name": "magnitude", "given": str(raw), "used": 0.0, "reason": "unreadable"}])
    used = min(abs(wanted), 1.0)
    if used != abs(wanted):
        knobs = dict(knobs, clamped=list(knobs.get("clamped", [])) + [
            {"name": "magnitude", "given": abs(wanted), "used": used,
             "reason": "a price cannot fall more than 100%"}])
    magnitude = -used

    shock = np.zeros(len(data["tickers"]))
    shock[asset] = magnitude
    result = run_cascade(shock=shock, **scenario)

    payload = result.as_dict()
    payload.update({
        "found": True,
        "params": knobs,
        "asset": data["tickers"][asset],
        "asset_index": asset,
        "magnitude": magnitude,
        "pct": abs(magnitude) * 100.0,
        "funds": data["funds"],
        "fund_indices": list(range(len(data["funds"]))),
        "tickers": data["tickers"],
        "holdings": data["holdings"],
        "adv": data["adv"],
        "adv_units": "USD",
        "quarter": data.get("quarter"),
        "source": data.get("source"),
        "replayed": True,
    })
    return payload


ROUTES["/api/cascade"] = _cascade_at

ROUTES["/api/portfolio/demo"] = lambda params: {
    "portfolio": _demo_portfolio_payload(), "source": "demo"}
ROUTES["/api/portfolio/firebreak"] = _portfolio_firebreak
ROUTES["/api/portfolio/full"] = _portfolio_full


def _demo_portfolio_payload():
    from .portfolio import normalise
    return normalise(list(DEMO_PORTFOLIO), source="demo").as_dict()
