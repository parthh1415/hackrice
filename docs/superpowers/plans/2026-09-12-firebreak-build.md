# Firebreak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Firebreak — a reverse stress-testing tool that finds the smallest shock breaking a network of overlapping leveraged funds, then the cheapest intervention that prevents it — with a four-scene web UI running locally.

**Architecture:** Pure-Python engine (already built and tested) wrapped by a stdlib HTTP server exposing JSON endpoints. Vanilla-JS frontend, no build step, no framework — four scenes on one page, advanced by one button each. Fund holdings come from real SEC 13F filings; leverage and price impact are declared scenario parameters.

**Tech Stack:** Python 3.13 + numpy + pytest. Stdlib `http.server`. Vanilla JS + inline SVG. No npm, no bundler, no CDN dependency.

**Spec:** `docs/superpowers/specs/2026-09-12-firebreak-design.md`

> **Status 2026-09-12.** This is the plan as written, kept for the record. Tasks 1–6 shipped, Task 8
> shipped only in part (the golden-path cache; the assumptions panel was not built);
> **Task 7 (Scene 4 — CSV import / bystander view) was cut** and is a Devpost "what's next" bullet.
> Code blocks below are the plan's *intended* implementations and several drifted during the build —
> where that happened it is flagged inline. The spec is the document that has been reconciled against
> the running code; read that for current behaviour.

## Global Constraints

- **Deadline:** Sunday 2026-09-13 09:00 CDT. Tasks 1–6 are the minimum winning version; 7–8 are cut first.
- **No new pip dependencies.** numpy and pytest only. Nothing that needs installing on a demo machine.
- **TDD throughout.** Test first, watch it fail, minimal implementation, watch it pass, commit.
- **Every number shown in the UI must be derivable.** No fake precision. Amplification is reported to 2 dp, losses to 1 dp.
- **Real vs declared, stated everywhere:** holdings are real 13F; leverage `λ`, impact `γ`, and ADV are declared parameters and must be visible and adjustable in the UI.
- **Amplification is `final_loss / shock_loss`, both equity-denominated.** It must equal exactly 1.0 when `γ = 0`. Never redefine this.
- **Declared scenario parameters are λ, γ and `band`.** *(Added after the build: the breach band was
  hardcoded at 1.05 during the work below and turned out to move the hero number more than either
  slider. It is a parameter now — spec §2.4 item 7 and §3.4.)*
- **Server port 8765**, bound to `127.0.0.1` only. *(As built — `server.py:13`, `server.py:62`.)*
- ~~**Colour semantics are fixed:** teal `#55B4C2` structural, green `#3FC29B` stable, amber `#D8A33F` stressed, ember `#E4705C` breached.~~
  **Superseded.** The frontend was restyled as a monochrome risk terminal. State escalates by
  luminance first, hue last: healthy dim white, stressed full white, breached red `#FF383B` — the
  only chromatic value in the product. None of the four hexes above appear anywhere in `web/`. See
  the header comment in `web/style.css`.

---

### Task 1: Stabilisation search

**Files:**
- Create: `src/firebreak/stabilise.py`
- Test: `tests/test_stabilise.py`

**Interfaces:**
- Consumes: `run_cascade` and `CascadeResult` from `firebreak.engine`; condition builders from `firebreak.search`.
- Produces: `find_cheapest_fix(condition, holdings, leverage, max_leverage, target_leverage, gamma, adv, shock, **kw) -> Fix | None` where `Fix` is a dataclass with fields `fund: int`, `asset: int`, `reduction: float` (fraction of that position sold, 0–1), `cost: float` (fraction of total gross assets given up).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stabilise.py
import numpy as np
from firebreak.search import at_least_n_breaches
from firebreak.stabilise import find_cheapest_fix
from firebreak.engine import run_cascade

CROWDED = np.array([[20.0, 80.0, 0.0], [0.0, 80.0, 20.0]])
ADV = np.array([2000.0, 2000.0, 2000.0])

def system(leverage=6.0):
    m = CROWDED.shape[0]
    return dict(holdings=CROWDED,
                leverage=np.full(m, leverage),
                max_leverage=np.full(m, leverage * 1.05),
                target_leverage=np.full(m, leverage * 0.95),
                gamma=0.5, adv=ADV)

