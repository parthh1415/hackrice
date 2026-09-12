"""13F amendments. Getting this wrong is silent and either halves or doubles a book.

SEC Form 13F FAQ 58: RESTATEMENT replaces the original outright; NEW HOLDINGS
is a supplement containing only the added rows and has to be unioned with it.
Picking the wrong rule gives you either a 5%-sized portfolio or a double count.
"""

import pytest

from firebreak.thirteenf import choose_filings


def rec(acc, period, kind=None, date="2026-08-14", is_amendment=None):
    """A filing record as `latest_filings` builds them.

    `is_amendment` comes from the FORM string ("13F-HR/A"), not from the cover
    page — that distinction is the whole of the bug below, so the helper keeps
    them separable. By default an amendment type implies an amendment, which
    is the ordinary case.
    """
    return {
        "accession": acc,
        "period": period,
        "amendment_type": kind,
        "is_amendment": (kind is not None) if is_amendment is None else is_amendment,
        "filing_date": date,
    }


def test_a_plain_filing_is_used_on_its_own():
    chosen = choose_filings([rec("A1", "06-30-2026")])

    assert [c["accession"] for c in chosen] == ["A1"]


def test_only_the_latest_period_is_used():
    chosen = choose_filings(
        [rec("OLD", "03-31-2026"), rec("NEW", "06-30-2026")]
    )

    assert [c["accession"] for c in chosen] == ["NEW"]


def test_a_restatement_replaces_the_original_outright():
    # Citadel actually did this: 0001104659-26-104387 restated Q2-2026,
    # 16,122 rows against the original's 16,127. We were reading the original.
    chosen = choose_filings(
        [
            rec("ORIG", "06-30-2026", None, "2026-08-14"),
            rec("AMEND", "06-30-2026", "RESTATEMENT", "2026-09-02"),
        ]
    )

    assert [c["accession"] for c in chosen] == ["AMEND"]


def test_new_holdings_supplements_rather_than_replaces():
    chosen = choose_filings(
        [
            rec("ORIG", "06-30-2026", None, "2026-08-14"),
            rec("ADDS", "06-30-2026", "NEW HOLDINGS", "2026-09-02"),
        ]
    )

    assert sorted(c["accession"] for c in chosen) == ["ADDS", "ORIG"]


def test_the_latest_restatement_wins_when_there_are_several():
    chosen = choose_filings(
        [
            rec("ORIG", "06-30-2026", None, "2026-08-14"),
            rec("AMEND1", "06-30-2026", "RESTATEMENT", "2026-09-02"),
            rec("AMEND2", "06-30-2026", "RESTATEMENT", "2026-09-20"),
        ]
    )

    assert [c["accession"] for c in chosen] == ["AMEND2"]


def test_nothing_at_all_returns_nothing():
    assert choose_filings([]) == []


def test_an_amendment_with_no_type_on_its_cover_page_is_refused_not_guessed():
    """The one that doubled a book.

    `choose_filings` decided by amendment_type alone, so a 13F-HR/A whose
    cover page omits <amendmentType> read as None — which meant "original" —
    and got summed with the filing it amends. Deleting that single element
    from Citadel's real restatement takes its book from $14.6B to $29.2B,
    gross from $40.9B to $55.5B, and the demo from four funds breaching to
    all five, amplification 1.87 to 2.37. Silently.

    The form string says "/A" and the cover page says
    <isAmendment>true</isAmendment>; both were being thrown away. A filing we
    cannot classify has to stop us, because the two ways of being wrong about
    it differ by a factor of two.
    """
    with pytest.raises(ValueError, match="not one of"):
        choose_filings([
            rec("ORIG", "06-30-2026", None, "2026-08-14"),
            rec("AMEND", "06-30-2026", None, "2026-09-02", is_amendment=True),
        ])


@pytest.mark.parametrize("kind", ["NEW HOLDINGS ONLY", "COMBINATION REPORT",
                                  "", "restated", "AMENDMENT"])
