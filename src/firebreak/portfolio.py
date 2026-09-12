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
    if isinstance(rows, dict) or not isinstance(rows, (list, tuple)):
        # A single holding object rather than a list of them reached
        # row.get() as a string and raised AttributeError, which is not on the
        # refusal path — so the endpoint answered 200 with an `error` key and
        # no `found` key at all, and the UI's `if (body.refused)` and
        # `if (!body.found)` branches both fell through.
        raise ValueError(
            "`holdings` must be a list of holdings, not a single one. "
            f"Received {type(rows).__name__}."
        )
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"holding {i + 1} is a {type(row).__name__}, not an object "
                             "with a symbol and a value.")
        symbol = str(row.get("symbol", "")).strip().upper()
        value = row.get("market_value")
        qty = row.get("quantity")
        if not symbol:
            # Skipping a nameless row is right when it is blank padding and
            # wrong when it carries money: $2,000 under no symbol used to
            # vanish and every other weight renormalised around the hole,
            # which is the silent undercount this whole project exists to
            # refuse. Say it rather than absorb it.
            if value in (None, "", 0) and qty in (None, "", 0):
                continue
            raise ValueError(
                f"holding {i + 1} has a value but no symbol, so it cannot be "
                "placed in the modelled universe. Dropping it would renormalise "
                "every other weight around the hole."
            )
        if value is None and qty is not None and row.get("price") is not None:
            value = float(qty) * float(row["price"])
        if value is None:
            raise ValueError(
                f"{symbol}: need market_value, or quantity and price. "
                "A holding with no value cannot be weighted."
            )
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{symbol}: market value {value!r} is not a number.")
        # NaN defeats every comparison silently: `nan > 1e-9` is False, so the
        # sum-to-one check downstream passed and the search reported "no shock
        # in the tested range" for a book that was never scored at all.
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{symbol}: market value {value} is not a finite number.")
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
    total = portfolio.total_value
    if total <= 0:
        # Otherwise weights() returns {} and this function hands back a vector
        # of zeros with zero cash — silently breaking the invariant three lines
        # below that the vector and cash sum to 1. portfolio_loss then computes
        # 1 - 0 = a 100% loss, which is >= every limit, so the search's
        # zero-shock guard fires and the app reports a break point of 0.00%:
        # "your portfolio is destroyed by a shock of nothing at all."
        raise ValueError(
            f"portfolio is worth {total:g}. A portfolio with no value has no "
            "weights, and a loss on nothing is not a number worth showing."
        )

    weights = portfolio.weights()
    known = set(tickers) | {CASH}
    unknown = [s for s in weights if s not in known]
    if unknown:
        raise UnknownSymbol(unknown, tickers)

    vector = np.array([weights.get(t, 0.0) for t in tickers], dtype=float)
    cash = float(weights.get(CASH, 0.0))
    # The invariant this function exists to maintain, checked rather than
    # asserted in a docstring.
    residual = abs(vector.sum() + cash - 1.0)
    if residual > 1e-9:
        raise ValueError(
            f"weights sum to {vector.sum() + cash:.12g}, not 1. Something is "
            "being held that is neither a modelled name nor cash."
        )
    return vector, cash


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


# How much headroom a recommendation has to buy, as a fraction of the limit.
#
# Without this the answer is ZERO, and correctly so: the break point is by
# construction the shock where the loss lands exactly ON the limit, so an
# infinitesimal cut already puts you under it. The first end-to-end run
# returned "reduce NVDA by $0 (0.0% of the position)" and a new break point
# 0.01pp further out. Arithmetically impeccable, worthless as advice, and
# precisely the kind of true-but-useless number this project keeps catching.
#
# So a fix has to buy real distance, and how much is a DECLARED parameter
# rather than a silent one. 0.1 means a 10% limit is defended to a 9% loss.
FIX_MARGIN = 0.1


def cheapest_portfolio_fix(vector, cash, limit, shock, holdings,
                           margin=FIX_MARGIN, **cascade_kwargs):
    """Smallest single-position cut to cash that survives this exact shock
    with `margin` of headroom under the limit.

    Bisects on depth against a RELATIVE tolerance for the same reason the
    institutional stabiliser does: an absolute one is only right at one order
    of magnitude, and it reported 2.15x the true minimum when the answer moved.

    Returns None when no single cut clears it — which is a real answer, not a
    failure, and the UI says so rather than showing an empty box.
    """
    from .engine import run_cascade

    target = limit * (1.0 - margin)

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
        if portfolio_loss(full, full_cash, prices) >= target:
            continue            # selling all of it still does not get you clear
        for _ in range(40):
            mid = (lo + hi) / 2.0
            vec, csh = cut_to_cash(vector, cash, asset, mid)
            if portfolio_loss(vec, csh, prices) >= target:
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
        "limit": limit,
        "margin": margin,
        "target_loss": target,
        "loss_after": portfolio_loss(vec, csh, prices),
    }