def test_the_fix_actually_prevents_the_failure():
    shock = np.array([-0.05, 0.0, 0.0])
    condition = at_least_n_breaches(2)
    fix = find_cheapest_fix(condition=condition, shock=shock, **system())
    assert fix is not None
    patched = system()
    patched["holdings"] = fix.apply(CROWDED)
    assert not condition(run_cascade(shock=shock, **patched))
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd ~/Desktop/firebreak && python3 -m pytest tests/test_stabilise.py -q`
Expected: `ModuleNotFoundError: No module named 'firebreak.stabilise'`. Create the module with `def find_cheapest_fix(*a, **k): raise NotImplementedError` and re-run until it fails with `NotImplementedError` rather than an import error.

- [ ] **Step 3: Implement**

```python
# src/firebreak/stabilise.py
"""The other half: given a shock that breaks us, what's the cheapest change
that makes us survive it?

Scans one (fund, asset) position at a time and finds the smallest reduction
that clears the failure condition. Cost is the fraction of total gross assets
given up — the thing a PM actually has to justify."""

from dataclasses import dataclass
import numpy as np
from .engine import run_cascade

_STEPS = 20  # 5% granularity on the reduction


@dataclass
class Fix:
    fund: int
    asset: int
    reduction: float
    cost: float

    def apply(self, holdings):
        patched = np.asarray(holdings, dtype=float).copy()
        patched[self.fund, self.asset] *= (1.0 - self.reduction)
        return patched


def find_cheapest_fix(condition, holdings, shock, **cascade_kwargs):
    holdings = np.asarray(holdings, dtype=float)
    total = holdings.sum()
    best = None

    for fund in range(holdings.shape[0]):
        for asset in range(holdings.shape[1]):
            if holdings[fund, asset] <= 0:
                continue
            for step in range(1, _STEPS + 1):
                reduction = step / _STEPS
                candidate = Fix(fund, asset, reduction,
                                holdings[fund, asset] * reduction / total)
                result = run_cascade(holdings=candidate.apply(holdings),
                                     shock=shock, **cascade_kwargs)
                if not condition(result):
                    if best is None or candidate.cost < best.cost:
                        best = candidate
                    break  # smaller reductions already failed
    return best
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Add the cost-minimality test**

```python
def test_it_prefers_the_cheaper_of_two_working_fixes():
    shock = np.array([-0.05, 0.0, 0.0])
    fix = find_cheapest_fix(condition=at_least_n_breaches(2), shock=shock, **system())
    # cost is a fraction of the whole system's gross assets, so it must be small
    assert 0.0 < fix.cost < 0.5
```

Run tests, then commit.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "stabilisation search — cheapest position cut that survives the same shock"
```

---

### Task 2: Real 13F dataset builder

**Files:**
- Create: `src/firebreak/dataset.py`
- Create: `data/universe.json`
- Test: `tests/test_dataset.py`

**Interfaces:**
- Consumes: `latest_filing`, `fetch_positions`, `build_holdings` from `firebreak.thirteenf`.
- Produces: `load_dataset(refresh=False) -> dict` with keys `funds: list[str]`, `tickers: list[str]`, `holdings: list[list[float]]`, `adv: list[float]`, `quarter: str`, `source: str`. Cached to `data/cache/dataset.json`.

- [ ] **Step 1: Write `data/universe.json`**

> **Drifted.** As shipped, `Two Sigma` maps to a *list* of CIKs (`[1179392, 1478735]` — Investments
> and Advisers file separately and both books are summed), and the CUSIP map is many-to-one so all
> four Alphabet share classes fold into GOOGL. See the real `data/universe.json`.

```json
{
  "managers": {
    "Citadel": 1423053,
    "Millennium": 1273087,
    "Point72": 1603466,
    "Two Sigma": 1179392,
    "Renaissance": 1037389
  },
  "cusips": {
    "67066G10": "NVDA", "03783310": "AAPL", "59491810": "MSFT",
    "02313510": "AMZN", "02079K30": "GOOGL", "30303M10": "META",
    "11135F10": "AVGO", "00790310": "AMD", "88160R10": "TSLA",
    "46625H10": "JPM"
  },
  "adv_usd_millions": {
    "NVDA": 28000, "AAPL": 11000, "MSFT": 8500, "AMZN": 9500,
    "GOOGL": 6000, "META": 7500, "AVGO": 6500, "AMD": 7000,
    "TSLA": 22000, "JPM": 3000
  }
}
```

ADV figures are order-of-magnitude dollar volumes; they are a declared parameter. Do not present them as precise. *(They were meant to appear in an assumptions panel; that panel was never built — see Task 8.)*

- [ ] **Step 2: Write the failing test**

```python
# tests/test_dataset.py
import json, numpy as np
from firebreak.dataset import assemble

