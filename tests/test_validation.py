"""The validation layer: does the fix actually help, and can we show it.

The failure mode these guard against is a comparison that flatters itself —
two portfolios scored under different conditions, or an "after" number derived
from the "before" one by arithmetic instead of measured by the same search.
Both would look like evidence and be none.
"""

import json
import pathlib

import numpy as np
import pytest

from minima.portfolio import (
    cheapest_portfolio_fix, find_portfolio_breakpoint, normalise, weight_vector,
)
from minima import validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data" / "cache" / "dataset.json").read_text())
TICKERS = DATA["tickers"]
LIMIT = 0.10


def scenario(leverage=5.0, gamma=0.2, band=1.05):
    m = len(DATA["funds"])
    return dict(
        holdings=np.array(DATA["holdings"]),
        leverage=np.full(m, leverage),
        max_leverage=np.full(m, leverage * band),
        target_leverage=np.full(m, min(max(1.0, leverage * 0.95), leverage * band)),
        gamma=gamma,
        adv=np.array(DATA["adv"]),
    )


@pytest.fixture(scope="module")
def solved():
    p = normalise([
        {"symbol": "NVDA", "market_value": 3600.0},
        {"symbol": "MSFT", "market_value": 3150.0},
        {"symbol": "AMZN", "market_value": 2250.0},
        {"symbol": "GOOGL", "market_value": 2250.0},
        {"symbol": "CASH", "market_value": 1050.0},
    ], source="demo")
    vector, cash = weight_vector(p, TICKERS)
    kw = scenario()
    found = find_portfolio_breakpoint(vector, cash, LIMIT, **kw)
    fix = cheapest_portfolio_fix(vector, cash, LIMIT, found.shock, **kw)
    return {
        "before": {"vector": vector, "cash": cash},
        "after": {"vector": fix["vector"], "cash": fix["cash"]},
        "found": found, "fix": fix, "kw": kw,
    }


def test_the_replay_breaks_before_and_survives_after(solved):
    out = validate.replay_identical(
        solved["before"], solved["after"], solved["found"].shock, LIMIT, **solved["kw"])

    assert out["before_breaks"] is True
    assert out["after_breaks"] is False
    assert out["after_loss"] < out["before_loss"]


def test_both_replay_losses_are_the_real_losses_not_merely_ordered(solved):
    """Pins the VALUES, because ordering is not enough.

    A mutation that halved the after-loss left the whole suite green: every
    assertion here only required after < before, and halving preserves that.
    So the screen could have shown any number at all, as long as it was
    smaller — on the comparison whose entire purpose is to be believed.

    Recomputed independently from the same price path.
    """
    out = validate.replay_identical(
        solved["before"], solved["after"], solved["found"].shock, LIMIT, **solved["kw"])

    from minima.engine import run_cascade
    from minima.portfolio import portfolio_loss
    prices = run_cascade(shock=solved["found"].shock, **solved["kw"]).prices

    assert out["before_loss"] == pytest.approx(
        portfolio_loss(solved["before"]["vector"], solved["before"]["cash"], prices))
    assert out["after_loss"] == pytest.approx(
        portfolio_loss(solved["after"]["vector"], solved["after"]["cash"], prices))


def test_the_replay_uses_one_cascade_for_both_sides(solved):
    """"Only the portfolio changed" is the entire claim of this comparison.

    Scoring each side against its own cascade run would let the two drift under
    some future edit while the caption went on saying they had not.
    """
    out = validate.replay_identical(
        solved["before"], solved["after"], solved["found"].shock, LIMIT, **solved["kw"])

    # identical shock, and an amplification that belongs to the one run
    assert out["shock_pct"] == pytest.approx(solved["found"].pct)
    assert out["amplification"] > 1.0


