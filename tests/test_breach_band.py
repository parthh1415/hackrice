"""The breach band is a scenario parameter and has to behave like one.

`max_leverage = leverage * 1.05` was hardcoded. That 5% is a free parameter
with MORE influence over the headline than gamma or leverage:

    band 1.02  ->  NVDA -1.75%   amp 3.08
    band 1.05  ->  NVDA -5.28%   amp 1.87
    band 1.10  ->  NVDA -10.69%  amp 1.61
    band 1.30  ->  NVDA -27.34%  amp 1.43

A fifteen-fold swing in the number on the wall, from a constant nobody could
see, while the two less influential knobs sat on sliders. That is the worst
configuration to be caught in — it reads as hiding the one that matters.
"""

from firebreak import api


def test_the_band_is_a_declared_parameter():
    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})

    assert "band" in result["params"]
    assert result["params"]["band"] == 1.05


def test_widening_the_band_needs_a_bigger_shock():
    tight = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&band=1.02", {})
    loose = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3&band=1.20", {})

    assert tight["found"] and loose["found"]
    assert loose["pct"] > tight["pct"] * 2, (
        f"band should dominate: got {tight['pct']:.2f}% vs {loose['pct']:.2f}%"
    )


def test_a_band_below_one_would_breach_everyone_instantly():
    result = api.handle("/api/break?band=0.5", {})

    assert result["params"]["band"] >= 1.0
    assert any(a["name"] == "band" for a in result["params"]["clamped"])


def test_the_band_is_never_below_the_deleverage_target():
    """target is leverage*0.95; a band under that makes the fix unreachable."""
    result = api.handle("/api/break?leverage=5&band=1.0", {})

    assert result["params"]["band"] >= 1.0
