"""A user's portfolio, and what it means for one to break.

The engine was always general. `find_weakest_shock` takes any
`condition(CascadeResult) -> bool`, and a finished cascade carries the price
vector it ended on. So "this person's portfolio crossed the loss they told us
they would not tolerate" is just another predicate — the same shape as
`at_least_n_breaches`, asked of a different observer. Nothing in engine.py,
search.py or stabilise.py changes to support any of this.

OBSERVER, NOT PARTICIPANT. The portfolio watches the institutional cascade and
takes the price damage. It does not join the network, because a retail account
does not move markets and pretending otherwise would be the most flattering
possible lie this app could tell.

That has a consequence which has to be said out loud wherever a fix is shown:
**cutting a position does not change the cascade.** The institutions deleverage
identically either way. What changes is how much of that price path lands on
you. "Your position doesn't move the market. It decides how much of the
market's move lands on you."
"""

from dataclasses import dataclass, field

import numpy as np

CASH = "CASH"


class UnknownSymbol(Exception):
    """A holding we cannot model, surfaced rather than silently dropped.

    Dropping it would renormalise every other weight and quietly understate the
    portfolio's concentration — the same shape as the CUSIP bug that started
    this project's long education in silent undercounts.
    """

    def __init__(self, symbols, known):
        self.symbols = list(symbols)
        super().__init__(
            f"not in the modelled universe: {', '.join(sorted(self.symbols))}. "
            f"Modelled names are {', '.join(known)} (and {CASH})."
        )


@dataclass
class Holding:
    symbol: str
    market_value: float
    quantity: float = None
    source: str = "demo"

    def as_dict(self):
        return {
            "symbol": self.symbol,
            "market_value": self.market_value,
            "quantity": self.quantity,
            "source": self.source,
        }


@dataclass
class Portfolio:
    holdings: list = field(default_factory=list)
    name: str = "Portfolio"
    source: str = "demo"

    @property
    def total_value(self):
        return sum(h.market_value for h in self.holdings)

    def weights(self):
        total = self.total_value
        if total <= 0:
            return {}
        return {h.symbol: h.market_value / total for h in self.holdings}

    def as_dict(self):
        total = self.total_value
        return {
            "name": self.name,
            "source": self.source,
            "total_value": total,
            "holdings": [
                dict(h.as_dict(), weight=(h.market_value / total if total else 0.0))
                for h in self.holdings
            ],
        }


def normalise(rows, source="csv"):
    """One path in, whatever the source. Every ingestion route calls this.

    Duplicate symbols are summed rather than last-write-wins, because a
    brokerage that reports two lots of the same stock is not reporting two
    different opinions about how much you own.
    """
    merged, order = {}, []
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        value = row.get("market_value")
        qty = row.get("quantity")
        if value is None and qty is not None and row.get("price") is not None:
            value = float(qty) * float(row["price"])
        if value is None:
            raise ValueError(
                f"{symbol}: need market_value, or quantity and price. "
                "A holding with no value cannot be weighted."
            )
        value = float(value)
        if symbol not in merged:
            order.append(symbol)
            merged[symbol] = {"value": 0.0, "qty": 0.0, "has_qty": False}
        merged[symbol]["value"] += value
        if qty is not None:
            merged[symbol]["qty"] += float(qty)
            merged[symbol]["has_qty"] = True

    return Portfolio(
        holdings=[
            Holding(
                symbol=s,
                market_value=merged[s]["value"],
                quantity=merged[s]["qty"] if merged[s]["has_qty"] else None,
                source=source,
            )
            for s in order
        ],
        source=source,
    )


def weight_vector(portfolio, tickers):
    """Weights aligned to the engine's ticker order, plus the cash weight.

    Returns (vector, cash_weight). The vector and the cash weight sum to 1, so
    a price path applied to the vector plus cash held at par is the whole
    portfolio — no residual, nothing renormalised behind your back.
    """
    weights = portfolio.weights()
    known = set(tickers) | {CASH}
    unknown = [s for s in weights if s not in known]
    if unknown:
        raise UnknownSymbol(unknown, tickers)

    vector = np.array([weights.get(t, 0.0) for t in tickers], dtype=float)
    return vector, float(weights.get(CASH, 0.0))


