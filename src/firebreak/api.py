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
    if route == "/api/boundary":
        return _boundary(params)

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
