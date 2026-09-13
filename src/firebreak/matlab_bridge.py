"""MATLAB for the stabilisation solve, with an honest fallback.

Why MATLAB here and nowhere else: the objective is a *simulation*. You
cannot differentiate it, the feasible set is defined by whether a cascade
crosses a discrete failure condition, and breach events make the landscape
piecewise constant. That is the problem class `patternsearch` exists for.
The forward cascade, by contrast, is straight linear algebra and has no
business being anywhere but Python where it is already tested.

Three paths, tried in order, and the UI is told which one actually ran:

  matlab          MATLAB Engine API for Python — needs a local install
  matlab-offline  a result file produced by running matlab/stabilise.m,
                  including from MATLAB Online, which needs no install
  python          the built-in search in stabilise.py

Never reports 'matlab' unless MATLAB genuinely produced the numbers.
"""

import hashlib
import json
import re
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
MATLAB_DIR = ROOT / "matlab"
CACHE = ROOT / "data" / "cache"
SPEC_PATH = CACHE / "solve_spec.json"
OUT_PATH = CACHE / "solve_out.json"

_FINGERPRINT_KEYS = (
    "holdings", "leverage", "max_leverage", "target_leverage",
    "gamma", "adv", "shock", "breaches",
)


TOKENS = ROOT / "web" / "tokens.css"

_PALETTE_KEYS = ("paper", "paper-raised", "paper-sunk", "ink", "ink-mid",
                 "ink-faint", "rule", "loss",
                 "ramp-0", "ramp-1", "ramp-2", "ramp-3", "ramp-4", "ramp-5")


def read_palette(path=TOKENS):
    """The app's palette, as 0-1 RGB triples, for the MATLAB figures.

    The figures are exported on the product's own colours so they read as part
    of the page rather than as a screenshot from another program. That only
    holds if there is ONE definition of those colours, and tokens.css is it —
    §7 of DESIGN.md says no raw hex outside that file, and a hex triple copied
    into a .m script is exactly the copy that survives a repaint and turns a
    figure into a bright slab on a dark page.

    Returns {} if the file is unreadable, and the MATLAB side keeps its own
    fallback, because a missing palette should cost you a nice-looking figure
    and not the solve.
    """
    try:
        text = pathlib.Path(path).read_text()
    except Exception:
        return {}
    out = {}
    for key in _PALETTE_KEYS:
        m = re.search(rf"--{re.escape(key)}\s*:\s*#([0-9A-Fa-f]{{6}})\s*;", text)
        if m:
            h = m.group(1)
            out[key.replace("-", "_")] = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return out


