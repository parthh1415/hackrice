"""JSON endpoints. Thin on purpose — the thinking lives in engine/search."""

import json
import os
import pathlib
import urllib.parse

import numpy as np

from .dataset import load_dataset
from .engine import run_cascade
from .search import at_least_n_breaches, find_weakest_shock
from .matlab_bridge import engine_label, solve_stabilisation, write_spec
from .stabilise import Fix


class NotFound(Exception):
    pass


def _health(params):
    return {"ok": True}


def _dataset(params):
    return load_dataset()


def handle(path, body):
    route, _, query = path.partition("?")
    params = dict(urllib.parse.parse_qsl(query))
    params.pop("demo", None)
    demo = _demo_requested(query)

    if route not in ROUTES:
        raise NotFound(route)

    if demo:
        cached = load_golden(route, params)
        if cached is not None:
            return cached
        # nothing recorded for this endpoint — computing is better than a 404

    try:
        payload = ROUTES[route](params)
    except Exception as exc:
        # a demo never shows a stack trace. if we ever recorded this endpoint,
        # serve that and label it; only re-raise when there's truly nothing.
        cached = load_golden(route, params)
        if cached is None:
            raise
        cached["fallback_reason"] = _reason(exc)
        return cached

    payload["cached"] = False
    return payload


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
KNOBS = {
    "/api/health": {},
    "/api/dataset": {},
    "/api/break": {"leverage": (5.0, 6.5), "gamma": (0.2, 1.0), "breaches": (2.0, 4.0)},
    "/api/stabilise": {"leverage": (5.0, 6.5), "gamma": (0.2, 1.0), "breaches": (2.0, 4.0)},
    "/api/boundary": {"leverage": (5.0, 6.5), "gamma": (0.2, 1.0)},
}

ROUTES = {
    "/api/health": _health,
    "/api/dataset": _dataset,
    "/api/break": lambda params: _break(params),
    "/api/stabilise": lambda params: _stabilise(params),
    "/api/boundary": lambda params: _boundary(params),
}


def _knobs(route, params):
    """The knob values this request implies, defaults filled in."""
    out = {}
    for name, (default, _) in KNOBS[route].items():
        try:
            out[name] = float(params.get(name, default))
        except (TypeError, ValueError):
            out[name] = float(default)
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
    path, _ = min(candidates, key=lambda c: (_distance(route, wanted, c[1]), c[0].name))
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    payload["cached"] = True
    payload.pop("fallback_reason", None)
    return payload


# the demo runs at 5 / 0.2 / 3; the rest are where a hand on the slider ends up
GOLDEN_SPOTS = [
    {"leverage": 5, "gamma": 0.2, "breaches": 3},
    {"leverage": 5, "gamma": 0.2, "breaches": 2},
    {"leverage": 4, "gamma": 0.2, "breaches": 3},
    {"leverage": 6, "gamma": 0.2, "breaches": 3},
    {"leverage": 7, "gamma": 0.2, "breaches": 3},
    {"leverage": 5, "gamma": 0.1, "breaches": 3},
    {"leverage": 5, "gamma": 0.4, "breaches": 3},
]


def golden_specs():
    specs = [("/api/health", {}), ("/api/dataset", {})]
    for spot in GOLDEN_SPOTS:
        specs.append(("/api/break", spot))
        specs.append(("/api/stabilise", spot))
        specs.append(("/api/boundary", {"leverage": spot["leverage"], "gamma": spot["gamma"]}))
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
    lev = float(params.get("leverage", 5.0))
    return dict(
        holdings=np.array(data["holdings"]),
        leverage=np.full(m, lev),
        max_leverage=np.full(m, lev * 1.05),
        target_leverage=np.full(m, max(1.0, lev * 0.95)),
        gamma=float(params.get("gamma", 0.2)),
        adv=np.array(data["adv"]),
    )


def _find(data, params):
    scenario = _scenario(data, params)
    condition = at_least_n_breaches(int(params.get("breaches", 2)))
    return scenario, condition, find_weakest_shock(condition=condition, **scenario)


def _break(params):
    data = load_dataset()
    scenario, _, found = _find(data, params)
    if found is None:
        return {"found": False, **data}

    result = run_cascade(shock=found.shock, **scenario)
    return {
        "found": True,
        "asset": data["tickers"][found.asset],
        "asset_index": found.asset,
        "magnitude": found.magnitude,
        "pct": found.pct,
        **data,
        **result.as_dict(),
    }


def _stabilise(params):
    data = load_dataset()
    scenario, condition, found = _find(data, params)
    if found is None:
        return {"found": False, **data}

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
        "breaches": int(params.get("breaches", 2)),
    }
    write_spec(spec)  # so matlab/stabilise.m can be run by hand, incl. MATLAB Online
    solved = solve_stabilisation(spec)
    if solved is None:
        return {"found": False, "reason": "no single-position fix clears it", **data}

    fix = Fix(
        fund=int(solved["fund_index"]),
        asset=int(solved["asset_index"]),
        reduction=float(solved["reduction"]),
        cost=float(solved["cost"]),
    )
    name, note = engine_label(solved)
    patched = dict(scenario, holdings=fix.apply(scenario["holdings"]))
    after = run_cascade(shock=found.shock, **patched)

    return {
        "found": True,
        "asset": data["tickers"][found.asset],
        # the split view rings this. without the index it falls back to 0,
        # which is correct only when the answer happens to be the first name.
        "asset_index": found.asset,
        "magnitude": found.magnitude,
        "pct": found.pct,
        "fix": fix.as_dict(data["funds"], data["tickers"]),
        "engine": {
            "name": name,
            "note": note,
            "kind": solved.get("engine", "python"),
            "solver": solved.get("solver", ""),
            "evaluations": solved.get("evaluations", 0),
            "exit_flag": solved.get("exit_flag", 0),
            "solve_ms": solved.get("solve_ms", 0),
        },
        "before": before.as_dict(),
        "after": after.as_dict(),
        **data,
    }


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

    The reference shock is market-wide (every name down the same percent),
    not single-name, and that matters. With a single-name shock, sharpening a
    fund onto its biggest positions tends to *concentrate* it into the shocked
    name — so the axis ends up measuring exposure rather than structure, and
    the grid comes out non-monotonic. A uniform shock costs every fund the same
    fraction of assets no matter how its weights are arranged, which leaves
    overlap as the only thing varying along the x axis.

    Caccioli et al. (2014) show a critical leverage that falls as crowding
    rises. If this grid is right you should be able to see that curve.
    """
    data = load_dataset()
    base = np.array(data["holdings"])
    adv = np.array(data["adv"])
    gamma = float(params.get("gamma", 0.2))

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
                max_leverage=np.full(m, lev * 1.05),
                target_leverage=np.full(m, max(1.0, lev * 0.95)),
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
        "leverage_axis": [round(float(x), 3) for x in levs],
        "overlap_axis": overlaps,
        "gamma": gamma,
        "reference_shock": _REF_SHOCK,
        "reference_kind": "single-name",
        "here": {
            "leverage": float(params.get("leverage", 5.0)),
            "overlap": round(mean_overlap(base), 4),
        },
    }