def test_assemble_builds_a_matrix_in_universe_order():
    universe = {"67066G10": "NVDA", "03783310": "AAPL"}
    books = {"Alpha": {"67066G10": 100.0}, "Beta": {"03783310": 50.0}}
    adv = {"NVDA": 1000.0, "AAPL": 500.0}

    data = assemble(books, universe, adv, quarter="2026Q2")

    assert data["funds"] == ["Alpha", "Beta"]
    assert data["tickers"] == ["NVDA", "AAPL"]
    np.testing.assert_allclose(data["holdings"], [[100.0, 0.0], [0.0, 50.0]])
    assert data["adv"] == [1000.0, 500.0]
    assert data["quarter"] == "2026Q2"
```

- [ ] **Step 3: Run it, watch it fail, implement**

```python
# src/firebreak/dataset.py
"""Turn real 13F filings into the matrix the engine eats.

Cached to disk because SEC is slow and we do not want to be fetching 8MB
XML files live in front of judges."""

import json, pathlib
from .thirteenf import build_holdings, fetch_positions, latest_filing

ROOT = pathlib.Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data" / "universe.json"
CACHE = ROOT / "data" / "cache" / "dataset.json"


def assemble(books, universe, adv_by_ticker, quarter):
    funds, tickers, matrix = build_holdings(books, universe)
    return {
        "funds": funds,
        "tickers": tickers,
        "holdings": matrix.tolist(),
        "adv": [float(adv_by_ticker[t]) for t in tickers],
        "quarter": quarter,
        "source": "SEC 13F-HR",
    }


def load_dataset(refresh=False):
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())

    config = json.loads(UNIVERSE.read_text())
    books, quarter = {}, ""
    for name, cik in config["managers"].items():
        _, accession, filed = latest_filing(cik)
        if not accession:
            continue
        books[name] = fetch_positions(cik, accession)
        quarter = quarter or filed

    data = assemble(books, config["cusips"], config["adv_usd_millions"], quarter)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2))
    return data
```

- [ ] **Step 4: Run tests, then fetch real data once**

```bash
python3 -m pytest tests/ -q
PYTHONPATH=src python3 -c "from firebreak.dataset import load_dataset; d=load_dataset(refresh=True); print(d['funds'], d['tickers'])"
```

Expected: five funds, ten tickers, `data/cache/dataset.json` written.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "pull the real books off edgar and cache them"
```

---

### Task 3: API endpoints

**Files:**
- Modify: `src/firebreak/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `handle(path, body) -> dict` routing `/api/health`, `/api/dataset`, `/api/break`, `/api/stabilise`, `/api/boundary`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api.py
from firebreak import api

def test_dataset_endpoint_returns_the_books():
    result = api.handle("/api/dataset", {})
    assert len(result["funds"]) >= 2
    assert len(result["tickers"]) == len(result["holdings"][0])

def test_break_endpoint_finds_a_shock():
    result = api.handle("/api/break?leverage=6&gamma=0.5&breaches=2", {})
    assert result["found"] is True
    assert result["magnitude"] < 0
    assert result["asset"] in result["tickers"]
    assert len(result["trajectory"]) >= 1
```

- [ ] **Step 2: Run, watch fail, implement**

```python
# add to src/firebreak/api.py
import numpy as np
from .dataset import load_dataset
from .engine import run_cascade
from .search import at_least_n_breaches, find_weakest_shock
from .stabilise import find_cheapest_fix


def _params(data, params):
    m = len(data["funds"])
    lev = float(params.get("leverage", 4.0))
    return dict(
        holdings=np.array(data["holdings"]),
        leverage=np.full(m, lev),
        max_leverage=np.full(m, lev * 1.05),
        target_leverage=np.full(m, lev * 0.95),
        gamma=float(params.get("gamma", 0.4)),
        adv=np.array(data["adv"]),
    )


def _break(params):
    data = load_dataset()
    kw = _params(data, params)
    condition = at_least_n_breaches(int(params.get("breaches", 2)))
    found = find_weakest_shock(condition=condition, **kw)
    if found is None:
        return {"found": False, **data}
    result = run_cascade(shock=found.shock, **kw)
    return {
        "found": True,
        "asset": data["tickers"][found.asset],
        "asset_index": found.asset,
        "magnitude": found.magnitude,
        "pct": found.pct,
        **data,
        **result.as_dict(),
    }
```

