"""The Portfolio Mode endpoints, and the caching decision behind them.

The interesting assertion in this file is the one about what these routes do
NOT do: they are not cached by knobs. The institutional routes key their
recordings on four slider positions, which is sound when the sliders are the
whole question. A portfolio is not a slider position — the same knobs with a
different portfolio is a different question — so keying a portfolio answer on
knobs alone would serve one person's result to another. That is the
`cached_for` mismatch in a far worse costume.
"""

import json
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


def test_every_number_in_the_recommendation_is_recomputed_not_just_positive():
    """The one sentence the user acts on, pinned field by field.

    A review agent moved each of these independently — inflating the dollars by
    1.35x, halving the position fraction, inventing loss_after — and the suite
    stayed at 282 passed every time. The only assertion guarding them was
    `out["fix"]["dollars"] > 0`.

    "Reduce NVDA by $478 · 13.3% of that position · leaves a 9.00% loss" is
    four numbers, and a wrong one is a wrong trade.
    """
    out = api.handle("/api/portfolio/full?limit=0.10", {})
    fix, total = out["fix"], out["portfolio"]["total_value"]
    holding = next(h for h in out["portfolio"]["holdings"] if h["symbol"] == fix["symbol"])

    assert fix["dollars"] == pytest.approx(fix["weight_moved"] * total), (
        "the dollar figure must be the weight actually moved times the real total"
    )
    assert fix["fraction_of_position"] == pytest.approx(
        fix["dollars"] / holding["market_value"], rel=1e-9), (
        "the percentage and the dollars must describe the same cut"
    )
    assert fix["loss_after"] <= fix["target_loss"] + 1e-12
    assert fix["target_loss"] == pytest.approx(
        out["params"]["limit"] * (1.0 - fix["margin"]))


def test_the_direct_loss_is_the_shock_alone_not_a_scaled_cascade():
    """Amplification is cascade/direct, so a wrong direct loss moves the one
    number the product's whole argument rests on. Recomputed here from the raw
    shock, with no cascade involved at all."""
    out = api.handle("/api/portfolio/full?limit=0.10", {})

    weight = next(h["weight"] for h in out["portfolio"]["holdings"]
                  if h["symbol"] == out["asset"])
    assert out["direct_loss"] == pytest.approx(weight * abs(out["magnitude"]), rel=1e-9), (
        "the direct loss is just the shocked name's weight times the shock"
    )
    assert out["amplification"] == pytest.approx(out["cascade_loss"] / out["direct_loss"])


def test_a_csv_with_only_a_header_is_refused_not_replaced_by_the_demo():
    """`[]` is falsy in Python and truthy in JavaScript.

    So a header-only CSV posted `{"holdings": []}`, hit `if not rows`, and got
    the demo book back — rendered as the user's own analysis, under a note
    reading "Loaded 0 rows from your-file.csv".
    """
    out = api.handle("/api/portfolio/full?limit=0.10", {"holdings": [], "source": "csv"})

    assert out["found"] is False and out["refused"] is True
    assert "no holdings" in out["reason"]
    assert "portfolio" not in out, "nothing was analysed, so no portfolio may be reported"


def test_an_absent_holdings_key_still_means_the_demo():
    """The distinction the fix rests on: absent is not empty."""
    assert api.handle("/api/portfolio/full?limit=0.10", {})["portfolio"]["source"] == "demo"
    assert api.handle("/api/portfolio/full?limit=0.10",
                      {"holdings": None})["portfolio"]["source"] == "demo"


def test_step_four_replays_the_portfolio_s_own_shock():
    """The "why" screen must animate the shock the result card just reported.

    It called /api/break, which SEARCHES for the institutional shock rather
    than replaying one — so the cascade underneath a result saying "NVDA
    −24.69%, five institutions" was NVDA −5.27% with four.
    """
    full = api.handle("/api/portfolio/full?limit=0.10", {})
    replay = api.handle(
        f"/api/cascade?asset={full['asset']}&magnitude={abs(full['magnitude'])}"
        f"&leverage=5&gamma=0.2&band=1.05", {})

    assert replay["asset"] == full["asset"]
    assert replay["pct"] == pytest.approx(full["pct"])
    assert replay["breached"] == full["breached"], (
        "the cascade shown must be the one the result card described"
    )
    assert replay["rounds"] == full["rounds"]


