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
            # A fund holding nothing in the modelled universe has A = 0, so it
            # gets D = 0 and E = 0 — and `0 <= _TINY` put it in with the
            # defaulted. Every frame reported `leverage: null, insolvent: true`
            # for a fund that owes nobody anything, and the units gate in
            # over_limit kept it out of `defaulted` forever, so it stayed
            # insolvent-but-never-defaulting for the whole animation.
            # Insolvency needs a balance sheet to be insolvent on.
            float(np.inf) if equity[j] < -_TINY
            else float(np.inf) if (equity[j] <= _TINY and assets[j] > _TINY)
            else 0.0 if assets[j] <= _TINY
            else float(assets[j] / equity[j])
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
            # Relative, not absolute. With target == ceiling a fund lands
            # exactly on its limit every round and the margin decays to the
            # last bit of a double, where whether it reads 0.0 or 2e-12 is
            # decided by summation order in `units @ prices` — which no amount
            # of agreeing semantics can pin down. An absolute epsilon can only
            # be right at one order of magnitude, and leverage runs from 1.0 to
            # infinity. Same reasoning as _DEPTH_RTOL in stabilise.py.
            and (equity[j] <= _TINY or lev[j] > max_leverage[j] * (1.0 + 1e-12))
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
            # There used to be a `raise_ <= _TINY: continue` here, and cascade.m
            # has never had one. An ABSOLUTE threshold of 1e-12 dollars on a
            # fund that over_limit has already declared to be breaching is a
            # fund told to deleverage and then told to do nothing — and since
            # nothing changed, it breaches again next round, and the loop sits
            # in that fixed point until max_rounds. The two engines then
            # disagreed 24/False against 3/True while every loss figure matched
            # to ten significant figures, and the UI said "did not settle" over
            # a book a millionth of a percent from its ceiling. The
            # `assets[j] <= _TINY` guard above already covers the division.
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
    # The other three parameters that quietly produce nonsense. Only
    # target_leverage was checked, and the reason given for checking it — the
    # model stops meaning anything outside the range — applies to all of them.
    #
    # adv is the one that reaches a payload. It is divided by and never
    # validated: for an asset no fund holds the numerator is 0.0 too, so the
    # impact multiplier is 0/0 = NaN. NaN spreads through prices, equity and
    # leverage, every comparison against it is False, so over_limit finds
    # nobody, the loop exits at round one and `converged` comes out True — with
    # final_loss and amplification NaN, which json.dumps writes bare and the
    # browser's parser rejects. One typo in data/universe.json away.
    adv = np.asarray(adv, dtype=float)
    if np.any(~np.isfinite(adv)) or np.any(adv <= 0.0):
        raise ValueError(
            "every adv must be a positive, finite number; a zero divides into "
            "the price impact and hands back NaN prices that report as a clean "
            "converged cascade"
        )
    if not np.isfinite(gamma) or gamma < 0.0:
        raise ValueError("gamma must be >= 0; a negative one makes forced "
                         "selling repair the market")
    if np.any(np.asarray(leverage, dtype=float) <= 0.0):
        raise ValueError("leverage must be > 0; at zero the implied debt is -inf")
    shock = np.asarray(shock, dtype=float)
    if np.any(shock < -1.0):
        # _FLOOR keeps the IMPACT multiplier off zero and was never applied to
        # the shock, so a -150% move set a price to -0.513 — and the comment on
        # _FLOOR promises prices never go negative. Exactly -100% is allowed:
        # /api/cascade clamps magnitude to 1.0 and a price of 0.0 is a real
        # answer, which tests/test_portfolio_api.py pins.
        raise ValueError("a shock worse than -100% would put a price below zero")

    book = Book(holdings, leverage)
    equity_start = book.equity().sum()

    book.shock(shock)
    # baseline for amplification: damage before anyone is forced to act.
    # equity-denominated, same as final_loss, or the ratio just reports the
    # leverage ratio back at you.
    equity_after_shock = book.equity().sum()

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
        # A NOTE ON GRANULARITY, because this line has a property the module
        # docstring does not mention and a reader would reasonably assume away.
        #
        # Rounds are solver iterations, not time steps — that is the model's
        # claim, and it is nearly but not exactly true of this arithmetic. The
        # impact is multiplicative in THIS round's volume while the execution
        # price below is the exact VWAP of a LINEAR path, and those two agree
        # only in the limit of fine slicing. So the answer depends on how the
        # round's already-decided block is chopped up, which is the one thing
        # the model says carries no meaning.
        #
        # Measured by holding everything else fixed and executing each round's
        # own block in 256 equal slices instead of one: at the demo defaults
        # final_loss moves 0.4pp, and at the slider limits (λ 8, band 1.00,
        # γ 1.0, −60%) it moves 44pp — 17% relative. Prices barely move; almost
        # all of it is in what sellers realise.
        #
        # A single block is the most damaging point of that family, which is the
        # conservative end for a stress test, and it is what every number in
        # this repo was computed with. The slicing-invariant alternative —
        # impact against cumulative volume from a fixed reference — is a
        # different model, not a bug fix, and it would move every recorded
        # answer. Documented rather than changed.
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
