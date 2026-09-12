"""Balance sheets and the deleveraging cascade.

Prices are normalised to 1.0 at t0, so the holdings matrix you pass in can be
straight dollar values off a 13F and the units work out.
"""

from dataclasses import dataclass

import numpy as np

_TINY = 1e-12
_FLOOR = 1e-6  # prices can sag but never go negative


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

    def assets(self):
        return self.units @ self.prices

    def equity(self):
        return self.assets() - self.debt

    def leverage(self):
        return list(self.assets() / self.equity())

    def shock(self, returns):
        """Move prices. Debt doesn't care, so the whole hit lands on equity."""
        self.prices = self.prices * (1.0 + np.asarray(returns, dtype=float))

    def deleverage(self, max_leverage, target_leverage):
        """Anyone over their limit raises cash and pays down debt.

        The sale itself is equity-neutral: assets and debt fall by the same
        dollar amount. What actually costs you money is the price move it
        causes for everyone else holding the same names.

        Solving (A - q)/E = target for q, and using E = A/L:
            q = A - target*E = A*(L - target)/L

        Returns dollars sold per asset, summed across funds.
        """
        max_leverage = np.asarray(max_leverage, dtype=float)
        target_leverage = np.asarray(target_leverage, dtype=float)

        assets = self.assets()
        equity = self.equity()
        solvent = equity > _TINY
        lev = np.divide(assets, equity, out=np.full_like(assets, np.inf), where=solvent)

        breached = solvent & (lev > max_leverage + _TINY)
        if not breached.any():
            return np.zeros_like(self.prices)

        raise_ = np.zeros_like(assets)
        raise_[breached] = assets[breached] * (
            (lev[breached] - target_leverage[breached]) / lev[breached]
        )
        # can't sell more than you own
        raise_ = np.minimum(raise_, assets)

        value = self.units * self.prices
        weights = np.divide(
            value, assets[:, None], out=np.zeros_like(value), where=assets[:, None] > _TINY
        )
        sold = raise_[:, None] * weights

        self.units -= np.divide(
            sold, self.prices, out=np.zeros_like(sold), where=self.prices > _TINY
        )
        self.debt -= raise_
        return sold.sum(axis=0)


@dataclass
class CascadeResult:
    """What came out of one run. `trajectory` is what the UI animates."""

    rounds: int
    breached: list
    prices: np.ndarray
    shock_loss: float
    final_loss: float
    amplification: float
    trajectory: list

    def as_dict(self):
        return {
            "rounds": self.rounds,
            "breached": self.breached,
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
    max_rounds=12,
):
    """Shock the prices, then let forced selling chase itself until it settles.

    Every round: work out who's over their limit, make them sell, push the
    prices of whatever they sold, go again. Usually dies out in two or three
    rounds. If it doesn't, that's the interesting case.
    """
    book = Book(holdings, leverage)
    equity_start = book.equity().sum()

    book.shock(shock)
    # baseline for amplification: the damage before anyone is forced to act.
    # has to be equity-denominated, same as final_loss, or the ratio just
    # reports the leverage ratio back at you.
    equity_after_shock = book.equity().sum()

    adv = np.asarray(adv, dtype=float)
    breached = set()
    trajectory = [_snapshot(book, 0, [])]
    rounds = 0

    for step in range(1, max_rounds + 1):
        hit = _over_limit(book, max_leverage)
        if not hit:
            break
        rounds = step
        breached.update(hit)

        sold = book.deleverage(max_leverage, target_leverage)
        book.prices = book.prices * np.maximum(1.0 - gamma * sold / adv, _FLOOR)
        trajectory.append(_snapshot(book, step, hit))

    equity_end = book.equity().sum()
    shock_loss = (equity_start - equity_after_shock) / equity_start
    final_loss = (equity_start - equity_end) / equity_start
    amplification = final_loss / shock_loss if abs(shock_loss) > _TINY else 1.0

    return CascadeResult(
        rounds=rounds,
        breached=sorted(breached),
        prices=book.prices.copy(),
        shock_loss=float(shock_loss),
        final_loss=float(final_loss),
        amplification=float(amplification),
        trajectory=trajectory,
    )


def _over_limit(book, max_leverage):
    equity = book.equity()
    assets = book.assets()
    solvent = equity > _TINY
    lev = np.divide(assets, equity, out=np.full_like(assets, np.inf), where=solvent)
    return [
        j
        for j in range(len(assets))
        if solvent[j] and lev[j] > np.asarray(max_leverage, dtype=float)[j] + _TINY
    ]


def _snapshot(book, step, hit):
    return {
        "t": step,
        "prices": book.prices.tolist(),
        "leverage": book.leverage(),
        "equity": book.equity().tolist(),
        "breached": list(hit),
    }
