"""The API must never answer a question nobody asked.

Before this, `?gamma=-2` produced a confident 5.25% hero number from a model
where forced selling pushes prices UP, `?leverage=99` gave 0.16%, `?breaches=0`
gave 0.0% (zero funds breaching is trivially true), and `?gamma=abc` silently
fell back to the default and answered as though it had been asked properly.

The demo must not error — a stack trace in front of judges is worse than a
clamp. So: clamp to the physically meaningful range, and SAY SO in the payload
so nothing is silent.
"""

from firebreak import api


def test_negative_impact_is_refused_not_modelled():
    # gamma < 0 means forced selling raises prices. that isn't a stress test,
    # it's a different universe.
    result = api.handle("/api/break?gamma=-2", {})

    assert result["params"]["gamma"] >= 0.0
    assert any(a["name"] == "gamma" for a in result["params"]["clamped"])


def test_absurd_leverage_is_clamped_and_declared():
    result = api.handle("/api/break?leverage=99", {})

    assert result["params"]["leverage"] <= 8.0
    assert any(a["name"] == "leverage" for a in result["params"]["clamped"])


def test_a_failure_condition_of_zero_is_not_a_failure_condition():
    result = api.handle("/api/break?breaches=0", {})

    assert result["params"]["breaches"] >= 1
    assert any(a["name"] == "breaches" for a in result["params"]["clamped"])


def test_garbage_is_flagged_rather_than_silently_defaulted():
    result = api.handle("/api/break?gamma=abc", {})

    adjustments = {a["name"]: a for a in result["params"]["clamped"]}
    assert "gamma" in adjustments
    assert adjustments["gamma"]["reason"] == "unreadable"


def test_breaches_cannot_exceed_the_number_of_funds():
    result = api.handle("/api/break?breaches=99", {})

    assert result["params"]["breaches"] <= len(result["funds"])


def test_a_clean_request_declares_nothing_clamped():
    result = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})

    assert result["params"]["clamped"] == []
    assert result["params"]["leverage"] == 5.0
    assert result["params"]["gamma"] == 0.2
