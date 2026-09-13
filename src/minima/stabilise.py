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

# Relative, not absolute. _DEPTH_TOLERANCE used to be a flat 0.002, which reads
# like precision until the answer is smaller than the tolerance: on the demo
# scenario the true minimum is 0.000725, so the bisection halted still holding
# the bracket (0, 0.0015625] and printed the top of it. 2.15x the cheapest cut,
# reported as the cheapest cut. An absolute tolerance can only be right at one
# order of magnitude, and nothing pins the answer to that one.
_DEPTH_RTOL = 0.02         # land within 2% of the true minimum

# The floor exists so the loop terminates: when the true minimum is zero, `hi`
# goes to zero with it and `_DEPTH_RTOL * hi` goes to zero too, so a purely
# relative stop never halts. But a floor stated as a fraction of a position is
# an absolute tolerance wearing a different hat, and it has the same failure —
# it can only be right at one order of magnitude. At 1e-7 it silently took over
# from the 2% guarantee as soon as the answer fell below about 5e-6, which is
# reachable at settings the sliders ship with: lambda=3.0, gamma=0.05,
# band=1.05 reported a cut 5.10% above the true minimum, and lambda=5.0,
# gamma=0.20, band=1.20 reported one 3.28% above. Both inside the stated 2%.
# Erring high is the safe direction, but the claim was false.
#
# So the floor is in DOLLARS now, which is the unit in which "too small to
# care" actually means something. A bracket narrower than a cent of the
# position being cut is not worth another cascade, and for every position in
# this dataset a cent is far below where the relative bound binds — so 2% is
# the guarantee in practice rather than in the comment.
_DEPTH_FLOOR_USD = 0.01


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

    Two passes per position. The coarse one walks the reduction up in 5% steps
    and stops at the first level that clears the condition — anything smaller
    already failed, so there's no point going further. That step is only a
    bracket, though: the true minimum is somewhere inside it, so a bisection
    then narrows it to within _DEPTH_RTOL of the answer before pricing it.
    We keep whichever
    position's cut came out cheapest overall.
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
                # Everything strictly below the previous step has already failed
                # for this position, so that is the floor on what a fix here can
                # possibly cost — and at step 1 the floor is zero, so step 1 can
                # never be pruned. The old test priced the step it was about to
                # TRY, which meant a position got discarded on the strength of a
                # 5% cut it might have cleared with 0.07%. That is unsound in
                # exactly the direction that hides cheap answers, and it got
                # worse every time the bisection made `best.cost` smaller.
                floor_cost = position * (step - 1) / _STEPS / total
                if best is not None and floor_cost >= best.cost:
                    break  # cannot beat what we have, however shallow the cut

                works = not condition(run_cascade(
                    holdings=Fix(fund, asset, reduction, 0.0).apply(holdings),
                    shock=shock, **cascade_kwargs))
                if not works:
                    continue

                # This depth works and the one below it didn't, so the true
                # minimum is inside that step. Bisect for it rather than
                # reporting the grid point and calling it the answer.
                lo, hi = reduction - 1.0 / _STEPS, reduction
                floor = _DEPTH_FLOOR_USD / position if position > 0 else _DEPTH_RTOL
                while hi - lo > max(floor, _DEPTH_RTOL * hi):
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