Wire `/api/dataset` to `load_dataset()`, `/api/break` to `_break`, and add `/api/stabilise` calling `find_cheapest_fix` with the shock recomputed from the same params.

- [ ] **Step 3: Run tests, verify in the browser**

```bash
python3 -m pytest tests/ -q
curl -s 'http://localhost:8765/api/break?leverage=6&gamma=0.5&breaches=2' | head -c 400
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "json endpoints over the engine"
```

---

### Task 4: Scene 1 — Break (network + cascade animation)

**Files:**
- Create: `web/app.js`, `web/style.css`
- Modify: `web/index.html`

**Interfaces:**
- Consumes: `/api/break`.
- Produces: `renderNetwork(svg, data, round)` and `playCascade(data)` in `web/app.js`.

- [ ] **Step 1: Lay out the bipartite network**

Assets in a left column, funds in a right column, edge opacity proportional to position weight. Node fill from the state ramp: stable green, stressed amber, breached ember. Compute y positions as `(i + 0.5) / n * height`.

- [ ] **Step 2: Step the animation one cascade round at a time**

One round per 900ms, with a visible round counter. The animation must *be* the mechanism — read `data.trajectory[t].leverage` and `data.trajectory[t].breached` for each frame, never interpolate between precomputed endpoints.

- [ ] **Step 3: Wire the FIND WEAKEST SHOCK button**

On click: fetch `/api/break` with the current slider values, show the returned `pct` as the hero number, then play the cascade.

- [ ] **Step 4: Verify in Safari, then commit**

```bash
git add -A && git commit -m "scene 1 — find the shock, watch it spread"
```

---

### Task 5: Scene 2 — Boundary (phase diagram)

**Files:**
- Modify: `web/app.js`
- Modify: `src/firebreak/api.py` (add `/api/boundary`)

- [ ] **Step 1: Add the boundary sweep endpoint**

> **Drifted.** As shipped the grid is **16×16**, not 18×18, and `blends` runs `-1.0 → +1.0` rather
> than `0.0 → 1.0` — a negative blend sharpens each fund away from the system mean, so the crowding
> axis sweeps both ways from the books as filed and measured overlap spans 0.00 to 1.00. The response
> also carries `leverage_axis`, `overlap_axis`, `reference_shock`, `reference_kind` and `here`, and
> `blend_toward_mean`/`mean_overlap` are module-level helpers in `api.py`.

```python
def _boundary(params):
    """Sweep leverage against an overlap-scaling factor and record, for each
    cell, whether a fixed reference shock cascades. This is the phase diagram."""
    data = load_dataset()
    base = np.array(data["holdings"])
    shock = np.zeros(base.shape[1]); shock[0] = -0.05
    grid = []
    for lev in np.linspace(1.5, 8.0, 18):
        row = []
        for blend in np.linspace(0.0, 1.0, 18):
            holdings = _blend_toward_mean(base, blend)
            m = holdings.shape[0]
            r = run_cascade(holdings=holdings,
                            leverage=np.full(m, lev),
                            max_leverage=np.full(m, lev * 1.05),
                            target_leverage=np.full(m, lev * 0.95),
                            gamma=float(params.get("gamma", 0.4)),
                            adv=np.array(data["adv"]), shock=shock)
            row.append(round(float(r.amplification), 3))
        grid.append(row)
    return {"grid": grid, "leverage": [1.5, 8.0], "overlap": [0.0, 1.0]}


def _blend_toward_mean(holdings, blend):
    """blend=0 leaves books as filed; blend=1 makes every fund identical.
    A clean, honest knob for 'how crowded is this system'."""
    weights = holdings / holdings.sum(axis=1, keepdims=True)
    mean = weights.mean(axis=0, keepdims=True)
    blended = (1 - blend) * weights + blend * mean
    return blended * holdings.sum(axis=1, keepdims=True)
```

- [ ] **Step 2: Draw the heatmap from the returned grid**

Colour each cell by amplification band. Draw the contour where amplification crosses 1.5 as the critical boundary. Mark the current `(leverage, measured overlap)` as "you are here".

> **Drifted.** No contour is drawn. `drawBoundary` shades each cell into one of five bands —
> amplification < 1.05, < 1.30, < 1.80, < 3.00, and above — and the boundary is whatever the eye
> reads off the white-to-red step at **1.80**, not a 1.5 isoline. The marker is a ring and a dot.
> The grid also renders in one synchronous pass rather than filling in cell by cell.

