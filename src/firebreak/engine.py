"""Balance sheets and the deleveraging cascade.

Prices are normalised to 1.0 at t0, so the holdings matrix you pass in can be
straight dollar values off a 13F and the units work out.

Two things in here are subtle enough to be worth stating up front.

**Insolvency.** A fund with negative equity has A/E negative, so a naive
`L > L_max` test is false and the most distressed fund in the system silently
stops breaching and stops selling. That made damage non-monotone in shock size
— bigger shock, fewer sellers, less damage — which makes "the smallest shock
that breaks the system" meaningless, because it isn't a threshold at all.
Insolvent funds are treated as infinitely levered, liquidate the whole book,
and get marked defaulted.

**Execution price.** Selling is equity-neutral only if you get book prices for
the entire block, which is exactly what a fire sale doesn't give you. Settled
at book prices, a fund liquidating 100% of its holdings takes *zero* fire-sale
loss — the funds causing the crash come out immune to it. Sales settle at the
round's VWAP instead: midway between the pre- and post-impact price.
"""

from dataclasses import dataclass

import numpy as np

_TINY = 1e-12
_FLOOR = 1e-6  # prices can sag but never reach zero or go negative


class Book:
    """The funds, what they hold, and what they owe.

    Leverage isn't in anybody's public filing, so it's a knob here, not data.
    Given a target L, debt has to be A*(1 - 1/L) for the arithmetic to land:
    E = A - A*(1 - 1/L) = A/L, so A/E = L.
    """

    def __init__(self, holdings, leverage):
        self.units = np.asarray(holdings, dtype=float).copy()
        self.prices = np.ones(self.units.shape[1])
        self.debt = self.assets() * (1.0 - 1.0 / np.asarray(leverage, dtype=float))
        self.defaulted = np.zeros(self.units.shape[0], dtype=bool)

    def assets(self):
        return self.units @ self.prices

    def equity(self):
        return self.assets() - self.debt

    def leverage(self):
        """A/E, with insolvency reported as +inf instead of a negative number.

        The sign flip is the entire reason the first version of this was wrong,
        so it gets handled once, here, rather than at every call site.
        """
        assets, equity = self.assets(), self.equity()
        return [
            float(np.inf) if equity[j] <= _TINY else float(assets[j] / equity[j])
            for j in range(len(assets))
        ]

    def shock(self, returns):
        """Move prices. Debt doesn't care, so the whole hit lands on equity."""
        self.prices = self.prices * (1.0 + np.asarray(returns, dtype=float))

    def over_limit(self, max_leverage):
        """Who has to sell this round. Insolvent counts — it's the worst case."""
        max_leverage = np.asarray(max_leverage, dtype=float)
        equity = self.equity()
        lev = self.leverage()
        return [
            j
            for j in range(len(equity))
            if not self.defaulted[j]
            and self.units[j].sum() > _TINY
            and (equity[j] <= _TINY or lev[j] > max_leverage[j] + _TINY)
        ]

    def plan_sales(self, hit, target_leverage):
        """Units each breached fund intends to sell. Doesn't move anything yet.

        Solving (A - q)/E = target for q, and using E = A/L:
            q = A - target*E = A*(L - target)/L

        An insolvent fund has no target it can reach, so it sells the lot.
        """
        target_leverage = np.asarray(target_leverage, dtype=float)
        assets, equity = self.assets(), self.equity()
        units_out = np.zeros_like(self.units)
        wiped = []

        for j in hit:
            if equity[j] <= _TINY:
                units_out[j] = self.units[j]
                wiped.append(j)
                continue
            if assets[j] <= _TINY:
                continue
            raise_ = float(np.clip(assets[j] - target_leverage[j] * equity[j], 0.0, assets[j]))
            if raise_ <= _TINY:
                continue
            units_out[j] = self.units[j] * (raise_ / assets[j])

        return units_out, wiped

    def settle(self, units_sold, execution_prices):
        """Hand over the units, take the cash, pay down debt.

        Proceeds at `execution_prices`, not book. That's the difference between
        a model where fire-sellers are immune to their own fire sale and one
        where they aren't.
        """
        proceeds = (units_sold * execution_prices).sum(axis=1)
        self.units = np.maximum(self.units - units_sold, 0.0)
        self.debt = self.debt - proceeds
        return proceeds


@dataclass
class CascadeResult:
    """What came out of one run. `trajectory` is what the UI animates."""

    rounds: int
    breached: list
    defaulted: list
    converged: bool
    prices: np.ndarray
    shock_loss: float
    final_loss: float
    amplification: float
    trajectory: list

    def as_dict(self):
        return {
            "rounds": self.rounds,
            "breached": self.breached,
            "defaulted": self.defaulted,
            "converged": self.converged,
            "prices": self.prices.tolist(),
            "metrics": {
                "shock_loss": self.shock_loss,
                "final_loss": self.final_loss,
                "amplification": self.amplification,
            },
            "trajectory": self.trajectory,
        }


