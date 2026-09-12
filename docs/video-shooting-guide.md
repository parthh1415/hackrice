# Video shooting guide

`docs/video-script.md` was written against the single-page institutional app —
three sliders, a solver strip, a phase diagram, a split screen, a modal. The
frontend is now six linked pages. **12 of its 21 numbered shots point at UI that
no longer exists.**

The script's *numbers* are not the problem: every figure in it was re-verified
against the engine and they are all still correct. The problem is that several
are described as things a viewer sees on screen, and they are not.

This file says what to film instead. Everything below was checked against the
running app, not against the source.

---

## What the app is now

Six pages, reachable from the nav or by pressing `1`–`6`:

| key | page | what it answers |
|---|---|---|
| `1` | Portfolio | what are we stress testing |
| `2` | Analysis | what breaks it, and where the loss comes from |
| `3` | Cascade | why the loss grows |
| `4` | Defend | the cheapest single-position change |
| `5` | Verify | did it actually help |
| `6` | Model | what is measured, what is declared, what computed the patch |

Also: `←` / `→` step the cascade, `space` plays it, `?` lists the keys. A bottom
status bar shows the shortcuts, the book, and the dataset.

Any page can be opened demo-ready with `?demo` — e.g.
`localhost:8765/cascade.html?demo`. That is the reliable way to set up a shot
without filming yourself clicking through to it.

---

## The demo path, as a presenter walks it

This route is covered by an automated check that fails if any step breaks, so
it is safe to rehearse against.

1. `localhost:8765/index.html` — press **Use demo portfolio**
2. press **Run reverse stress test** → Analysis
3. press **See why the loss grows** → Cascade
4. press **Find the cheapest single-position fix** → Defend
5. press **Check it actually helped** → Verify

---

## Shot by shot

`OK` = film as written. `RETARGET` = same beat, different screen.
`GONE` = the screen does not exist.

