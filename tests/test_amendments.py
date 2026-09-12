"""13F amendments. Getting this wrong is silent and either halves or doubles a book.

SEC Form 13F FAQ 58: RESTATEMENT replaces the original outright; NEW HOLDINGS
is a supplement containing only the added rows and has to be unioned with it.
Picking the wrong rule gives you either a 5%-sized portfolio or a double count.
"""

from firebreak.thirteenf import choose_filings


def rec(acc, period, kind=None, date="2026-08-14"):
    return {
        "accession": acc,
        "period": period,
        "amendment_type": kind,
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