def test_the_new_break_point_is_recomputed_not_derived(solved):
    """Measured by the same search that found the first one.

    Inferring it from the old break point and the size of the cut would be a
    formula dressed as a measurement.
    """
    out = validate.new_breaking_point(
        solved["before"], solved["after"], LIMIT, **solved["kw"])

    assert out["before_pct"] == pytest.approx(solved["found"].pct)
    if out["after_pct"] is not None:
        assert out["after_pct"] > out["before_pct"], (
            "the fix was chosen to survive this shock, so the next break point "
            "has to sit further out"
        )
        assert out["moved_pp"] == pytest.approx(out["after_pct"] - out["before_pct"])

        # moved_ratio is the only two-sided quantity here whose DIRECTION is
        # the whole claim, and nothing asserted it. verify.html renders it as
        # "Additional shock now required: +12%"; inverted to before/after it
        # reads "−11%" — the evidence page saying the defended book breaks more
        # easily — and every test in the suite stayed green.
        assert out["moved_ratio"] == pytest.approx(out["after_pct"] / out["before_pct"])
        assert out["moved_ratio"] > 1.0, (
            "the defended book breaks further out, so the ratio of the new "
            "break point to the old one is greater than one. A value below 1 "
            "renders on the evidence page as a NEGATIVE additional shock"
        )
        # what the page actually prints, stated in the page's own terms
        assert (out["moved_ratio"] - 1.0) * 100.0 > 0
    else:
        assert out["after_unbreakable"] is True
        assert out["after_pct"] is None
        assert "moved_pp" not in out and "moved_ratio" not in out, (
            "verify.html branches on after_unbreakable to avoid calling "
            ".toFixed() on these; if they start appearing, that branch is wrong"
        )


def test_both_portfolios_are_scored_on_identical_draws(solved):
    """Different weather for the two sides would make any difference meaningless."""
    a = validate.synthetic_stress(solved["before"], solved["after"], n=60, seed=7,
                                  **solved["kw"])
    b = validate.synthetic_stress(solved["before"], solved["after"], n=60, seed=7,
                                  **solved["kw"])
    assert a == b, "the seed does not reproduce"

    c = validate.synthetic_stress(solved["before"], solved["after"], n=60, seed=8,
                                  **solved["kw"])
    assert c["before"] != a["before"], "a different seed produced identical draws"


def test_the_fix_cannot_make_the_portfolio_worse_and_that_is_a_theorem(solved):
    """This assertion cannot fail, and saying so is more useful than deleting it.

    Cash is held at par and cascade prices are bounded above by 1.0 — they
    start there, the shock is negative-only, and the impact factor is at most
    1. Moving weight f·vₐ from asset a into cash changes the loss by exactly
    −f·vₐ·(1 − pₐ) ≤ 0. So no cut to cash can raise the loss in any scenario,
    and this holds identically for a $1 cut, the right cut, or one a hundred
    times too large.

    Which means the evidence screen is STRUCTURALLY INCAPABLE of ever reporting
    "this fix did not help". That is worth knowing on the screen whose entire
    purpose is to be believed, and it is why the tests that carry weight here
    are the ones checking the fix is CHEAPEST and that the numbers are
    recomputed — not this one.

    Kept as a guard on the price bound itself, which is the premise the theorem
    rests on and is not obviously true from the outside.
    """
    out = validate.synthetic_stress(solved["before"], solved["after"], n=120, seed=11,
                                    **solved["kw"])
    assert out["after"]["median_loss"] <= out["before"]["median_loss"]
    assert out["after"]["worst_loss"] <= out["before"]["worst_loss"]

    from minima.engine import run_cascade
    prices = run_cascade(shock=solved["found"].shock, **solved["kw"]).prices
    assert (prices <= 1.0 + 1e-12).all(), (
        "a price above par would break the argument above: a cut to cash could "
        "then RAISE the loss, and the monotonicity this file assumes would be "
        "an accident rather than a theorem"
    )


def test_the_new_break_point_is_a_real_search_not_a_multiple_of_the_old_one(solved):
    """`after = before * 1.37` passed every existing assertion.

    The docstring says "recomputed, never derived… a formula dressed as a
    measurement" and the UI caption repeats it verbatim. The test asserted only
    that after > before and that moved_pp was their difference — which any
    monotone formula satisfies.

    A real search lands on the adjusted portfolio's OWN break point, so it has
    to agree with running that search directly.
    """
    out = validate.new_breaking_point(
        solved["before"], solved["after"], LIMIT, **solved["kw"])

    direct = find_portfolio_breakpoint(
        solved["after"]["vector"], solved["after"]["cash"], LIMIT, **solved["kw"])
    assert direct is not None
    assert out["after_pct"] == pytest.approx(direct.pct), (
        "the reported new break point is not what the search returns for that "
        "portfolio — it is coming from somewhere else"
    )
    assert out["after_asset"] == direct.asset