def run_cascade(
    holdings,
    leverage,
    max_leverage,
    target_leverage,
    gamma,
    adv,
    shock,
    max_rounds=24,
):
    """Shock the prices, then let forced selling chase itself until it settles.

    Each round: find who's over their limit, plan the sales, price the impact
    those sales cause, settle at the resulting VWAP, go again.
    """
    max_leverage = np.asarray(max_leverage, dtype=float)
    target_leverage = np.asarray(target_leverage, dtype=float)
    if np.any(target_leverage < 1.0) or np.any(target_leverage > max_leverage):
        raise ValueError(
            "need 1 <= target_leverage <= max_leverage; outside that range the "
            "'sale' has negative size and forced selling pushes prices up"
        )

    book = Book(holdings, leverage)
    equity_start = book.equity().sum()

    book.shock(shock)
    # baseline for amplification: damage before anyone is forced to act.
    # equity-denominated, same as final_loss, or the ratio just reports the
    # leverage ratio back at you.
    equity_after_shock = book.equity().sum()

    adv = np.asarray(adv, dtype=float)
    n_funds, n_assets = book.units.shape
    breached, defaulted = set(), set()
    # t=0 is the post-shock, pre-deleverage state, and some funds are already
    # over their limit in it. Reporting nobody there puts a fund on screen at
    # 8.1x against a 6.3 limit with no breach marker on it. Same reading as
    # every later frame — who was over at the start of the round — and it
    # doesn't touch CascadeResult.breached, which the loop still owns.
    trajectory = [
        _snapshot(book, 0, book.over_limit(max_leverage), np.zeros((n_funds, n_assets)))
    ]
    rounds = 0

    for step in range(1, max_rounds + 1):
        hit = book.over_limit(max_leverage)
        if not hit:
            break
        rounds = step
        breached.update(hit)

        units_sold, wiped = book.plan_sales(hit, target_leverage)
        volume = (units_sold * book.prices).sum(axis=0)

        before = book.prices
        after = before * np.maximum(1.0 - gamma * volume / adv, _FLOOR)
        execution = (before + after) / 2.0  # round VWAP
        # dollars actually raised, per fund per asset, at the price they got.
        # the flow animation is width-proportional to this, so it has to be
        # what changed hands rather than what was intended.
        sold_value = units_sold * execution
        book.settle(units_sold, execution)
        book.prices = after

        for j in wiped:
            book.defaulted[j] = True
            defaulted.add(j)

        trajectory.append(_snapshot(book, step, hit, sold_value))

    # a run that spent its last permitted round selling may or may not have
    # finished; the only way to know is to look afterwards. deciding on the way
    # in — "this is the last round and somebody is selling" — marked every run
    # that settled on the final round as divergent, and the UI prints that.
    converged = not book.over_limit(max_leverage)

    equity_end = book.equity().sum()
    shock_loss = (equity_start - equity_after_shock) / equity_start
    final_loss = (equity_start - equity_end) / equity_start
    # A zero denominator makes this ratio undefined, and 1.0 is not a neutral
    # stand-in for undefined — it is the claim that forced selling added
    # nothing to the initial damage. Books already over their limit before
    # anything happens deleverage on their own, so a zero shock can destroy
    # 14% of system equity across five funds and still divide by nothing; the
    # old fallback printed "1.00x" beside it. Say the ratio does not exist.
    if abs(shock_loss) > _TINY:
        amplification = final_loss / shock_loss
    elif abs(final_loss) <= _TINY:
        amplification = 1.0        # nothing happened, so nothing was amplified
    else:
        amplification = None

    return CascadeResult(
        rounds=rounds,
        breached=sorted(breached),
        defaulted=sorted(defaulted),
        converged=converged,
        prices=book.prices.copy(),
        shock_loss=float(shock_loss),
        final_loss=float(final_loss),
        amplification=None if amplification is None else float(amplification),
        trajectory=trajectory,
    )


def _snapshot(book, step, hit, sold_value):
    lev = book.leverage()
    return {
        "t": step,
        "sold": np.asarray(sold_value, dtype=float).tolist(),
        "prices": book.prices.tolist(),
        "leverage": [None if np.isinf(x) else x for x in lev],
        "insolvent": [bool(np.isinf(x)) for x in lev],
        "equity": book.equity().tolist(),
        "breached": list(hit),
        "defaulted": [int(j) for j in np.flatnonzero(book.defaulted)],
    }