def _spec_fingerprint(spec):
    """Stable hash of everything the solve depends on.

    An offline MATLAB result is only usable if the parameters have not moved
    since it was produced — otherwise the UI shows a confident answer to a
    question nobody asked.
    """
    payload = json.dumps(
        {k: spec[k] for k in _FINGERPRINT_KEYS}, sort_keys=True, default=float
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def write_spec(spec, path=SPEC_PATH):
    """Write the spec MATLAB reads, and leave the file alone if it hasn't moved.

    Not rewriting an identical spec is load-bearing, not tidiness: the file's
    mtime is how `_try_offline` knows when the question last changed, and
    every request rewrites this file. Touch it each time and an offline result
    solved thirty seconds ago looks older than the question it answers.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(spec)
    payload["fingerprint"] = _spec_fingerprint(spec)
    # Deliberately after the fingerprint: the palette is for the figure, not
    # for the solve. Folding it in would invalidate a perfectly good MATLAB
    # result every time somebody changed a colour.
    palette = read_palette()
    if palette:
        payload["palette"] = palette
    text = json.dumps(payload, indent=2, default=float)
    if not (path.exists() and path.read_text() == text):
        path.write_text(text)
    return path


def _try_engine(spec):
    """MATLAB Engine API. Absent on most machines; that is fine."""
    try:
        import matlab.engine  # noqa: F401
    except Exception:
        return None
    try:
        import matlab.engine

        started = time.perf_counter()
        eng = matlab.engine.start_matlab()
        eng.addpath(str(MATLAB_DIR), nargout=0)
        spec_file = write_spec(spec)
        result = eng.stabilise(str(spec_file), str(OUT_PATH), nargout=1)
        eng.quit()
        result = {k: result[k] for k in result.keys()}
        result["engine"] = "matlab"
        result["solve_ms"] = round((time.perf_counter() - started) * 1000)
        return result
    except Exception:
        return None


def _try_offline(spec):
    """A result file produced by running matlab/stabilise.m by hand.

    This is the MATLAB Online path: no install, you paste the spec in,
    run it, download the result. The fingerprint check is what stops a
    stale file being presented as a live answer.
    """
    if not OUT_PATH.exists() or not SPEC_PATH.exists():
        return None
    try:
        fingerprint = _spec_fingerprint(spec)
        written = json.loads(SPEC_PATH.read_text())
        if written.get("fingerprint") != fingerprint:
            return None

        result = json.loads(OUT_PATH.read_text())
        if not isinstance(result, dict):
            return None
        # stabilise.m echoes the spec fingerprint into its result, so this is
        # an exact match and it wins over the mtime heuristic. The mtime path
        # below still covers results produced by an older stabilise.m.
        stamped = result.get("fingerprint")
        if stamped is not None and stamped != fingerprint:
            return None
        if stamped is None and OUT_PATH.stat().st_mtime < SPEC_PATH.stat().st_mtime:
            # the spec file was rewritten after this result was produced, which
            # only happens when the question changed. comparing the spec file
            # to the request is no help — we wrote it from that request a
            # moment ago, so it agrees with itself no matter how stale the
            # result next to it is.
            return None

        if not _usable(result, spec):
            return None
        result["engine"] = "matlab-offline"
        return result
    except Exception:
        return None


def _usable(result, spec):
    """Does this dict describe a fix that exists and actually works?

    patternsearch can exit on an infeasible point and still hand back an `x`,
    and the offline path is a file a human downloaded and dropped in a folder.
    So nothing that comes back here is trusted until it has been re-simulated
    in the Python engine that everything else in this project is measured by.

    Untrusted in particular: a negative index, which numpy would quietly read
    as "the last fund"; a reduction outside [0, 1], which turns the position
    negative rather than smaller; and NaN, which propagates into every number
    in the response and leaves the frontend with a body it cannot parse.
    """
    import numpy as np

    from .engine import run_cascade
    from .search import at_least_n_breaches
    from .stabilise import Fix

    try:
        holdings = np.array(spec["holdings"], dtype=float)
        n_funds, n_assets = holdings.shape
        fund, asset = int(result["fund_index"]), int(result["asset_index"])
        reduction, cost = float(result["reduction"]), float(result["cost"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return False

    if not (0 <= fund < n_funds and 0 <= asset < n_assets):
        return False
    if not (np.isfinite(reduction) and 0.0 <= reduction <= 1.0):
        return False
    if not (np.isfinite(cost) and cost >= 0.0):
        return False

    try:
        after = run_cascade(
            holdings=Fix(fund, asset, reduction, cost).apply(holdings),
            shock=np.array(spec["shock"], dtype=float),
            leverage=np.array(spec["leverage"], dtype=float),
            max_leverage=np.array(spec["max_leverage"], dtype=float),
            target_leverage=np.array(spec["target_leverage"], dtype=float),
            gamma=float(spec["gamma"]),
            adv=np.array(spec["adv"], dtype=float),
        )
    except Exception:
        return False

    # a "firebreak" the fire walks straight through is worse than admitting
    # we haven't got one
    return not at_least_n_breaches(int(spec["breaches"]))(after)


def _python_fallback(spec):
    import numpy as np

    from .search import at_least_n_breaches
    from .stabilise import find_cheapest_fix

    started = time.perf_counter()
    holdings = np.array(spec["holdings"], dtype=float)

    # the readout puts this next to MATLAB's funccount, so it has to be the
    # number of cascades we ran, not the size of the space we could have
    # searched. the early exit in find_cheapest_fix means those differ by a
    # lot, and quoting the bigger one flatters the wrong solver.
    solves = 0
    fails = at_least_n_breaches(int(spec["breaches"]))

    def condition(result):
        nonlocal solves
        solves += 1
        return fails(result)

    fix = find_cheapest_fix(
        condition=condition,
        holdings=holdings,
        shock=np.array(spec["shock"], dtype=float),
        leverage=np.array(spec["leverage"], dtype=float),
        max_leverage=np.array(spec["max_leverage"], dtype=float),
        target_leverage=np.array(spec["target_leverage"], dtype=float),
        gamma=float(spec["gamma"]),
        adv=np.array(spec["adv"], dtype=float),
    )
    if fix is None:
        return None
    return {
        "fund_index": fix.fund,
        "asset_index": fix.asset,
        "reduction": fix.reduction,
        "cost": fix.cost,
        "solver": "exhaustive position scan",
        "evaluations": solves,
        "exit_flag": 1,
        "solve_ms": round((time.perf_counter() - started) * 1000),
        "engine": "python",
    }


def solve_stabilisation(spec):
    """First path that produces a fix which survives re-simulation.

    A MATLAB result that doesn't hold up isn't an error to surface — it's a
    reason to try the next path, which is the whole point of having three.
    """
    for attempt in (_try_engine, _try_offline, _python_fallback):
        result = attempt(spec)
        if result is not None and _usable(result, spec):
            return result
    return None


def engine_label(result):
    """What the solver readout shows. Never inflates what ran."""
    if result is None:
        return "—", "no feasible single-position fix"
    engine = result.get("engine", "python")
    solver = result.get("solver", "?")
    if engine == "matlab":
        return f"MATLAB · {solver}", "live engine"
    if engine == "matlab-offline":
        return f"MATLAB · {solver}", "solved offline, fingerprint matched"
    return f"SciPy-free Python · {solver}", "MATLAB not available on this machine"
