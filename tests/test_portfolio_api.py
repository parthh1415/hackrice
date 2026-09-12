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