| shot | verdict | what to do |
|---|---|---|
| 1.1 | **OK** | Title slide. |
| 1.2 | **OK** | Slide. |
| 1.3 | **GONE** | No network, sliders, rail or hero on the landing page. Open `index.html?demo` and hold on the portfolio table — five holdings, and a crowding column reading `0.3 / 0.4 / 0.7 / 0.9 days of volume`. |
| 2.1 | **GONE** | No network on this screen, no control strip. Assumptions is a nav link labelled **Model** leading to a page, not a modal over the stage. |
| 2.2 | **GONE — the worst one** | Narrated as "three sliders, both adjustable, both on screen the whole time". λ, γ and band are not adjustable anywhere. They *are* now printed on the Model page (`Gross leverage · 5.0×`, `Breach band · 1.05× target, so a book sells above 5.25×`, `Price impact · γ = 0.2`), so the "we show our assumptions" claim survives — the "watch me change them" claim does not. Rewrite or cut. |
| 2.3 | **RETARGET** | `index` → **Run reverse stress test** → Analysis. Hero reads **NVDA −24.69%** (portfolio mode), not −5.27%. No solver strip, no count-up, so the 0.52s hold note is moot. |
| 2.4 | **RETARGET — better than written** | Cascade page. **Prev / Play / Next**, or `←` `→` `space`. Steps at 900ms, does not auto-play. The edges now carry the forced selling for that round, so the picture visibly dies out: `$8.7B → $2.5B → $818M`. At −24.69% **four** funds breach in round 1 — Citadel, Millennium, Two Sigma, Renaissance. |
| 2.5 | **WRONG NUMBERS** | At −24.69%: four breach at round 1, Point72 joins at round 3, **5 of 5** breached, 3 rounds, amplification 1.38× on the portfolio. |
| 2.6 | **GONE — but replaced** | The Point72 "never turned red" zoom has no screen; Point72 does breach at this shock. **Film the attribution table on Analysis instead.** MSFT, AMZN and GOOGL show `—` under *Shocked* and still carry a *From contagion* fall that lands in *Costs you*. Same thesis, more directly: damage arriving through other people's liquidation. |
| 2.7 | **GONE** | No boundary UI. `/api/boundary` returns the grid, nothing fetches it. |
| 2.8 | **GONE** | Same missing screen, and no slider to demonstrate the band with. |
| 2.9 | **RETARGET** | Defend. **"Sell $478 of NVDA"**, 13.3% of a $3,600 position, over a Loss before / Loss after / Your limit / Share of book moved strip and a before-and-after table that **foots to the same total** — which is a better proof than the old caption. |
| 2.10 | **GONE, no substitute** | "Notice who it isn't" — patching the fund that breaches *second* because it is the biggest book. Portfolio mode always fixes a name in the user's own book, so this argument has no screen. If you want it, build a slide from `/api/stabilise?leverage=5&gamma=0.2&band=1.05&breaches=3`. It is one of the script's strongest beats; losing it costs something. |
| 2.11 | **RETARGET** | Verify §1 is a two-column table (Current book / Defended book) at −24.69%: identical shock both sides, **10.00% → 9.00%**, and Breach / Within-limit badges *derived* from the replay rather than written in. No 2.6s split animation, so the scripted silence becomes a presenter pause. |
| 2.12 | **RETARGET** | The `bought` line is a row on the Model page: *What it bought the funds*. Note it runs at the session's breach count, so in portfolio mode it reads `−4.60% → −4.60% · no measurable change`, not `5.27% → 5.28%`. The point is unchanged and the honesty is the same. |
| 3.1 | **OK** | Architecture slide. Contents verified: six registrants across five firms, options rows filtered, aggregation by CUSIP, engine genuinely a pure function. |
| 3.2 | **RETARGET — wording only** | `matlab/stabilise.m` exists. The readout is a **card**, not a strip: "What computed the institutional patch" on the Model page. Narration survives verbatim. |
| 3.3 | **RETARGET** | Not a masthead modal — a nav link labelled **Model**. The eight tagged rows are there and now print their values. Two things the script describes are absent: a **Scale / ~$8.2B system equity** row, and the "1.02 gives −1.73%, 1.30 gives −27.33%" sentence. **Better target:** Analysis's *"What this does not say"* table — header prints `NVDA −24.69% · limit 10% · λ 5.0× · band 1.05× · γ 0.2`, then Not a probability / Not a threshold / One name at a time / Your book is an observer. The honesty beat in one frame, on the page that just made the claim. |
| 4.1 | **GONE** | No phase diagram. Cut to the cascade's final frame. |
| 4.2 | **OK** | Slide. "Bystander exposure view" now undersells you — CSV import works and the user's portfolio *is* the bystander. Reword or drop that bullet. |
| 4.3 | **WRONG NUMBERS** | The hero is **NVDA −24.69%** and **5 of 5** books breach. The closing line has to change with it. |

---

## Film these — they did not exist when the script was written

1. **The attribution table** (Analysis). Weight · Shocked · Total fall · From
   contagion · Costs you, summing to exactly the portfolio loss. GOOGL falls
   5.31% having never been shocked. This is the thesis as arithmetic.
2. **The crowding column** (Portfolio). `0.9 days of volume` in GOOGL against
   `0.3` in NVDA, before anything is run — the mechanism previewed on the first
   screen, and the reason GOOGL is the one that bleeds.
3. **The forced-selling flow** (Cascade). Press `3` then `space`. The red edges
   are dollars sold that round and they visibly thin out.
4. **The footing table** (Defend). Current and Defended both total $12,300 —
   "worth the same afterwards" made checkable rather than asserted.
5. **"What this does not say"** (Analysis). Four caveats as rows, with the run's
   parameters in the header.
6. **`?`** — the keyboard overlay. Two seconds, and it reads as a tool rather
   than a web page.

## Do not film

- Anything at a 25% limit unless you mean to: the demo book has no break point
  there, and the app correctly says so rather than inventing one. It is a good
  beat if you want it, and a confusing one if you hit it by accident.
- The MATLAB line unless you have run the MATLAB step. Otherwise it honestly
  reads `SciPy-free Python · exhaustive position scan` /
  `MATLAB not available on this machine`.