def test_the_after_column_is_scored_with_the_after_weights(solved):
    """Making "after" score the BEFORE weights left the suite green.

    The existing draw test checks that a seed reproduces and that a different
    seed differs — neither of which has anything to do with which weights each
    column was scored with. So the evidence screen's After column could have
    been a copy of Before.
    """
    out = validate.synthetic_stress(solved["before"], solved["after"], n=80, seed=5,
                                    **solved["kw"])

    assert out["after"] != out["before"], (
        "both columns are identical; the After column may be scoring the "
        "before-portfolio's weights"
    )
    # and the direction is the one the theorem above guarantees
    assert out["after"]["worst_loss"] < out["before"]["worst_loss"]


def test_the_percentile_and_worst_summaries_are_what_they_claim(solved):
    """p95 -> p50 and worst -> mean both left the suite green."""
    losses = [0.01, 0.02, 0.03, 0.50]
    summary = validate._summarise(losses)

    assert summary["worst_loss"] == pytest.approx(0.50), "worst is the maximum"
    assert summary["median_loss"] == pytest.approx(0.025)
    assert summary["mean_loss"] == pytest.approx(0.14)
    assert summary["p95_loss"] > summary["median_loss"], "p95 is not the median"
    assert summary["p95_loss"] == pytest.approx(np.percentile(losses, 95))


def test_no_scenario_produces_a_nan_or_an_infinity(solved):
    """Every summary field is a real number — with `survival` explicitly
    required, because it is None unless a limit is passed and this test caught
    that the first time it ran."""
    out = validate.synthetic_stress(solved["before"], solved["after"], n=120, seed=3,
                                    limit=LIMIT, **solved["kw"])
    for side in ("before", "after"):
        assert out[side]["survival"] is not None, (
            f"{side}.survival is None — a limit was passed, so a rate must exist"
        )
        for key, value in out[side].items():
            assert np.isfinite(value), f"{side}.{key} is {value}"


def test_survival_is_absent_rather_than_zero_when_no_limit_is_given():
    """A rate you cannot compute is None, not 0.0 — which would read as
    "nothing survived"."""
    import json, pathlib
    out = validate.synthetic_stress(
        {"vector": np.zeros(len(TICKERS)), "cash": 1.0},
        {"vector": np.zeros(len(TICKERS)), "cash": 1.0},
        n=5, seed=1, **scenario())

    assert out["limit"] is None
    assert out["before"]["survival"] is None


def test_survival_counts_scenarios_under_the_limit():
    assert validate.survival([0.0, 0.05, 0.11, 0.20], 0.10) == pytest.approx(0.5)
    assert validate.survival([0.10, 0.10], 0.10) == pytest.approx(0.0), (
        "a loss exactly at the limit is not survival — the user said they would "
        "not tolerate it"
    )


def test_historical_replay_says_it_is_unavailable_rather_than_inventing_returns():
    """The one test in this file that asserts a feature is ABSENT.

    Shipping it against plausible-looking invented returns would be a confident
    number with nothing underneath it, on the screen that exists to show
    evidence. Missing coverage is stated, not scored as zero risk.
    """
    out = validate.historical_stress()

    assert out["available"] is False
    assert "no price history" in out["reason"].lower()
    assert "loss" not in out, "an unavailable test must not report a number"


def test_the_reported_shock_range_is_the_one_that_was_drawn_from(solved):
    """A literal beside the draws it describes drifts silently.

    `shock_range_pct` was `[1.0, 30.0]` written out fifteen lines below a
    `rng.uniform(0.01, 0.30)`. Widening the draw left the payload describing
    the narrower range, and no test could see it — the summary would have been
    labelled with a range it was not computed over. The range is one argument
    now, which is what makes this checkable at all.
    """
    narrow = validate.synthetic_stress(solved["before"], solved["after"], n=60,
                                       limit=LIMIT, shock_range=(0.01, 0.05),
                                       **solved["kw"])
    wide = validate.synthetic_stress(solved["before"], solved["after"], n=60,
                                     limit=LIMIT, shock_range=(0.01, 0.30),
                                     **solved["kw"])

    assert narrow["shock_range_pct"] == [1.0, 5.0]
    assert wide["shock_range_pct"] == [1.0, 30.0]

    # the label has to move with the draw, not merely alongside it: a wider
    # range must actually produce worse worst cases.
    assert wide["before"]["worst_loss"] > narrow["before"]["worst_loss"], (
        "the reported range changed but the draws did not, so the label is "
        "decoration rather than a description"
    )

    default = validate.synthetic_stress(solved["before"], solved["after"], n=60,
                                        limit=LIMIT, **solved["kw"])
    assert default["shock_range_pct"] == wide["shock_range_pct"]
    assert default["before"]["worst_loss"] == pytest.approx(wide["before"]["worst_loss"])
