"""`measurable` has to be able to say yes.

The existing check is a one-sided implication — if the delta is inside the
search resolution, it must not be called measurable — so two mutations sail
straight through the suite:

    measurable = False, unconditionally          -> all tests green
    resolution = 0.05 (ten times the truth)      -> all tests green,
        and the UI then prints "(search resolves to +/-0.050pp)"

Nothing asserted that a genuinely measurable move gets reported as one, and
nothing tied the stated resolution to the search that produced it. A number
the UI shows as the limit of what we can claim was free to be any constant
at all.

Measurable deltas are rare on purpose — a cheapest single-position cut
defends against THE shock, not the next one — so this pins the settings
where one exists. Found by sweeping all 1920 slider combinations: exactly
two produce `measurable: true`, both at leverage 7 / gamma 0.2 / band 1.2.
"""

import pytest

from firebreak import api
from firebreak.search import DEFAULT_TOLERANCE


def test_the_stated_resolution_is_two_searches_worth_of_tolerance():
    """Not a constant that happens to look right, and not one search's worth.

    The UI prints this as "search resolves to +/-Xpp" — the bound on what the
    product is willing to claim — so it has to come from the thing doing the
    searching. It also has to count BOTH of them: `delta` is the difference of
    two independently bisected searches, each able to be off by a tolerance in
    either direction, so the error on their difference is twice that.

    It was one tolerance until a review agent pointed out the arithmetic. A
    delta of 0.007pp would have been announced as "+0.01pp" while sitting
    inside its own error bar — the precise fake-precision failure this block
    exists to police. It did not bite, because the nearest measurable case is
    thirty times over the bar, which is exactly why it would have gone on not
    biting.
    """
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})
    assert result["bought"]["resolution_pct"] == pytest.approx(2 * DEFAULT_TOLERANCE * 100), (
        "the stated resolution must be two searches' worth of tolerance, "
        "because the delta it bounds is the difference of two searches"
    )


@pytest.mark.parametrize("breaches", [3, 4])
def test_a_move_larger_than_the_resolution_is_reported_as_measurable(breaches):
    """The other half of the implication, which nothing tested.

    At these settings the fix genuinely moves the break point, by about
    thirty times the search's own resolution. Reporting that as "no
    measurable change" would be understating our own result — the mirror of
    the fake precision the rest of this file exists to prevent.
    """
    result = api.handle(
        f"/api/stabilise?leverage=7&gamma=0.2&band=1.2&breaches={breaches}", {})
    bought = result["bought"]

    assert abs(bought["delta_pct"]) > bought["resolution_pct"], (
        "these settings are supposed to produce a delta outside the resolution; "
        f"got {bought['delta_pct']:+.4f}pp against {bought['resolution_pct']}pp"
    )
    assert bought["measurable"] is True, (
        f"delta {bought['delta_pct']:+.4f}pp is {abs(bought['delta_pct']) / bought['resolution_pct']:.0f}x "
        "the stated resolution and was still called unmeasurable"
    )
    assert "moves the break point" in bought["note"], bought["note"]


def test_an_unmeasurable_move_is_still_reported_as_unmeasurable():
    """The demo path, where the honest answer is no.

    Kept alongside the case above so neither direction can be satisfied by a
    constant: one of these two tests fails for `measurable = True` always,
    the other for `measurable = False` always.
    """
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})
    bought = result["bought"]

    assert abs(bought["delta_pct"]) <= bought["resolution_pct"]
    assert bought["measurable"] is False
    assert "no measurable change" in bought["note"], bought["note"]


def test_the_dollar_fields_are_the_fractions_times_the_real_book():
    """position_usd / sell_usd / gross_usd were added with no test at all.

    A mutation sweep changed each of them independently and the suite stayed
    green three times over. They are the numbers the fix line now LEADS with
    — "sell $1.7M of NVDA · 0.073% of a $2.4B position" — so a wrong one is
    a wrong instruction, stated in the units a PM actually acts in.
    """
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})
    fix, holdings = result["fix"], result["holdings"]

    position = holdings[fix["fund_index"]][fix["asset_index"]]
    gross = sum(sum(row) for row in holdings)

    assert fix["position_usd"] == pytest.approx(position), (
        "position_usd does not match the holding it names"
    )
    assert fix["gross_usd"] == pytest.approx(gross), (
        "gross_usd does not match the sum of the book"
    )
    assert fix["sell_usd"] == pytest.approx(position * fix["reduction"]), (
        f"sell_usd {fix['sell_usd']:,.0f} prices a reduction of "
        f"{fix['sell_usd'] / position:.8f}, but the reported reduction is "
        f"{fix['reduction']:.8f}"
    )
    # and the two ways of saying the price have to agree
    assert fix["cost"] == pytest.approx(fix["sell_usd"] / gross, rel=1e-9), (
        "cost and sell_usd/gross_usd disagree about the same trade"
    )