def portfolio_loss(vector, cash, prices):
    """Fractional loss under a price vector. Prices start at 1.0 and fall.

    Cash is held at par, so it dilutes the loss exactly as holding cash does.
    """
    prices = np.asarray(prices, dtype=float)
    return float(1.0 - (float(np.dot(vector, prices)) + cash))


def portfolio_loss_above(vector, cash, limit):
    """The predicate. `limit` is a positive fraction: 0.10 means "a 10% loss".

    Note `>=`, not `>`: the user said the loss they would not tolerate, and a
    loss exactly equal to it is not tolerated either.
    """
    return lambda result: portfolio_loss(vector, cash, result.prices) >= limit


# ── the product loop ────────────────────────────────────────────────────────

def find_portfolio_firebreak(vector, cash, limit, holdings, tolerance=None, **cascade_kwargs):
    """Smallest single-name shock that pushes this portfolio past `limit`.

    Composition, not new search code. `find_weakest_shock` already takes an
    arbitrary predicate and already has the precision discipline — testing zero
    first, grid-scanning to a bracket, bisecting to a tolerance finer than the
    digits anybody prints. Handing it a different question does not entitle us
    to a different standard.
    """
    from .search import DEFAULT_TOLERANCE, find_weakest_shock

    return find_weakest_shock(
        condition=portfolio_loss_above(vector, cash, limit),
        holdings=holdings,
        tolerance=DEFAULT_TOLERANCE if tolerance is None else tolerance,
        **cascade_kwargs,
    )


def cut_to_cash(vector, cash, asset, fraction):
    """Move `fraction` of one position into cash. Value is conserved, visibly.

    Cash is a real line in the vector rather than a hole left behind, so the
    weights still sum to one and nothing is quietly renormalised. §18 of the
    brief: do not silently change portfolio value.
    """
    moved = vector[asset] * fraction
    out = np.array(vector, dtype=float)
    out[asset] -= moved
    return out, cash + moved


def cheapest_portfolio_fix(vector, cash, limit, shock, holdings, steps=200, **cascade_kwargs):
    """Smallest single-position cut to cash that survives this exact shock.

    Bisects on depth against a RELATIVE tolerance for the same reason the
    institutional stabiliser does: an absolute one is only right at one order
    of magnitude, and it reported 2.15x the true minimum when the answer moved.

    Returns None when no single cut clears it — which is a real answer, not a
    failure, and the UI says so rather than showing an empty box.
    """
    from .engine import run_cascade

    def survives(vec, csh):
        result = run_cascade(holdings=holdings, shock=shock, **cascade_kwargs)
        return portfolio_loss(vec, csh, result.prices) < limit

    # The cascade does not depend on the user's weights at all — they are an
    # observer — so it is run ONCE and every candidate cut is scored against
    # the same price path. That is not an optimisation, it is the modelling
    # statement: your position does not move the market.
    prices = run_cascade(holdings=holdings, shock=shock, **cascade_kwargs).prices

    best = None
    for asset in range(len(vector)):
        if vector[asset] <= 0:
            continue
        lo, hi = 0.0, 1.0
        full, full_cash = cut_to_cash(vector, cash, asset, 1.0)
        if portfolio_loss(full, full_cash, prices) >= limit:
            continue            # selling all of it still does not save you
        for _ in range(40):
            mid = (lo + hi) / 2.0
            vec, csh = cut_to_cash(vector, cash, asset, mid)
            if portfolio_loss(vec, csh, prices) >= limit:
                lo = mid
            else:
                hi = mid
        moved = vector[asset] * hi
        if best is None or moved < best[0]:
            best = (moved, asset, hi)
    if best is None:
        return None
    moved, asset, fraction = best
    vec, csh = cut_to_cash(vector, cash, asset, fraction)
    return {
        "asset": asset,
        "fraction_of_position": fraction,
        "weight_moved": moved,
        "vector": vec,
        "cash": csh,
    }
