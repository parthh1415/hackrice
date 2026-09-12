"""JSON endpoints. Thin on purpose — the thinking lives in engine/search."""

import urllib.parse

import numpy as np

from .dataset import load_dataset
from .engine import run_cascade
from .search import at_least_n_breaches, find_weakest_shock
from .stabilise import find_cheapest_fix


class NotFound(Exception):
    pass


def handle(path, body):
    route, _, query = path.partition("?")
    params = dict(urllib.parse.parse_qsl(query))

    if route == "/api/health":
        return {"ok": True}
    if route == "/api/dataset":
        return load_dataset()
    if route == "/api/break":
        return _break(params)
    if route == "/api/stabilise":
        return _stabilise(params)

    raise NotFound(route)


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
        target_leverage=np.full(m, lev * 0.95),
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
    fix = find_cheapest_fix(condition=condition, shock=found.shock, **scenario)
    if fix is None:
        return {"found": False, "reason": "no single-position fix clears it", **data}

    patched = dict(scenario, holdings=fix.apply(scenario["holdings"]))
    after = run_cascade(shock=found.shock, **patched)

    return {
        "found": True,
        "asset": data["tickers"][found.asset],
        "pct": found.pct,
        "fix": fix.as_dict(data["funds"], data["tickers"]),
        "before": before.as_dict(),
        "after": after.as_dict(),
        **data,
    }
