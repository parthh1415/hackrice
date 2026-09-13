"""What the search actually promises.

The docstring used to claim breach count is monotone in shock size, "verified
across 12,200 runs". That was true of the data it was verified against and
then the holdings matrix changed underneath it (GOOGL share classes, 13F
amendments) and nobody re-ran it. On the corrected books there is exactly one
violation in the same 12,200-run sweep: lambda=3.0, gamma=0.5, MSFT at -32%
gives 4 breaches where -31% gives 5, with nobody insolvent.

So monotonicity is NOT the property to lean on. The property that actually
matters — and the one the product claims — is that the answer is the smallest
shock on the search grid that trips the condition. That holds whether or not
the damage function is monotone above it, because the scan walks up from zero
and stops at the first crossing.
"""

import json
import pathlib

import numpy as np

from minima.engine import run_cascade
from minima.search import at_least_n_breaches, find_weakest_shock

REAL = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache" / "dataset.json"


def scenario(leverage=5.0, gamma=0.2):
    data = json.loads(REAL.read_text())
    m = len(data["funds"])
    return data, dict(
        holdings=np.array(data["holdings"]),
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * 1.05),
        target_leverage=np.full(m, max(1.0, leverage * 0.95)),
        gamma=gamma,
        adv=np.array(data["adv"]),
    )


def test_the_answer_is_the_smallest_crossing_on_the_grid():
    """No coarser shock anywhere trips the condition. This is the real claim."""
    data, kw = scenario()
    condition = at_least_n_breaches(3)

    found = find_weakest_shock(condition=condition, **kw)
    assert found is not None

    n = len(data["tickers"])
    step = 0.01
    ceiling = int(abs(found.magnitude) / step)  # every whole step strictly below it
    for asset in range(n):
        for k in range(1, ceiling + 1):
            shock = np.zeros(n)
            shock[asset] = -k * step
            result = run_cascade(shock=shock, **kw)
            assert not condition(result), (
                f"{data['tickers'][asset]} at -{k}% already trips the condition, "
                f"but the search reported {found.pct:.2f}% on {data['tickers'][found.asset]}"
            )


def test_a_configuration_already_in_breach_reports_zero_not_a_sliver():
    """Leverage above the ceiling breaches before anyone shocks anything."""
    _, kw = scenario(leverage=5.0)
    kw["max_leverage"] = np.full(len(kw["leverage"]), 4.0)  # already over
    kw["target_leverage"] = np.full(len(kw["leverage"]), 3.8)

    found = find_weakest_shock(condition=at_least_n_breaches(1), **kw)

    assert found is not None
    assert found.magnitude == 0.0


def test_breach_count_is_monotone_at_the_demo_calibration():
    """Monotone where the demo lives, which is what the sliders default to.

    Deliberately NOT claimed for the whole parameter space — see the module
    docstring for the counterexample.
    """
    data, kw = scenario(leverage=5.0, gamma=0.2)

    for asset in range(len(data["tickers"])):
        worst = -1
        for pct in range(0, 61):
            shock = np.zeros(len(data["tickers"]))
            shock[asset] = -pct / 100
            count = len(run_cascade(shock=shock, **kw).breached)
            assert count >= worst, f"{data['tickers'][asset]} fell at -{pct}%"
            worst = count
