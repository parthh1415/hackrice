"""The Portfolio Mode endpoints, and the caching decision behind them.

The interesting assertion in this file is the one about what these routes do
NOT do: they are not cached by knobs. The institutional routes key their
recordings on four slider positions, which is sound when the sliders are the
whole question. A portfolio is not a slider position — the same knobs with a
different portfolio is a different question — so keying a portfolio answer on
knobs alone would serve one person's result to another. That is the
`cached_for` mismatch in a far worse costume.
"""

import pytest

from firebreak import api


def test_the_demo_portfolio_loads_with_no_body_and_no_network():
    out = api.handle("/api/portfolio/demo", {})

    assert out["portfolio"]["total_value"] == pytest.approx(12300.0)
    assert len(out["portfolio"]["holdings"]) == 5
    assert sum(h["weight"] for h in out["portfolio"]["holdings"]) == pytest.approx(1.0)


def test_the_full_loop_returns_a_break_a_fix_and_evidence():
    out = api.handle("/api/portfolio/full?limit=0.10", {})

    assert out["found"] is True
    assert out["asset"] in out["tickers"]
    assert out["cascade_loss"] >= 0.10
    assert out["fix"]["dollars"] > 0
    v = out["validation"]
    assert v["identical_shock"]["before_breaks"] is True
    assert v["identical_shock"]["after_breaks"] is False
    assert v["new_breaking_point"]["after_pct"] > v["new_breaking_point"]["before_pct"]
    assert v["synthetic"]["scenarios"] > 0
    assert v["historical"]["available"] is False


def test_the_cascade_loss_exceeds_the_direct_loss():
    """Amplification is the product's whole argument. If these were equal the
    contagion model would be contributing nothing."""
    out = api.handle("/api/portfolio/full?limit=0.10", {})

    assert out["cascade_loss"] > out["direct_loss"]
    assert out["amplification"] > 1.0


def test_a_stricter_limit_gives_a_nearer_break_point():
    tight = api.handle("/api/portfolio/full?limit=0.05", {})
    loose = api.handle("/api/portfolio/full?limit=0.15", {})

    assert tight["pct"] <= loose["pct"]


def test_the_limit_is_guarded_like_every_other_input():
    """Out-of-range input is clamped, not obeyed and not crashed on."""
    out = api.handle("/api/portfolio/firebreak?limit=99", {})
    assert out["params"]["limit"] <= 0.90

    out = api.handle("/api/portfolio/firebreak?limit=nonsense", {})
    assert out["params"]["limit"] == pytest.approx(0.10)


def test_an_all_cash_portfolio_reports_none_found_not_safe():
    """"We looked in a range and did not find one" and "you are safe" are
    different statements, and only one of them is ours to make."""
    out = api.handle("/api/portfolio/firebreak?limit=0.10",
                     {"holdings": [{"symbol": "CASH", "market_value": 10000.0}]})

    assert out["found"] is False
    assert "did not find" in out["reason"] or "No shock" in out["reason"]
    assert "pct" not in out, "a result that was not found must not report a number"


def test_a_supplied_portfolio_is_used_rather_than_the_demo_one():
    out = api.handle("/api/portfolio/firebreak?limit=0.10", {
        "holdings": [
            {"symbol": "NVDA", "market_value": 9000.0},
            {"symbol": "CASH", "market_value": 1000.0},
        ],
        "source": "csv",
    })

    assert out["portfolio"]["total_value"] == pytest.approx(10000.0)
    assert out["portfolio"]["source"] == "csv"
    # 90% in one name breaks far sooner than the diversified demo book
    assert out["pct"] < api.handle("/api/portfolio/full?limit=0.10", {})["pct"]


def test_portfolio_routes_do_not_claim_knob_state_they_do_not_have():
    """They are keyed by a portfolio, not by four sliders."""
    out = api.handle("/api/portfolio/demo", {})
    assert out["cached_for"] == {}


def test_an_unmodellable_holding_is_a_refusal_not_a_clean_bill_of_health():
    """The worst bug this file exists to prevent.

    `weight_vector` raised, `handle` let it escape, the server wrapped it as
    `{"error": ...}` with a 200, and the frontend's `if (!body.found)` branch
    caught it — because `undefined` is falsy — and rendered "no shock in the
    tested range crossed your limit. That is not the same as safe."

    Nothing had been searched. A holding had been refused. The screen said the
    opposite, in the exact register this project reserves for honest negatives.

    And the input is VOO, or SPY, or VTI: the single most likely line in a real
    brokerage CSV.
    """
    out = api.handle("/api/portfolio/full?limit=0.10",
                     {"holdings": [{"symbol": "VOO", "market_value": 10000.0}]})

    assert out["found"] is False
    assert out["refused"] is True, "a refusal must be distinguishable from a null result"
    assert out["unmodelled"] == ["VOO"]
    assert "VOO" in out["reason"]
    assert "pct" not in out, "nothing was searched, so nothing may be reported"


def test_a_refusal_names_what_it_can_model_so_the_user_can_act():
    out = api.handle("/api/portfolio/full?limit=0.10",
                     {"holdings": [{"symbol": "SPY", "market_value": 5000.0},
                                   {"symbol": "NVDA", "market_value": 5000.0}]})

    assert out["refused"] is True
    assert "NVDA" in out["modelled"] and "CASH" in out["modelled"]


@pytest.mark.parametrize("value", [0.0, -500.0])
def test_a_portfolio_worth_nothing_is_refused_not_scored(value):
    """It reported a 100% loss at a 0.00% shock.

    weights() returns {} when the total is <= 0, so the vector was zeros with
    zero cash — breaking the invariant that they sum to 1 — and the loss came
    out as 1 - 0 = 100%. That is >= every limit, so the search's zero-shock
    guard fired and the app announced a break point of nothing at all:
    "your portfolio is destroyed by a shock of zero."
    """
    out = api.handle("/api/portfolio/full?limit=0.10",
                     {"holdings": [{"symbol": "NVDA", "market_value": value}]})

    assert out["found"] is False and out["refused"] is True
    assert "worth" in out["reason"]
    assert "pct" not in out
