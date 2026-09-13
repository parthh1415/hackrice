# Minima Portfolio Pivot — design

**Source of truth:** `MINIMA_PRODUCT_PIVOT_FOR_CLAUDE.md` (the brief).
**Goal:** wrap the existing engine in a user workflow — *my portfolio → my failure limit →
my breaking shock → why it breaks → smallest fix → validate the fix* — without touching the
numerical core, and without deleting Risk Desk mode.

## The load-bearing insight

The engine already generalises. `find_weakest_shock(condition, ...)` takes any
`condition(CascadeResult) -> bool`, and `CascadeResult.prices` is the post-cascade price
vector. So "the user's portfolio crosses its loss limit" is *just another predicate*:

```python
def portfolio_loss_above(weights, limit):
    return lambda r: 1.0 - float(np.dot(weights, r.prices)) >= limit
```

No change to `run_cascade`, `find_weakest_shock`, or `find_cheapest_fix`. The whole pivot is
a new predicate, a portfolio adapter, a validation layer and a UI. That is why this is
buildable in the time available, and it is the strongest possible answer to "did you rebuild
the engine for the demo" — no, the engine was always general; we were only ever calling it
one way.

## Observer, not participant

The user's portfolio watches the institutional cascade and takes the price damage. It does
**not** join the network.

This is a modelling decision with a consequence that must be stated on screen: **the user's
fix does not change the cascade.** Institutional deleveraging happens identically either
way. Reducing NVDA changes the user's *exposure* to that price path, not the path. Anything
else would be pretending a retail account moves markets, and §11 of the brief forbids it.

The honest framing: *"Your position doesn't move the market. It decides how much of the
market's move lands on you."*

## Failure conditions

| mode | predicate | keeps working |
|---|---|---|
| Portfolio (new default) | user loss ≥ limit | — |
| Risk Desk (preserved) | ≥ N funds breach | every existing test |

Both live in `search.py` beside `at_least_n_breaches`. Nothing is replaced.

## Stabilisation in Portfolio Mode

Reuse `find_cheapest_fix`'s shape but over the user's weights, cutting one position to
**cash**. Cash is a real asset in the user vector with price fixed at 1.0, so value is
conserved and visible — §18's "do not quietly change portfolio value."

## Validation layer — four tests, three of which we can honestly ship

1. **Identical shock replay.** Same shock vector, same assumptions, same cascade, only the
   weights differ. This is exact and cheap: the price path is already computed.
2. **New breaking point.** Re-run the reverse search against the adjusted weights. Uniquely
   Minima, and the brief is right that it beats a return chart.
3. **Synthetic stress.** N deterministic sampled shock vectors through the same engine,
   both portfolios scored on identical draws. Seeded, reproducible, offline.
4. **Historical replay.** *We do not ship the price history for this.* Building it against
   invented returns would be the exact sin this project has spent its whole life removing.
   The interface exists and the UI says plainly that it is unavailable without a data file,
   per §42 — missing coverage is stated, never silently scored as zero risk.

## Precision discipline carries over

The new break point is a search result and obeys the same rule as the old one: display no
more precision than the search resolved. `test_precision_is_earned.py` extends to cover it.

## Architecture

```
ingestion (demo | csv | brokerage)
   -> normalise  -> Portfolio {symbol, quantity, market_value, weight}
   -> adapter    -> weight vector aligned to the engine's ticker order
   -> predicate  -> find_weakest_shock  [unchanged]
   -> cascade    -> run_cascade         [unchanged]
   -> stabilise  -> find_cheapest_fix   [unchanged shape]
   -> validate   -> new layer
   -> UI / persistence
```

Numerical functions take plain data and return plain data. No Firebase inside the core.

## What I am NOT doing, and why

- **Firebase**: no project credentials exist here. I build the persistence *interface* and a
  local adapter so it slots in, and I do not fake a connection. §28's rule generalises:
  never fabricate a successful integration.
- **SnapTrade**: same. The button exists, is honestly labelled unavailable, and CSV/demo carry
  the flow.
- **Historical replay**: see above.

## Acceptance

The brief's §51 checklist, minus the Firebase rows, which are honestly out of reach without
a project. Every old test keeps passing — that is non-negotiable and mechanically checked.