def test_an_amendment_type_we_do_not_recognise_is_refused_not_dropped(kind):
    """The mirror image, equally silent.

    An unrecognised type matched neither branch, so the amendment simply
    vanished and the superseded original was used. Between that and the case
    above there was no input at all that produced a loud failure for an
    amendment we had mishandled.
    """
    with pytest.raises(ValueError, match="not one of"):
        choose_filings([
            rec("ORIG", "06-30-2026", None, "2026-08-14"),
            rec("AMEND", "06-30-2026", kind, "2026-09-02", is_amendment=True),
        ])


def test_a_supplement_filed_after_a_restatement_still_counts():
    """FAQ 58: NEW HOLDINGS supplements the report as it then stands.

    The restatement branch returned early, so additive rows filed afterwards
    were dropped — an under-count rather than a double count, but silent in
    the same way. Not present in the real data; logic-level fix.
    """
    chosen = choose_filings([
        rec("ORIG", "06-30-2026", None, "2026-08-14"),
        rec("REST", "06-30-2026", "RESTATEMENT", "2026-09-02"),
        rec("ADDS", "06-30-2026", "NEW HOLDINGS", "2026-09-20"),
    ])

    assert [c["accession"] for c in chosen] == ["REST", "ADDS"]


def test_a_supplement_filed_before_a_restatement_is_superseded_by_it():
    """The other order: the restatement replaces everything before it."""
    chosen = choose_filings([
        rec("ORIG", "06-30-2026", None, "2026-08-14"),
        rec("ADDS", "06-30-2026", "NEW HOLDINGS", "2026-08-20"),
        rec("REST", "06-30-2026", "RESTATEMENT", "2026-09-02"),
    ])

    assert [c["accession"] for c in chosen] == ["REST"]


@pytest.mark.parametrize("kind,expect", [
    ("RESTATEMENT ", ["AMEND"]),
    (" restatement", ["AMEND"]),
    ("new holdings", ["ORIG", "AMEND"]),
])
def test_whitespace_and_case_around_a_real_type_are_tolerated(kind, expect):
    """Refusing what we cannot classify must not mean refusing what we can.

    These are the same two types EDGAR defines, written the way a filer's
    software might actually emit them. A stricter reading would turn a
    cosmetic difference into a hard stop on real data.
    """
    chosen = choose_filings([
        rec("ORIG", "06-30-2026", None, "2026-08-14"),
        rec("AMEND", "06-30-2026", kind, "2026-09-02", is_amendment=True),
    ])

    assert [c["accession"] for c in chosen] == expect


def test_a_supplement_with_no_original_is_refused_not_used_alone():
    """A NEW HOLDINGS amendment carries the added rows, not the book.

    Returned on its own it becomes the fund's entire position set — a book a
    fraction of its real size, with no error. That is the same silent
    factor-of-N this module already refuses to guess at for an unclassifiable
    amendment type, and it does not depend on any reading of the FAQ: a
    supplement without the thing it supplements is not a portfolio.

    Reachable whenever the original falls outside the look-back window, which
    counts candidate filings rather than distinct periods, so a heavily-amended
    quarter pushes it out.
    """
    supplement = {
        "accession": "SUPP", "period": "2026-06-30", "filing_date": "2026-08-14",
        "is_amendment": True, "amendment_type": "NEW HOLDINGS",
    }
    with pytest.raises(ValueError) as excinfo:
        choose_filings([supplement])
    assert "supplement" in str(excinfo.value).lower()

    # with its original present it is used, as before
    original = dict(supplement, accession="ORIG", is_amendment=False, amendment_type=None)
    assert [r["accession"] for r in choose_filings([original, supplement])] == ["ORIG", "SUPP"]


def test_a_supplement_after_a_restatement_still_needs_the_restatement():
    """The restatement is the base; the supplement adds to it."""
    base = {"accession": "REST", "period": "2026-06-30", "filing_date": "2026-08-10",
            "is_amendment": True, "amendment_type": "RESTATEMENT"}
    later = {"accession": "SUPP", "period": "2026-06-30", "filing_date": "2026-08-20",
             "is_amendment": True, "amendment_type": "NEW HOLDINGS"}
    assert [r["accession"] for r in choose_filings([base, later])] == ["REST", "SUPP"]
