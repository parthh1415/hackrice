# Video shooting guide

What to point the camera at, as the app actually is. Everything below was read
off the running build, not off the source.

This file has been rewritten once already. The first version bridged
`docs/video-script.md` — written against the single-page institutional app —
to the six dark pages that replaced it. The frontend has since been rebuilt
again against `DESIGN.md`: eight screens, monochrome on paper, red only where a
limit is crossed. Anything you remember about cyan, amber, a terminal ground or
a status bar at the foot is gone.

---

## What the app is now

Eight screens. Six are a numbered sequence in the left rail; two sit below a
rule as reference screens and are deliberately unnumbered.

| key | screen | what it answers |
|---|---|---|
| `1` | Portfolio | what are we stress testing |
| `2` | Limit | what loss would you refuse to tolerate |
| `3` | Break | the smallest shock that crosses it, and what it costs |
| `4` | Cascade | why the loss grows |
| `5` | Fix | the cheapest single-position change |
| `6` | Validate | did it actually help |
| `7` | Boundary | where the system stops absorbing at all |
| `8` | Model | what is measured, what is declared, what computed the patch |

Limit is a section of the Portfolio screen rather than a page of its own, so
`2` scrolls rather than navigates.

Also: `←` / `→` step the cascade, `space` plays it, `?` lists the keys.

The rail's foot prints the book's source and the last engine response time —
`demo · 10ms`, measured, not typed — over `engine live`. That readout is worth
two seconds of screen time on its own.

Any screen opens demo-ready with `?demo`, e.g.
`localhost:8765/defend.html?demo`. That is the reliable way to set up a shot
without filming yourself clicking to it.

---

## The demo path, as a presenter walks it

Covered by an automated check that fails if any step breaks, so it is safe to
rehearse against.

1. `localhost:8765/index.html` — press **Use demo portfolio**
2. press **Run reverse stress test** → Break
3. press **See why the loss grows** → Cascade
4. press **Find the cheapest single-position fix** → Fix
5. press **Check it actually helped** → Validate
6. press **Map the whole system** → Boundary

---

## The five frames worth building the video around

In order of how much they carry.

**1. The Fix page, above the fold.** The same waterfall drawn twice over
itself: the book as it stands as a thin outline, the defended book filled in
ink on top. The outline crosses the dashed limit line at the bottom right; the
filled series stops at 9.00%, above it. One shock, two books, one picture —
and both series are read off a single price path, because the portfolio is an
observer and the cut does not change what the five books are forced to do.
This is the strongest single frame in the product. Hold on it.

**2. The Break page waterfall.** Cumulative loss falling left to right:
`7.33% → 9.28% → 9.85% → 10.00%`, one band per cascade round, against a dashed
line at your limit. The first band is the shock alone. Everything after it is
other people selling. The segments draw in over about a third of a second on
load, so refresh the page rather than cutting to it cold.

Note the crossing is a hairline, and say so if you narrate it: a reverse stress
test returns the shock that lands you *exactly* on your limit, so the book
touches the line at the very end rather than sailing through it. That is what a
break point is.

**3. The Boundary map.** 16×16, leverage 1.5 to 8.0 up the side, crowding along
the bottom, every cell a full cascade — 256 of them, nothing interpolated. Pale
paper at the bottom left where every shock is absorbed, through to near-black
at the top right. An ink contour on the cell edges where amplification crosses
1.5×, and a small ink cross on where the five books actually sit, labelled
`As filed — λ 5.0, overlap 0.71`. It sits just past the cliff: the headroom
tile reads **−0.03×**.

**4. The attribution table** (Break). Weight, Shocked, Total fall, From
contagion, Costs you — and it foots to exactly the 10.00% in the headline.
GOOGL falls 5.31% having never been shocked. This is the thesis as arithmetic
rather than as a claim.

**5. The crowding column** (Portfolio). `0.9 days of volume` against NVDA's
`0.3`, on the first screen, before anything has been run. The mechanism
previewed, and the reason GOOGL is the name that bleeds.

---

## Also worth filming

- **The forced-selling flow** (Cascade, press `space`). The red edges are
  dollars sold that round and they visibly die out: **$8.72B → $2.49B →
  $818M**. Four books breach at round 1 — Citadel, Millennium, Two Sigma,
  Renaissance — and Point72 joins at round 2, so **5 of 5** are over by the
  end.
- **The footing table** (Fix). Current and Defended both total $12,300 — "worth
  the same afterwards" made checkable rather than asserted.
- **The Model page** (`8`). Every input tagged measured, declared or not
  modelled — and the tag is the ink's weight, not a colour, so the column reads
  from "we counted this" down to "we cannot see this".
- **`?`** — the keyboard overlay. Two seconds, and it reads as a tool rather
  than a web page.

---

## The recorded video quotes the ten-name numbers

The universe was widened from ten names to eighteen AFTER the video was shot,
which moved every headline figure slightly: the break point from −24.69% to
−25.05%, the direct loss from 7.23% to 7.33%, amplification from 1.38× to
1.36×, the fix from $478 to $472. Nothing changed direction and nothing changed
by more than half a point, but the video and the live app now disagree in the
second decimal.

If anybody notices, the true answer is a good one: *the model covers eighteen
securities now instead of ten, so a real brokerage export is modellable and the
cascade has more paths through it.* Do not claim the video matches.

The table below is the LIVE build, not the video.

## The numbers, verified against this build

Speak these or none. Every one was read off the engine while writing this file.

| | |
|---|---|
| demo book | $12,300, 5 holdings |
| break point | NVDA **−25.05%** |
| direct loss | **7.33%** |
| after cascade | **10.00%** |
| amplification | **1.36×** over **3** rounds |
| books breached | **5 of 5** |
| the fix | sell **$472** of NVDA — 13.1% of a $3,600 position |
| same shock, defended | 10.00% → **9.00%** |
| break point, defended | −25.05% → **−28.17%** (3.07 pp further out) |
| 400 scenarios | stayed under the limit **395 → 398** |
| worst of 400 | 11.94% → **10.73%** |
| boundary | **108 of 256** cells amplify; worst **3.10×** |
| headroom | **−0.03×** |
| data | SEC 13F-HR, period 06-30-2026, 5 managers, 10 names |

---

## Do not film

- **Anything at a 25% limit** unless you mean to. The demo book has no break
  point there and the app correctly says so rather than inventing one. A good
  beat on purpose; a confusing one by accident.
- **The MATLAB line** unless you have run the MATLAB step. Otherwise the Model
  page honestly reads `Python fallback · MATLAB not found`.
- **The word "pattern search"** unless the card says `patternsearch`. Rice's
  published TAH bundle lists Optimization Toolbox and not Global Optimization
  Toolbox, so the likely readout is `MATLAB · fmincon`. The card reports
  whichever solver ran and the narration has to match it. See
  `matlab/README.md`: the "why MATLAB" argument is a direct-search argument,
  and `fmincon` does not get to make it.
- **A green tick anywhere.** There is no green in this build, by design. A
  passing check is set in ink like every other figure, and red means one thing
  only: a limit was crossed. If the narration says "green means safe", it is
  describing a different app.
