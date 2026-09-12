"""Does the recommendation actually make the portfolio more resilient?

A recommendation is not the end of the workflow. The natural next question is
"how do you know", and the honest answer has to be evidence rather than
assertion. Four tests, three of which this repository can ship truthfully.

The language matters and is deliberate throughout: MODELLED, SIMULATED,
REPLAY. A simulation cannot prove the future. "The optimised portfolio stayed
under your limit in 94% of the simulated scenarios" is a fact about our
scenarios; "94% chance you are safe" is a fact about the world, and we do not
have one of those.
"""

import numpy as np

from .engine import run_cascade
from .portfolio import find_portfolio_firebreak, portfolio_loss


def replay_identical(before, after, shock, limit, holdings, **cascade_kwargs):
    """Test 1. The same shock, the same cascade, only the weights differ.

    One cascade, two scorings. Running it twice would invite the two halves to
    drift apart under some future edit, and "only the portfolio changed" is the
    entire claim of this comparison — so it is enforced by construction rather
    than promised in a caption.
    """
    result = run_cascade(holdings=holdings, shock=shock, **cascade_kwargs)
    before_loss = portfolio_loss(before["vector"], before["cash"], result.prices)
    after_loss = portfolio_loss(after["vector"], after["cash"], result.prices)
    return {
        "shock_pct": float(abs(shock.min()) * 100.0),
        "shock_asset": int(np.argmin(shock)),
        "limit": limit,
        "before_loss": before_loss,
        "after_loss": after_loss,
        "before_breaks": before_loss >= limit,
        "after_breaks": after_loss >= limit,
        "amplification": result.amplification,
        "note": "Same shock. Same assumptions. Only the portfolio changed.",
    }


def new_breaking_point(before, after, limit, holdings, **cascade_kwargs):
    """Test 2. Re-run the reverse search against the adjusted weights.

    Recomputed, never derived. The temptation is to infer the new break point
    from the old one and the size of the cut; that would be a formula dressed
    as a measurement, and the number is only worth anything because the same
    search that found the first one found this one too.
    """
    was = find_portfolio_firebreak(before["vector"], before["cash"], limit,
                                   holdings=holdings, **cascade_kwargs)
    now = find_portfolio_firebreak(after["vector"], after["cash"], limit,
                                   holdings=holdings, **cascade_kwargs)
    out = {
        "before_pct": was.pct if was else None,
        "before_asset": int(was.asset) if was else None,
        "after_pct": now.pct if now else None,
        "after_asset": int(now.asset) if now else None,
        "after_unbreakable": now is None,
    }
    if was and now:
        out["moved_pp"] = now.pct - was.pct
        out["moved_ratio"] = now.pct / was.pct if was.pct else None
    return out


def synthetic_stress(before, after, holdings, n=1000, seed=20260912,
                     limit=None, shock_range=(0.01, 0.30), **cascade_kwargs):
    """Test 3. N sampled shocks through the same engine, both portfolios scored
    on IDENTICAL draws.

    Identical draws is the whole design. Scoring the two portfolios against
    separately sampled scenarios would compare them on different weather and
    call the difference an improvement. Seeded, so the demo reproduces.

    Each draw shocks one name — the same single-name family the product is
    about — at a magnitude from a fixed range. Deliberately simple: a more
    elaborate generator would be more impressive and less checkable, and the
    number it produced would be harder to defend than it is worth.
    """
    rng = np.random.default_rng(seed)
    n_assets = holdings.shape[1]
    assets = rng.integers(0, n_assets, size=n)
    # One place, so the range we report is the range we drew from. It used to
    # be a literal [1.0, 30.0] fifteen lines below a separate 0.01/0.30 here;
    # widening the draw left the payload describing the old one, and nothing
    # in the suite could tell.
    lo, hi = shock_range
    sizes = rng.uniform(lo, hi, size=n)

    before_losses, after_losses, amps = [], [], []
    for asset, size in zip(assets, sizes):
        shock = np.zeros(n_assets)
        shock[asset] = -float(size)
        result = run_cascade(holdings=holdings, shock=shock, **cascade_kwargs)
        before_losses.append(portfolio_loss(before["vector"], before["cash"], result.prices))
        after_losses.append(portfolio_loss(after["vector"], after["cash"], result.prices))
        amps.append(result.amplification)

    return {
        "scenarios": int(n),
        "seed": int(seed),
        "shock_range_pct": [lo * 100.0, hi * 100.0],
        # `limit` is threaded through so the survival rate — the headline number
        # this module's own docstring advertises — actually exists. It did not:
        # survival() was called by nothing but its own test, the API never
        # computed a rate, and the UI never rendered one. The worked example
        # described output the product did not produce.
        "limit": (float(limit) if limit is not None else None),
        "before": dict(_summarise(before_losses),
                       survival=(survival(before_losses, limit) if limit else None)),
        "after": dict(_summarise(after_losses),
                      survival=(survival(after_losses, limit) if limit else None)),
        "mean_amplification": float(np.mean(amps)),
        "note": ("Sampled single-name shocks through the same contagion model. "
                 "Both portfolios were scored on identical draws."),
    }


def survival(losses, limit):
    """Share of scenarios in which the portfolio stayed under the limit."""
    losses = np.asarray(losses, dtype=float)
    return float(np.mean(losses < limit))


def _summarise(losses):
    a = np.asarray(losses, dtype=float)
    return {
        "median_loss": float(np.median(a)),
        "p95_loss": float(np.percentile(a, 95)),
        "worst_loss": float(a.max()),
        "mean_loss": float(a.mean()),
    }


def historical_stress(*_args, **_kwargs):
    """Test 4, and the one we cannot honestly ship.

    A historical replay answers "what would these weights have done under this
    return path". We do not ship those return paths — the repository has one
    frozen quarter of 13F holdings and no price history — so there is nothing
    to replay against.

    Building it anyway, against returns invented to look plausible, would be
    the exact failure this project has spent its entire life removing: a
    confident number with nothing underneath it, on the screen that exists to
    show evidence. Missing coverage gets stated, never scored as zero risk.
    """
    return {
        "available": False,
        "reason": ("No price history ships with this build — the dataset is one "
                   "frozen quarter of holdings. Historical replay needs daily "
                   "returns for the modelled names, which would have to be added "
                   "as a committed data file."),
        "what_it_would_answer": ("How these weights would have behaved under a "
                                 "past return path — not whether the same forced "
                                 "selling would recur."),
    }