@pytest.mark.parametrize("given,used", [(0.95, 0.90), (0.0, 0.01), (-1.0, 0.01)])
def test_a_clamped_limit_is_reported_as_clamped(given, used):
    """`clamped: []` next to a limit that was changed is a false statement.

    Every other knob that gets pulled back into range records itself in
    `clamped`, which is what the UI reads to tell you it did not use the number
    you gave it. `limit` was clamped silently, so asking for a 95% limit came
    back as a 90% limit with the payload asserting that nothing had been
    adjusted — and the nav, which reads the number the user typed, went on
    showing 95% beside a page reading 90%.

    Not reachable from the product UI, which offers 5/10/15/25%. Reachable from
    a URL, and wrong in either.
    """
    out = api.handle(f"/api/portfolio/full?limit={given}", {})
    assert out["params"]["limit"] == pytest.approx(used)
    names = [c["name"] for c in out["params"].get("clamped", [])]
    assert "limit" in names, (
        f"limit {given} was used as {used} and clamped says {out['params'].get('clamped')}"
    )
    entry = next(c for c in out["params"]["clamped"] if c["name"] == "limit")
    assert entry["given"] == pytest.approx(given)
    assert entry["used"] == pytest.approx(used)


def test_a_limit_inside_the_range_is_not_reported_as_clamped():
    out = api.handle("/api/portfolio/full?limit=0.15", {})
    assert out["params"]["limit"] == pytest.approx(0.15)
    assert not [c for c in out["params"].get("clamped", []) if c["name"] == "limit"]


@pytest.mark.parametrize("query,knob", [
    ("/api/break?breaches=inf", "breaches"),
    ("/api/break?breaches=-inf", "breaches"),
    ("/api/break?leverage=inf&breaches=3", "leverage"),
    ("/api/break?gamma=-inf&breaches=3", "gamma"),
])
def test_an_infinite_knob_is_clamped_and_declared_like_every_other(query, knob):
    """`int(float("inf"))` raises OverflowError, which is not a ValueError.

    It escaped the guard entirely and propagated out of handle(), whose
    except-clause falls back to load_golden with no near check — so
    `?breaches=inf` returned 200, found: true, pct 1.734%, and a params block
    reading band=1.02, breaches=3 with clamped: []. Settings nobody asked for,
    presented as the settings that were used. Every other out-of-range value
    was clamped and declared; that one alone answered a different question
    confidently.
    """
    out = api.handle(query, {})
    assert out["found"] is True
    names = [c["name"] for c in out["params"].get("clamped", [])]
    assert knob in names, (
        f"{query} used {out['params'].get(knob)} and reported {out['params'].get('clamped')}"
    )
    # and it must be answering the question asked, not one off the shelf
    if out.get("cached"):
        assert out.get("cached_exact"), out.get("cached_for")
    # `given` has to survive json.dumps — a bare Infinity is not valid JSON
    json.dumps(out["params"]["clamped"])


def test_a_fractional_breach_count_says_it_was_truncated():
    """int() truncates. 2.999999999 became 2 in silence.

    That is exactly where a slider readout carrying float error lands, and 2
    against 3 is 4.598% against 5.273% on the screen.
    """
    out = api.handle("/api/break?breaches=2.999999999", {})
    entry = [c for c in out["params"]["clamped"] if c["name"] == "breaches"]
    assert entry, out["params"].get("clamped")
    assert entry[0]["used"] == 2


@pytest.mark.parametrize("magnitude,expect_price", [(5, 0.0), (1.5, 0.0), (0.25, 0.75)])
def test_a_price_cannot_fall_by_more_than_all_of_itself(magnitude, expect_price):
    """/api/cascade took `-abs(float(...))` with no range and no record.

    `magnitude=5` set prices[0] to -4.0 — a negative stock price — and then ran
    a full cascade on top of it, reporting the result like any other.
    """
    out = api.handle(f"/api/cascade?asset=NVDA&magnitude={magnitude}", {})
    assert out["trajectory"][0]["prices"][0] == pytest.approx(expect_price)
    assert all(p >= 0.0 for p in out["trajectory"][0]["prices"]), "a negative price"
    if magnitude > 1.0:
        assert any(c["name"] == "magnitude" for c in out["params"].get("clamped", []))


def test_an_unreadable_magnitude_is_zero_and_says_so_rather_than_becoming_nan():
    out = api.handle("/api/cascade?asset=NVDA&magnitude=abc", {})
    assert out["trajectory"][0]["prices"][0] == pytest.approx(1.0)
    assert any(c["name"] == "magnitude" for c in out["params"].get("clamped", []))