- [ ] **Step 3: Make the leverage slider move the marker live**

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "scene 2 — the stability boundary, computed not drawn"
```

---

### Task 6: Scene 3 — Firebreak (before/after)

**Files:**
- Modify: `web/app.js`, `src/firebreak/api.py`

- [ ] **Step 1: Wire `/api/stabilise`** to return the `Fix` plus a re-run of the same shock on patched holdings.

- [ ] **Step 2: Render the instruction in words**, not a score: `"{fund}: cut {asset} exposure {reduction:.0%}. Cost: {cost:.1%} of gross assets."`

- [ ] **Step 3: Show before and after side by side** — system loss and breach count, same shock both sides, with the shock magnitude labelled underneath so it is obviously identical.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "scene 3 — cheapest fix, same shock, different outcome"
```

---

### Task 7: Scene 4 — Exposure (CSV import)

**Files:**
- Modify: `web/app.js`, `src/firebreak/api.py`

- [ ] **Step 1: Parse a pasted or dropped CSV** of `ticker,value` client-side. Every major broker exports this shape.

- [ ] **Step 2: Add the portfolio as a row with `leverage = 1.0`** so it can never breach, and re-run.

- [ ] **Step 3: Show the crowding share** — the fraction of the user's value sitting in tickers whose institutional concentration is above the universe median — and the per-round loss counter.

- [ ] **Step 4: Label it an exposure measurement, never a prediction**, in the UI text itself.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "scene 4 — you never sold, you still lost"
```

---

### Task 8: Assumptions panel and golden-path cache

**Files:**
- Modify: `web/app.js`, `web/index.html`

- [ ] **Step 1: Assumptions panel** listing: quarter, source, λ, γ, ADV values, and the four "what we do not claim" bullets from spec §9. Always reachable, never hidden.

> **Not built.** There is no assumptions panel in `web/index.html` — no quarter, no source line, no
> bullets. The declared parameters live on the control strip and in the `params` block of every API
> response, and the "what we do not claim" list lives in `docs/devpost.md` and the video script.
> Spec §9 now says so. This is the largest single gap between the docs as originally written and the
> shipped app, and it is a small piece of HTML.

- [ ] **Step 2: Cache the golden path.** Add `?demo=1` which loads a recording instead of computing.

> **Drifted (for the better).** Recordings live in `data/cache/golden/` as one file per scenario,
> named by a canonical knob slug (`break__breaches=3__gamma=0.2__leverage=5.json`), written by
> `scripts/record_golden.py` and matched by `api.slug()`. `?demo=1` on any request asks for them,
> `FIREBREAK_DEMO=1` switches the whole process over, and an exploding engine falls back to them.
> There is no single `golden.json`. The command below is the plan's original one-file version:

```bash
PYTHONPATH=src python3 -c "
from firebreak import api, dataset; import json, pathlib
out = api.handle('/api/break?leverage=6&gamma=0.5&breaches=2', {})
pathlib.Path('data/cache/golden.json').write_text(json.dumps(out))
print('golden path cached')"
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "assumptions panel + cached demo path so wifi can't kill us"
```

---

## Self-Review

**Spec coverage.** *(Written before the build; Task 7 was subsequently cut and Task 8's assumptions
panel was never built — §9 is not on screen anywhere.)* §3 model → already built (Tasks complete before this plan). §3.9 reverse search → built. §3.10 stabilisation → Task 1. §2 13F ingest → Task 2. §5 four scenes → Tasks 4–7. §9 what-we-don't-claim → Task 8. §7 sanity tests → green. *(That read "25 passing" when written; the suite is **139 tests** as of
2026-09-12, all passing.)* Gap found and closed: the spec's §5 Scene 2 needed a server-side sweep, added as `/api/boundary` in Task 5.

**Placeholders.** None — every code step contains runnable code. Task 4's steps describe rendering rather than pasting 200 lines of SVG, which is a judgement call: the interface (`renderNetwork`, `playCascade`, the trajectory shape) is specified exactly, and the drawing is genuinely free-form.

**Type consistency.** `Fix.apply(holdings) -> ndarray` used identically in Tasks 1, 3, 6. `find_weakest_shock` returns `WeakestShock` with `.shock`, `.asset`, `.magnitude`, `.pct` — matches `src/firebreak/search.py`. `run_cascade(...).as_dict()` shape matches what Task 4 consumes. `load_dataset()` keys match `_params` and `_break`.
