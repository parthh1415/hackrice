"""Reverse stress testing: don't pick a scenario, go looking for one.

You say what counts as failure. This goes and finds the smallest single-asset
shock that gets you there. Regulators (PRA, EBA) make banks do this by hand;
nobody does it interactively for overlapping portfolios.
"""

from dataclasses import dataclass

import numpy as np

from .engine import run_cascade

# don't bother searching past this — a 60% single-name drop isn't a stress
# test any more, it's a different company
_MAX_DROP = 0.60
_COARSE_STEP = 0.01


@dataclass
class WeakestShock:
    asset: int
    magnitude: float          # negative, e.g. -0.042
    shock: np.ndarray         # full vector, zeros except at `asset`

    @property
    def pct(self):
        return abs(self.magnitude) * 100.0


def at_least_n_breaches(n):
    return lambda result: len(result.breached) >= n


def system_loss_above(fraction):
    return lambda result: result.final_loss > fraction


def amplification_above(factor):
    return lambda result: result.amplification > factor


def find_weakest_shock(condition, holdings, tolerance=0.0005, **cascade_kwargs):
    """Smallest single-asset drop that trips `condition`, or None.

    Damage is monotone in shock size but it's a *step* function — breaches are
    discrete, so there are flat stretches where bisection has nothing to bite
    on. So: coarse scan to find the step, then bisect inside that bracket.
    """
    n_assets = np.asarray(holdings).shape[1]
    best = None

    for asset in range(n_assets):
        magnitude = _critical_drop_for(
            asset, n_assets, condition, holdings, tolerance, cascade_kwargs
        )
        if magnitude is None:
            continue
        if best is None or abs(magnitude) < abs(best.magnitude):
            best = WeakestShock(
                asset=asset,
                magnitude=magnitude,
                shock=_vector(asset, n_assets, magnitude),
            )

    return best


def _critical_drop_for(asset, n_assets, condition, holdings, tolerance, cascade_kwargs):
    def fails(drop):
        result = run_cascade(
            holdings=holdings, shock=_vector(asset, n_assets, drop), **cascade_kwargs
        )
        return condition(result)

    # coarse pass: walk down until something gives
    lo = 0.0  # known safe
    hi = None  # known to fail
    steps = int(_MAX_DROP / _COARSE_STEP)
    for k in range(1, steps + 1):
        drop = -k * _COARSE_STEP
        if fails(drop):
            hi = drop
            break
        lo = drop

    if hi is None:
        return None

    # refine inside the bracket
    while abs(hi - lo) > tolerance:
        mid = (lo + hi) / 2.0
        if fails(mid):
            hi = mid
        else:
            lo = mid

    return hi


def _vector(asset, n_assets, magnitude):
    shock = np.zeros(n_assets)
    shock[asset] = magnitude
    return shock