def test_the_no_break_point_answer_carries_the_range_it_searched():
    """"The tested range" is an appeal to something the reader cannot see.

    The UI has to be able to name it, and the number belongs to the search
    rather than to a literal typed into a page — otherwise widening _MAX_DROP
    leaves the screen quoting the old figure.
    """
    from firebreak.search import _MAX_DROP

    out = api.handle("/api/portfolio/full?limit=0.90", {"holdings": [
        {"symbol": "CASH", "market_value": 9000},
        {"symbol": "NVDA", "market_value": 1000},
    ], "source": "csv"})
    assert out["found"] is False
    assert out["search_max_drop"] == pytest.approx(_MAX_DROP)


@pytest.mark.parametrize("name,body,needle", [
    ("a NaN market value",
     [{"symbol": "NVDA", "market_value": "nan"}, {"symbol": "CASH", "market_value": 1000}],
     "not a finite number"),
    ("an infinite market value",
     [{"symbol": "NVDA", "market_value": 1e400}, {"symbol": "CASH", "market_value": 1}],
     "not a finite number"),
    ("a row with money and no symbol",
     [{"symbol": "NVDA", "market_value": 1000}, {"symbol": "CASH", "market_value": 1000},
      {"symbol": "", "market_value": 2000}],
     "no symbol"),
    ("a holding that is not an object", ["NVDA"], "not an object"),
])
def test_a_book_we_cannot_read_is_refused_rather_than_absorbed(name, body, needle):
    """Each of these used to produce a confident answer about a different book.

    A NaN value defeats every comparison silently — `nan > 1e-9` is False — so
    the sum-to-one check downstream passed and the search reported "no shock
    within the tested range" for a portfolio it had never scored.

    A row carrying $2,000 under no symbol was skipped, and every other weight
    renormalised around the hole: a $4,000 book answered as a $2,000 one, with
    no refusal. That is the silent undercount this project exists to refuse —
    the same shape as the CUSIP bug in its own origin story.
    """
    out = api.handle("/api/portfolio/full?limit=0.10", {"holdings": body, "source": "csv"})
    assert out["found"] is False, f"{name} produced an answer"
    assert out.get("refused") is True, f"{name} was not refused: {out.get('reason')}"
    assert needle in out["reason"], out["reason"]


def test_holdings_given_as_a_single_object_is_refused_not_a_crash():
    """AttributeError is not on the refusal path.

    `{"holdings": {...}}` reached row.get() as a string and raised, so the
    endpoint answered 200 with an `error` key and NO `found` key — and both of
    the UI's branches, `if (body.refused)` and `if (!body.found)`, fell
    through it.
    """
    out = api.handle("/api/portfolio/full?limit=0.10",
                     {"holdings": {"symbol": "NVDA", "market_value": 1000}, "source": "csv"})
    assert "found" in out and out["found"] is False
    assert out["refused"] is True
    assert "must be a list" in out["reason"]


def test_a_blank_padding_row_is_still_skipped():
    """The guard must not turn trailing empty rows into a refusal — a CSV with
    a stray comma line is not a broken portfolio."""
    out = api.handle("/api/portfolio/full?limit=0.10", {"holdings": [
        {"symbol": "NVDA", "market_value": 3600},
        {"symbol": "CASH", "market_value": 8700},
        {"symbol": "", "market_value": 0},
        {"symbol": "  "},
    ], "source": "csv"})
    assert out["found"] is True
    assert out["portfolio"]["total_value"] == pytest.approx(12300.0)


@pytest.mark.parametrize("query", [
    "/api/break?leverage=nan&breaches=3",
    "/api/break?leverage=1e400&breaches=3",
    "/api/break?gamma=nan&breaches=3",
    "/api/break?band=inf&breaches=3",
    "/api/stabilise?leverage=nan&breaches=3",
    "/api/boundary?gamma=1e400",
])
def test_no_response_can_contain_a_bare_nan_or_infinity(query):
    """json.dumps writes NaN and Infinity as bare tokens, which are not JSON.

    `cached_for` echoed the RAW request rather than the clamped value, so
    `?leverage=nan` put a bare NaN in the body and JSON.parse threw on the
    whole response — a well-formed 200 that no browser could read.
    """
    raw = json.dumps(api.handle(query, {}))
    assert "NaN" not in raw and "Infinity" not in raw, (
        f"{query} produced a body that JSON.parse rejects"
    )
    json.loads(raw)  # and it round-trips


@pytest.mark.parametrize("query,knob,used", [
    ("/api/break?leverage=999&breaches=3", "leverage", 8.0),
    ("/api/break?gamma=-5&breaches=3", "gamma", 0.0),
])
def test_cached_for_reports_the_knobs_the_answer_was_computed_with(query, knob, used):
    """It echoed the request instead.

    `?leverage=999` came back with `params {leverage: 8.0}` next to
    `cached_for {leverage: 999.0}` and `cached_exact: true` — three fields
    disagreeing about which question was answered, on a response that is not
    cached at all.
    """
    out = api.handle(query, {})
    assert out["cached"] is False
    assert out["params"][knob] == pytest.approx(used)
    assert out["cached_for"][knob] == pytest.approx(used), (
        f"cached_for says {out['cached_for'][knob]} where the engine used "
        f"{out['params'][knob]}"
    )


