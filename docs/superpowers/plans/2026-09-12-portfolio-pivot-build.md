# Portfolio Pivot — build plan

**Spec:** `docs/superpowers/specs/2026-09-12-portfolio-pivot.md`
**Rule for every task:** all existing tests keep passing. Checked mechanically, not by eye.

## Global constraints

- Numerical core (`engine.py`, `search.py`, `stabilise.py`) gains functions, loses none.
- Risk Desk mode keeps working end to end. Its tests are the proof.
- Demo path needs no network, no login, no external API.
- Display no more precision than the search resolved — including the new break point.
- Never claim a solver ran that did not. Never fabricate an integration.
- Every new number gets a mutation in `scripts/mutate.py` proving a test catches it.

---

## Task 1 — the portfolio-loss predicate  ✅ smallest real step

**Files:** `src/minima/portfolio.py` (new), `tests/test_portfolio_predicate.py` (new)

A `Portfolio` dataclass, a normaliser that every ingestion path calls, a weight-vector
adapter aligned to the engine's ticker order, and `portfolio_loss_above(weights, limit)`.

Tests: weights sum to 1 including cash; loss at zero shock is 0; loss under a known price
vector is exact; the predicate flips at the limit and not before; an unknown symbol is
surfaced rather than dropped.

## Task 2 — reverse search over a portfolio

**Files:** `src/minima/portfolio.py`, `tests/test_portfolio_search.py`

`find_portfolio_breakpoint(portfolio, limit, **scenario)` — composes the predicate with the
existing `find_weakest_shock`. No new search code.

Tests: the result crosses the limit; one tolerance below it does not; a tighter limit never
yields a larger shock (monotonicity); display precision is earned.

## Task 3 — portfolio stabilisation

**Files:** `src/minima/portfolio.py`, `tests/test_portfolio_stabilise.py`

Cheapest single-position cut to cash that survives the identical shock.

Tests: total value conserved; the cut clears the limit; a smaller cut does not; the
reported dollar figure equals weight × total value.

## Task 4 — validation layer

**Files:** `src/minima/validate.py` (new), `tests/test_validation.py` (new)

- `replay_identical(portfolio, fixed, shock, scenario)` — one cascade, two scorings.
- `new_breaking_point(fixed, limit, scenario)` — re-runs the search.
- `synthetic_stress(portfolio, fixed, n, seed, scenario)` — identical draws for both.
- `historical_stress(...)` — returns `available: False` with a reason. No invented returns.

Tests: the replay uses the same shock and same prices for both; before/after differ only in
weights; the new break point is recomputed rather than derived; synthetic uses identical
scenario ids for both portfolios; the seed reproduces; no NaN/Inf anywhere.

## Task 5 — API endpoints

**Files:** `src/minima/api.py`, `tests/test_portfolio_api.py`

`/api/portfolio/demo`, `/api/portfolio/parse` (CSV), `/api/portfolio/breakpoint`,
`/api/portfolio/stabilise`, `/api/portfolio/validate`. Same guarded-knobs and cached
discipline as the existing routes.

## Task 6 — guided UI

**Files:** `web/index.html`, `web/app.js`, `web/style.css`

Five steps: Portfolio → Risk limit → Break → Cascade → Stabilise → Validate. Risk Desk
behind a toggle, reachable and unchanged. Existing cascade animation reused verbatim —
it still reads real `trajectory[t]` frames.

## Task 7 — harness + mutation coverage

Extend `smoke.js` / `provenance.js` to the new flow; register mutations for every new
number so the "does a test actually catch this" question is answered mechanically.

## Task 8 — docs

README, devpost and the 3-minute script updated to the new product. Old numbers stay only
where still true.

---

## Order and why

1–4 are the engine and are testable with no UI at all. 5 exposes them. 6 is the product. 7
proves it. 8 sells it. If the clock runs out, stopping after 4 still leaves a working,
tested capability; stopping after 6 leaves a demo.
