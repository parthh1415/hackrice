"""Balance sheets and the deleveraging cascade.

Prices are normalised to 1.0 at t0, so the holdings matrix you pass in can be
straight dollar values off a 13F and the units work out.
"""

import numpy as np

_TINY = 1e-12


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