FIDELITY_BOOK = [
    {"symbol": "VOO", "market_value": 13000},
    {"symbol": "NVDA", "market_value": 3600},
    {"symbol": "MSFT", "market_value": 3150},
    {"symbol": "VTI", "market_value": 5220},
    {"symbol": "CASH", "market_value": 6030},
]


def test_an_unmodellable_book_is_refused_but_priced():
    """A real brokerage export is mostly funds we do not model.

    Half a Fidelity book is often one S&P ETF, so refusing outright ends the
    road for anybody who actually uploads one. The refusal now carries what
    saying yes would cost, in the units the user thinks in — otherwise the
    choice is "drop something" with no way to see how much.
    """
    out = api.handle("/api/portfolio/full?limit=0.10",
                     {"holdings": FIDELITY_BOOK, "source": "csv"})

    assert out["found"] is False and out["refused"] is True
    assert sorted(out["unmodelled"]) == ["VOO", "VTI"]
    assert out["can_exclude"] is True
    assert out["excluded_value"] == pytest.approx(18220.0)
    assert out["modellable_value"] == pytest.approx(12780.0)
    assert out["excluded_fraction"] == pytest.approx(18220.0 / 31000.0)


def test_excluding_is_opt_in_and_never_silent():
    """Dropping a holding and renormalising the rest around the hole is the
    silent undercount this project exists to refuse. Chosen, priced, and
    carried onto every screen, it is a different thing — but only if the note
    travels with the answer.
    """
    out = api.handle("/api/portfolio/full?limit=0.10&exclude_unmodelled=1",
                     {"holdings": FIDELITY_BOOK, "source": "csv"})

    assert out["found"] is True
    # the book that was scored is the modellable part, not the whole
    assert out["portfolio"]["total_value"] == pytest.approx(12780.0)

    note = out["excluded_note"]
    assert note is not None, "the answer does not say anything was left out"
    assert sorted(e["symbol"] for e in note["excluded"]) == ["VOO", "VTI"]
    assert note["excluded_value"] == pytest.approx(18220.0)
    assert note["whole_book_value"] == pytest.approx(31000.0)
    assert note["excluded_fraction"] == pytest.approx(18220.0 / 31000.0)


def test_a_fully_modelled_book_carries_no_exclusion_note():
    """The banner must not appear when nothing was excluded."""
    out = api.handle("/api/portfolio/full?limit=0.10&exclude_unmodelled=1", {})
    assert out["found"] is True
    assert out["excluded_note"] is None


def test_portfolio_positions_export_is_fully_modelled():
    """The current Fidelity export must not require dropping any holdings."""
    holdings = [
        {"symbol": "CASH", "market_value": 1256.86},  # SPAXX cash sweep
        {"symbol": "AAPL", "market_value": 1661.35},
        {"symbol": "CVX", "market_value": 428.12},
        {"symbol": "FNDX", "market_value": 1785.30},
        {"symbol": "HEFA", "market_value": 791.35},
        {"symbol": "MSFT", "market_value": 991.26},
        {"symbol": "NOW", "market_value": 148.96},
        {"symbol": "SCHF", "market_value": 1127.60},
        {"symbol": "SCHG", "market_value": 1160.28},
        {"symbol": "SMH", "market_value": 1137.06},
        {"symbol": "VGIT", "market_value": 516.06},
    ]

    out = api.handle("/api/portfolio/full?limit=0.10", {
        "holdings": holdings,
        "source": "csv",
    })

    assert out.get("refused") is not True
    assert out["portfolio"]["total_value"] == pytest.approx(11004.20)
    assert {row["symbol"] for row in holdings if row["symbol"] != "CASH"} <= set(out["tickers"])


def test_a_book_with_nothing_modellable_is_still_refused():
    """Excluding everything leaves no portfolio, and the flag must not force
    an answer out of an empty book."""
    out = api.handle("/api/portfolio/full?limit=0.10&exclude_unmodelled=1", {"holdings": [
        {"symbol": "VOO", "market_value": 10000},
        {"symbol": "VTI", "market_value": 5000},
    ], "source": "csv"})
    assert out["found"] is False and out["refused"] is True
    assert out["can_exclude"] is False
