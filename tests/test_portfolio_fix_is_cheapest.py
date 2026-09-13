"""The recommendation has to be the cheapest one, not the first one that works.

`tests/test_fix_is_cheapest_off_the_demo_path.py` exists because the
institutional stabiliser once returned a fix 303x too expensive, invisible at
the demo settings because the cheapest position happened to be the first cell
the scan visited. There was no portfolio counterpart, and a review agent
showed the same hole: replacing

    if best is None or moved < best[0]

with

    if best is None

— take the first feasible position rather than the cheapest — left all 282
tests green.

It is inert at the demo point for exactly the old reason: NVDA is both index 0
and the cheapest, so the two answers coincide. Off the demo path it bites, and
not rarely. The agent swept 11,763 random (portfolio, leverage, gamma, limit)
combinations and found 570 where the first feasible position was not the
cheapest — about one in twenty.

The case below is theirs, reproduced: the first feasible cut is 8.48x the
price of the cheapest one.
"""

import json
import pathlib
from types import SimpleNamespace

import numpy as np
import pytest

from minima.engine import run_cascade
from minima.portfolio import (
    FIX_MARGIN, cheapest_portfolio_fix, cut_to_cash, find_portfolio_breakpoint,
    normalise, portfolio_loss, weight_vector,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data" / "cache" / "dataset.json").read_text())
TICKERS = DATA["tickers"]


def scenario(leverage, gamma, band=1.05):
    m = len(DATA["funds"])
    return dict(
        holdings=np.array(DATA["holdings"]),
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * band),
        target_leverage=np.full(m, min(max(1.0, leverage * 0.95), leverage * band)),
        gamma=gamma,
        adv=np.array(DATA["adv"]),
    )


def brute_force_cheapest(vector, cash, limit, prices, margin=FIX_MARGIN):
    """Every position, bisected independently. Slow, obvious, and the answer."""
    target = limit * (1.0 - margin)
    best = None
    for asset in range(len(vector)):
        if vector[asset] <= 0:
            continue
        full, full_cash = cut_to_cash(vector, cash, asset, 1.0)
        if portfolio_loss(full, full_cash, prices) >= target:
            continue
        lo, hi = 0.0, 1.0
        for _ in range(50):
            mid = (lo + hi) / 2.0
            vec, csh = cut_to_cash(vector, cash, asset, mid)
            if portfolio_loss(vec, csh, prices) >= target:
                lo = mid
            else:
                hi = mid
        moved = vector[asset] * hi
        if best is None or moved < best[0]:
            best = (moved, asset, hi)
    return best


# Settings where the first feasible position is NOT the cheapest, so a scan
# that stopped at the first one would be caught.
OFF_PATH = [
    ({"TSLA": 3000, "JPM": 500, "AVGO": 3000, "AAPL": 200, "CASH": 3000}, 7.0, 0.3, 0.10),
    ({"AMD": 4000, "META": 2000, "AAPL": 2000, "CASH": 2000}, 6.0, 0.2, 0.10),
    ({"AAPL": 2500, "MSFT": 2500, "AMZN": 2500, "GOOGL": 2500}, 5.0, 0.4, 0.05),
]


@pytest.mark.parametrize("holdings,leverage,gamma,limit", OFF_PATH)
def test_the_fix_is_the_cheapest_position_not_the_first_workable_one(
        holdings, leverage, gamma, limit):
    portfolio = normalise([{"symbol": s, "market_value": float(v)}
                           for s, v in holdings.items()])
    vector, cash = weight_vector(portfolio, TICKERS)
    kw = scenario(leverage, gamma)

    found = find_portfolio_breakpoint(vector, cash, limit, **kw)
    if found is None:
        pytest.skip("these settings do not break this portfolio")

    prices = run_cascade(shock=found.shock, **kw).prices
    truth = brute_force_cheapest(vector, cash, limit, prices)
    assert truth is not None

    fix = cheapest_portfolio_fix(vector, cash, limit, found.shock, **kw)
    assert fix is not None

    cost, asset, _ = truth
    assert fix["asset"] == asset, (
        f"recommended {TICKERS[fix['asset']]} at {fix['weight_moved'] / cost:.2f}x the "
        f"price of {TICKERS[asset]}, which also clears the limit"
    )
    assert fix["weight_moved"] <= cost * 1.01


def test_the_first_feasible_position_really_is_not_always_the_cheapest(monkeypatch):
    """A controlled path keeps the selection check stable as holdings grow.

    AAPL is intentionally first in the portfolio and feasible, but its 10%
    loss means selling 60% of the whole portfolio. MSFT falls 70%, so selling
    only 8.57% clears the same limit. A first-feasible implementation returns
    AAPL; the real solver must inspect both and return MSFT.
    """
    portfolio = normalise([
        {"symbol": "AAPL", "market_value": 8000.0},
        {"symbol": "MSFT", "market_value": 1000.0},
        {"symbol": "CASH", "market_value": 1000.0},
    ])
    vector, cash = weight_vector(portfolio, TICKERS)
    prices = np.ones(len(TICKERS))
    prices[TICKERS.index("AAPL")] = 0.90
    prices[TICKERS.index("MSFT")] = 0.30
    monkeypatch.setattr(
        "minima.engine.run_cascade",
        lambda **_kwargs: SimpleNamespace(prices=prices),
    )

    limit = 0.10
    truth = brute_force_cheapest(vector, cash, limit, prices)
    fix = cheapest_portfolio_fix(
        vector, cash, limit, np.zeros(len(TICKERS)), holdings=np.empty((0, 0)),
    )

    assert truth is not None and fix is not None
    assert TICKERS[truth[1]] == "MSFT"
    assert TICKERS[fix["asset"]] == "MSFT"
    assert fix["weight_moved"] == pytest.approx(truth[0], rel=1e-9)
