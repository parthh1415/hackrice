"""The other half of the product: given a shock that breaks us, what's the
smallest change that makes us survive it?

Scans one (fund, asset) position at a time and finds the least reduction that
clears the failure condition. Cost is expressed as a fraction of the system's
gross assets — the thing a PM actually has to justify to somebody.

Deliberately one-dimensional. A multi-position optimiser would be a better
answer and a worse demo: nobody can act on "shave 3% off eleven things".
"""

from dataclasses import dataclass

import numpy as np

from .engine import run_cascade

# Coarse pass picks the POSITION; a bisection then finds the depth. The grid
# alone used to be the whole answer, and at 5% steps every scenario we ever
# recorded came back at exactly 0.050 — the floor. So "cut GOOGL by 5%" really
# meant "by at most 5%, we didn't look closer": the same fake precision the
# shock search was tightened to 5e-5 to avoid, sitting in the beat the product
# is named after. The old comment here said finer steps were "slow for no
# gain". The gain is the answer.
_STEPS = 20
_DEPTH_TOLERANCE = 0.002   # 0.2% of a position; ~9 extra cascade runs


@dataclass
class Fix:
    fund: int
    asset: int
    reduction: float  # fraction of that position to sell, 0-1
    cost: float       # fraction of the system's gross assets given up

    def apply(self, holdings):
        patched = np.asarray(holdings, dtype=float).copy()
        patched[self.fund, self.asset] *= 1.0 - self.reduction
        return patched

    def as_dict(self, funds=None, tickers=None):
        return {
            "fund": funds[self.fund] if funds else self.fund,
            "asset": tickers[self.asset] if tickers else self.asset,
            "fund_index": self.fund,
            "asset_index": self.asset,
            "reduction": self.reduction,
            "cost": self.cost,
        }


def find_cheapest_fix(condition, holdings, shock, **cascade_kwargs):
    """Least-cost single-position cut that survives `shock`, or None.

    For each position we walk the reduction up from 5% and stop at the first
    level that clears the condition — anything smaller already failed, so
    there's no point checking further. Then we keep whichever position's
    successful cut was cheapest overall.
    """
    holdings = np.asarray(holdings, dtype=float)
    total = holdings.sum()
    if total <= 0:
        return None

    if not condition(run_cascade(holdings=holdings, shock=shock, **cascade_kwargs)):
        return None  # nothing to fix

    best = None
    n_funds, n_assets = holdings.shape

    for fund in range(n_funds):
        for asset in range(n_assets):
            position = holdings[fund, asset]
            if position <= 0:
                continue

            for step in range(1, _STEPS + 1):
                reduction = step / _STEPS
                cost = position * reduction / total
                if best is not None and cost >= best.cost:
                    break  # already more expensive than what we have

                works = not condition(run_cascade(
                    holdings=Fix(fund, asset, reduction, cost).apply(holdings),
                    shock=shock, **cascade_kwargs))
                if not works:
                    continue

                # This depth works and the one below it didn't, so the true
                # minimum is inside that step. Bisect for it rather than
                # reporting the grid point and calling it the answer.
                lo, hi = reduction - 1.0 / _STEPS, reduction
                while hi - lo > _DEPTH_TOLERANCE:
                    mid = (lo + hi) / 2.0
                    if condition(run_cascade(
                        holdings=Fix(fund, asset, mid, 0.0).apply(holdings),
                        shock=shock, **cascade_kwargs)):
                        lo = mid
                    else:
                        hi = mid

                candidate = Fix(fund, asset, hi, position * hi / total)
                if best is None or candidate.cost < best.cost:
                    best = candidate
                break

    return best
