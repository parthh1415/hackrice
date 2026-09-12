# Firebreak — demo video script

> **STALE — read `docs/video-shooting-guide.md` first.** This script was written
> against the single-page institutional app: three sliders, a solver strip, a
> phase diagram, a split screen and a modal. The frontend is now six linked
> pages and **12 of the 21 numbered shots point at UI that no longer exists**.
> The numbers below are still correct *for the institutional endpoints* — they
> were re-verified — but several of them are no longer things a viewer sees on
> screen, which is a different claim. The shooting guide says, shot by shot,
> what survives, what to retarget, and what to cut.


**Target length:** 3:42. Hard ceiling 4:00.

> **⚠ The script does not currently fit, and the per-shot timecodes below are a target, not a
> measurement.** Counted at the stated 150 wpm, the spoken lines alone run **7:08**; with the marked
> ⏸ silences it is about **7:25** — twice the ceiling. *Every single shot* is over its slot. The
> worst are 2.12 (12s allotted, 42s of words), 3.3 (10s / 34s), 2.6 (13s / 30s), 2.2 (6s / 27s),
> 4.2 (12s / 26s), 3.1 (10s / 24s), 4.1 (12s / 23s), 3.2 (10s / 22s). **51% of the words have to come
> out** before this is recordable. That is a writing decision, not a pacing one — do not try to solve
> it by speaking faster, and do not solve it by cutting Shot 2.12.
>
> Full accounting, timed 2026-09-12: spoken lines **7:08** at the script's own 150 wpm, plus **10s**
> of marked ⏸ silences, plus **3.4s** of clicking and animation that the app makes you wait for —
> **7:22 end to end** against a 3:42 claim and a 4:00 ceiling. Note where that time is *not*: the
> app costs under four seconds in total. Every second over is narration.

**Required HackRice structure:** 30s intro · 2min demo · 30s technical design · 30s impact and future.

**Before you record**

- Sliders at the golden path: gross leverage **5.0**, price impact **γ = 0.20**, failure condition
  **3 or more funds breach**, and the breach band at its default **1.05**. Every number below is the
  live output at those settings. If you move a slider, the numbers change and this script is wrong.
- **The band is a slider now** — `Breach band`, third knob down the rail, range 1.0–1.5 step 0.01,
  default 1.05. It is on camera the whole time like the other two and no longer needs a URL
  parameter. Leave it at 1.05 for the run. It swings the hero harder than either of the others
  (1.02 → −1.73%, amp 3.10; 1.30 → −27.33%, amp 1.43), which is exactly why Act 3 names it as a
  declared parameter.
- **Read numbers off the screen, not off this script's underlying floats.** The app rounds, and
  saying a float over a display that shows something else is the fastest way to lose a judge. The
  full rendered set at the golden path, verified live 2026-09-12 — **this is the authority; if a
  line in this script disagrees with the table, the table wins**:

  | on screen | reads | rendered by |
  |---|---|---|
  | hero | `5.27%` | 2 dp |
  | hero sub | `NVDA · 4 of 5 funds forced to sell` | counts |
  | metrics band | `Shock loss 4.9%` · `After cascade 9.1%` · `Amplification 1.87×` · `Breaches 4` · `Rounds 3 / 3` | losses 1 dp, amp 2 dp |
  | round label | `round 3 / 3` | integers |
  | asset label, NVDA, at t0 | `−5.27%` | 2 dp |
  | asset label, NVDA, at round 3 / 3 | `−5.76%` | 2 dp |
  | fund labels at t0 | `L 5.18` `L 5.36` `L 5.03` `L 5.15` `L 5.25` | 2 dp |
  | fix line | `Citadel: sell $1.7M of NVDA · 0.073% of a $2.4B position · costs 0.0042% of gross assets` | dollars 1 dp + unit, percentages 2 significant figures |
  | split feet | `9.1% loss · 4 breaches · amp 1.87×` / `6.5% loss · 2 breaches · amp 1.33×` | loss 1 dp, amp 2 dp |
  | shock stamp | `identical shock · 5.27% NVDA` | 2 dp |
  | boundary marker | `L 5.0 · overlap 0.71` | 1 dp / 2 dp |
  | boundary axes | `1.5`–`8.0`, `0.00 · 0.72 · 1.00` | 1 dp / 2 dp |
  | boundary title | `amplification · contour at 1.5× · single-name 5% reference · band 1.05` | 1 dp / 2 dp |
  | solver, after attack | `grid scan + bisection` · `names 10 · step 1.0% · <n>ms` | — |
  | solver, after boundary | `parameter sweep` · `cells 256 · <n>ms` | — |
  | solver card, Model page | `SciPy-free Python · exhaustive position scan` · `MATLAB not available on this machine` · evals and solve time as shown | — |
  | | NOTE: `124 evals` is the **>=3 breach** figure. The Model page runs at the session's own breach count, which in portfolio mode is 2, and shows **301**. Read what is on screen. | |
  | bought line, above the split | `critical distance 5.27% → 5.28% · no measurable change (difference of two searches has to clear 0.01pp) — defends this shock, not the next one` | 2 dp / 3 dp |
  | sliders | `5.0`, `0.20` and `1.05` | 1 dp / 2 dp / 2 dp |

  ✅ **The `0%` bug flagged here last pass is fixed.** The fix line used fixed-decimal formatters,
  so once the answer got small it printed `cut NVDA exposure 0% · costs 0.00% of gross assets` —
  the one sentence the beat exists to produce, telling a PM to cut nothing. It now leads with the
  dollar amount and formats both percentages to two significant figures, so it reads as a trade
  rather than a rounding error. Beat 4 is recordable.

  **The hero has no minus sign.** It renders `5.27%` under the label *Critical shock distance*, and
  the split stamp reads `identical shock · 5.27% NVDA`. Where this script writes "NVDA −5.27%" that
  is shorthand for the shock, not a quotation of the screen. The minus only appears on the NVDA
  *asset node* label (`−5.27%` at t0). Don't point at the hero and read a sign that isn't on it.

  Nothing else in this script is a screen value. Two things you still have to make: the Point72
  overlay in Shot 2.6 and the architecture diagram in Shot 3.1. The other two are in the product
  now — `bought` renders as a line above the split (Shot 2.12) and the assumptions live behind the
  **Assumptions** button in the masthead (Shot 3.3), so both of those beats are live app, not slides.
- Run the loop once to warm the cache. Serve with the cached demo path so wifi cannot kill you.
- **The app runs the attack by itself at boot.** By the time the page has settled, the hero already
  reads `5.27%`, the metrics band is filled and the timeline is parked on `round 3 / 3`. There is no
  blank idle state to open on. Either open on a fresh reload and start talking over the boot run, or
  accept that Shot 2.3's click is a *re-run* of an answer already on screen — it does replay the
  count-up and the cascade from round 0, so the reveal still reads. Just don't describe the opening
  frame as empty.
- Browser at 1280×800, zoom 100%, no tab bar clutter, no notifications.
- Speak at roughly 150 words per minute. The lines below are timed for that.
- **⏸ marks a deliberate silence.** Do not talk over the cascade. The animation is the argument.

---

## ACT 1 — INTRODUCTION (0:00 – 0:30)

### Shot 1.1 · 0:00 – 0:08
**On screen:** Firebreak title card. Below it: team member names, "HackRice 16 · Finance track ·
Capital One challenge · MathWorks challenge".

> "This is Firebreak. I'm [NAME], with [NAME] and [NAME]. We built it for the Finance track at
> HackRice 16, and we're also entering the Capital One and MathWorks challenges."

### Shot 1.2 · 0:08 – 0:21
**On screen:** Cut to a plain slide, two lines of text appearing one at a time:
`Stress test: what if NVDA drops 20%?` then `Firebreak: what is the smallest drop that breaks us?`

> "Every stress test asks the same shape of question. What if this happens? The scenario is the
> assumption, and the assumption is the part nobody checks. Firebreak asks the inverse. What is the
> smallest shock that breaks this system, and what is the cheapest change that prevents it."

### Shot 1.3 · 0:21 – 0:30
**On screen:** The live app as it lands. Five fund nodes, ten asset nodes, edges visible. Three
sliders, the failure-condition select and the solver strip legible down the left rail. **Not idle —
the app has already run the attack for itself**, so the hero reads `5.27%` and the timeline is
parked on `round 3 / 3` before you have touched anything.

> "Real holdings from five hedge funds' SEC 13F filings. A Python cascade engine, MATLAB pattern
> search for the optimisation, and a plain JavaScript front end. Purpose: find the failure before it
> finds you."

---

## ACT 2 — DEMO (0:30 – 2:42)

### Beat 1 — ATTACK (0:30 – 0:57)

#### Shot 2.1 · 0:30 – 0:44
**On screen:** Cursor traces across the bipartite network, then rests on the control strip.

> *The provenance is in the app now. **Assumptions** sits in the masthead next to the badge and opens
> a panel whose first row reads "measured · Holdings — Real, and the only thing here that is. SEC
> 13F-HR, period 2026-06-30, 5 managers across 10 names, $40.9B gross notional." One click, Escape or
> Close to dismiss. You can open it here or save it for Shot 3.3, but don't claim a strip on the
> stage — it is a modal over the network, not a band under it.*

> "Citadel, Millennium, Point72, Two Sigma, Renaissance. Ten mega-cap names. These are their real
> filed books, second quarter twenty twenty-six. Mean pairwise overlap between these five portfolios
> is zero point seven one. Citadel and Two Sigma are at zero point nine two. Nearly the same fund."

#### Shot 2.2 · 0:44 – 0:50
**On screen:** Cursor down the rail. Leverage `5.0`, γ `0.20`, Breach band `1.05` — three sliders,
all three highlighted briefly.

> "Leverage and price impact aren't in a 13F, so they're ours. Five times gross, impact coefficient
> zero point two, both adjustable, both on screen the whole time. And a third one — how far over
> its limit a fund runs before it's forced to sell. One point oh five. I'll come back to it, because
> it moves this number more than either of the others."

> *All three are sliders on the rail; the band is no longer hidden in a URL. Don't say "we hold that
> at" as though it were a constant you couldn't reach — it is the knob directly under γ.*


#### Shot 2.3 · 0:50 – 0:57
**On screen:** Click **Find weakest shock**. Solver strip ticks over. The hero number lands:
**NVDA −5.27%**.

> "Failure means three or more funds breach. Find me the smallest single-name drop that does it."
>
> ⏸ *(let the number land. The count-up is **0.52s**, not 1.5 — `countTo` runs a 520ms ease from
> 0.00% up to 5.27%, two decimals the whole way. Hold longer than that if you want the pause, but
> know you are holding on a settled number, and know the cascade has already started behind it.)*
>
> "NVIDIA, down five point two seven percent. That's not a crash. That's a bad Tuesday."


### Beat 2 — CASCADE (0:57 – 1:32)

#### Shot 2.4 · 0:57 – 1:10
**On screen:** Cascade plays. Round counter visible. Millennium and Renaissance turn red in round 1.
**Presenter is silent for the first two rounds.**

> *⚠ **This needs a click the script never mentions.** The cascade starts by itself 260ms after the
> attack returns and is over 3.2s later — which is *during* Shot 2.3's spoken line, not after it. By
> the time you say "that's a bad Tuesday" the network has been sitting on its final frame for about
> nine seconds. To have anything to be silent over here you must press **Replay cascade** (second
> button on the rail) at the top of this shot. Either put that click in, or move the whole of 2.3's
> narration before the click and let 2.4 be the first thing the cascade hears.*

> *The UI is monochrome plus exactly one red (`--alert #FF383B`). Healthy nodes are dim white,
> stressed nodes are full white, breached nodes are red. There is no amber or ember in the product —
> don't say those words on camera.*

> "Watch it move."
>
> ⏸ *(full silence through round 1 and round 2 — which is **2.2 seconds**, not six. The step is
> 1020ms: round 1 lands ~0.3s after the click, round 2 at ~1.3s, round 3 at ~2.3s, and the whole
> cascade has settled by ~3.2s. If you hold six seconds of silence you are holding three seconds of
> a frozen final frame. Either come in at 2.2s or cut back to round 0 and let it play twice.)*
>
> "Millennium and Renaissance breach first. They're the two heaviest in NVIDIA. To get back under
> their limits they sell across the whole book, not just the name that fell. Everything they own
> ticks down."

#### Shot 2.5 · 1:10 – 1:19
**On screen:** Round 2, Citadel turns red. Round 3, Two Sigma turns red. Final state holds.

> "Nobody shocked Citadel. Citadel breaches in round two because of what Millennium had to sell. Two
> Sigma goes in round three. Four of five funds, three rounds."

#### Shot 2.6 · 1:19 – 1:32
**On screen:** Zoom to the Point72 node, which never turned red. Its only on-screen readout is its
leverage label, which **starts** at `L 5.03` and **ends** at `L 5.24` — it is the one fund whose
leverage goes *up* across the cascade, because its equity falls and it never sells. That is worth
the zoom on its own. **Add the three numbers as an overlay in the edit** —
`NVDA weight 2.8% · direct loss 0.75% · total loss 5.70%`. The app renders none of them; they are
derived from the trajectory and this beat depends on them, so build the overlay rather than pointing
the cursor at something that isn't there.

> "But look at Point72. It holds two point eight percent NVIDIA, the smallest position in the system.
> The shock itself costs it three quarters of one percent of equity."
>
> ⏸ *(beat)*
>
> "It ends down five point seven. Seven and a half times its own exposure. It never breached. It never
> sold a share. That damage is entirely other people liquidating names it happens to share with them.
> That's the part a single-fund stress test cannot see."

**On screen at 1:30:** Metrics panel reads `Shock loss 4.9% · After cascade 9.1% · Amplification
1.87× · Breaches 4 · Rounds 3 / 3`. The underlying floats are 4.88% and 9.12%; the band rounds to one
decimal. Say "nearly five percent" and "just over nine", or read the screen — do not say "four point
eight eight" over a display that reads 4.9%.

### Beat 3 — BOUNDARY (1:32 – 1:57)

#### Shot 2.7 · 1:32 – 1:42
**On screen:** Click **Map the boundary**. The sweep runs server-side, then the whole 16×16 grid
appears at once. Axis labels read `1.5` to `8.0` up the side and `0.00 · 0.72 · 1.00` along the
bottom, with `amplification · contour at 1.5× · single-name 5% reference · band 1.05` in the top
right, and a white contour line traced across the plot.

> *It does **not** fill in cell by cell — `drawBoundary` paints all 256 rects, the contour and the
> marker in one synchronous pass, so the grid pops. Don't promise a fill-in in the edit, and don't
> promise a wait either (see below).*

> "Fair question: did we get unlucky, or is the structure the problem? So sweep it. Leverage from one
> and a half to eight. Crowding from every fund holding something different, through the books
> exactly as filed, all the way up to every fund holding the same thing."
>
> ⏸ *(there is **no** wait. The sweep returns in under 50ms warm or cold, and `drawBoundary` paints
> all 256 rects plus the contour in one synchronous pass, so the grid is on screen within about a
> twentieth of a second of the click. Don't write dead air into the edit and don't say "give it a
> moment" — there isn't one. If you want a beat here it has to be a presenter pause on a grid that
> is already up.)*

#### Shot 2.8 · 1:42 – 1:57
**On screen:** The marker — a white ring and dot, captioned `YOU ARE HERE` over `L 5.0 · overlap
0.71` on a dark plate — lands just above the white 1.5× contour, near the middle of the horizontal
axis (which is nonlinear: the middle column is overlap 0.72, not 0.50 — that's what the third axis
tick is for).

> *There **is** a contour now. `drawBoundary` shades each cell into one of five bands (amplification
> < 1.05, < 1.30, < 1.80, < 3.00, above) **and then runs marching squares at 1.5× and strokes the
> crossings in white** — 29 short segments at the golden path. The title in the top right names it:
> `amplification · contour at 1.5× · single-name 5% reference · band 1.05`. So "the contour" is a
> thing you can point at and a word you are allowed to say. Say **1.5×** if you name the level; do
> not say 1.80 — that was the old shading step, and it is not where the line is drawn.*

> "Every cell is a full cascade, computed, not drawn. And there's a boundary. Below it the shock gets
> absorbed. Above it, it runs. You are here."
>
> ⏸ *(beat on the marker)*
>
> "Right on the edge. Which means this isn't bad luck. It's a place you're standing. And if it's a
> place, you can move."

> *Say "below / above", not "one side / the other". The sharp transition is in **leverage** — at the
> filed overlap column, amplification is flat at 1.00 all the way up to λ≈4.1, is 1.16 at λ≈4.5 and
> 1.86 at λ≈5.0, and the 1.5× contour crosses at **λ≈4.7**. (Not "1.00 at 4.5" — 4.5 is already off
> the floor.) Along the crowding axis the
> reference shock is single-name, so amplification is not monotone in crowding. If a judge points at
> the right-hand columns and asks why they're cooler, that's why: blending toward the mean dilutes
> the shocked name. Don't claim a crowding threshold on camera.*
>
> *And don't oversell "right on the edge". Where the leverage boundary sits is set by the breach band
> we chose. The sweep honours `band`, so you can show this — measured off the 1.5× contour at the
> filed overlap column: band 1.02 puts it at **λ≈2.7**, band 1.05 at **λ≈4.7**, band 1.10 at
> **λ≈7.7**, and at band 1.30 the filed-overlap column never leaves 1.00 — only the top row, λ=8.0,
> cascades at all (16 of 256 cells amplify, 12 of them cross 1.5×). Do **not** say "nothing in the
> grid cascades" at 1.30; something does, it is just nowhere near where we are standing. The map's
> shape is the finding; the marker sitting near the line at band 1.05 is partly a consequence of
> picking 1.05. If a judge presses, concede it immediately — "that's a parameter we declared, and
> here's how much it moves" is a much better answer than defending the coincidence.*
>
> *Demonstrating it live is now a drag, not a URL: pull the **Breach band** slider and press **Map
> the boundary** again. Nothing to type on camera. The sweep is instant, so the grid redraws under a
> new title reading `… · band 1.30` and the contour disappears off the top of the plot entirely.
> **Use 1.02 or 1.30** if you do this — those, plus 1.15, are the only bands in the golden cache
> (`data/cache/golden/boundary__band=*`); anything else computes live, which is also instant but is
> not the cached path. Put the slider back to 1.05 before Shot 2.9 or every number after it is
> wrong.*


### Beat 4 — DEFEND (1:57 – 2:42)

#### Shot 2.9 · 1:57 – 2:08
**On screen:** Click **Stabilise**. The solver strip updates — `SciPy-free Python · exhaustive
position scan`, `MATLAB not available on this machine`, and an evaluation count that depends on the
breach count the session ran at (301 at 2+, 124 at 3+) — unless you have
done the MATLAB step, in which case it reads `MATLAB · patternsearch`. The instruction line
resolves in about a tenth of a second:
`Citadel: sell $1.7M of NVDA · 0.073% of a $2.4B position · costs 0.0042% of gross assets`
and the `bought` line lands **immediately underneath it, at the same moment** — see Shot 2.12. You
cannot hold it back, so don't plan a reveal.

> "Now run it backwards again. Same failure condition, same shock. What is the smallest change
> anywhere in this system that gets us under it?"

>
> ⏸ *(let the instruction render)*
>
> "Citadel sells one point seven million dollars of NVIDIA. Out of a two point four billion dollar
> position — seven hundredths of one percent of it. Four ten-thousandths of one percent of the
> system's gross assets."




#### Shot 2.10 · 2:08 – 2:18
**On screen:** Cursor underlines **Citadel** in the instruction, then flicks to the Citadel node —
which did *not* breach in round one.

> "Notice who it isn't. Millennium and Renaissance are the two funds that breach first. The fix is in
> neither of them. It's Citadel, which doesn't go until round two — and it's seven hundredths of one
> percent of a single position. Citadel is the largest book here, so the smallest fractional cut anywhere in
> the system is the one that takes the most dollars out of round two's selling. That is not the move
> anyone would guess, and it's why you solve it instead of guessing."

> *⚠ The old version of this beat said "notice it isn't NVIDIA — the cheapest fix is in Alphabet".
> That is backwards now. The answer at the golden path is **Citadel · NVDA · 0.0732%** — $1,731,560
> out of a $2,364,156,792 position, costing 0.0042% of the $40.9B gross book. The fix **is** the
> shocked name.*
>
> *This number has now moved twice, so check it rather than trusting any prose. Anything quoting
> GOOGL, "five percent" or "four basis points" is the old 5%-grid answer; anything quoting 0.15625%,
> 0.16%, 0.009%, 0.01% or 33 evals is the answer from before the depth tolerance was made relative
> (`_DEPTH_RTOL = 0.02`, `_DEPTH_FLOOR = 1e-7`). The absolute 0.002 tolerance was halting with a
> bracket wider than the answer it reported and printing the top of it — 2.15× the true minimum, on
> the one number the product exists to produce.*
>
> *Verified: Citadel $14.6B of the $40.9B total; Two Sigma $9.2B, Millennium $7.7B, Renaissance
> $6.3B, Point72 $3.1B. Citadel's NVDA position is 16.2% of its own book. Round-one breachers are
> Millennium and Renaissance — don't say "the" fund. Crowding rank, if a judge asks, is unchanged:
> NVDA 26%, AMZN 26%, GOOGL 15% of total pairwise overlap.*


#### Shot 2.11 · 2:18 – 2:30
**On screen:** Split screen. Both sides run **NVDA −5.27%**, the identical shock stamped underneath
both panels (`identical shock · 5.27% NVDA`). Left foot: `9.1% loss · 4 breaches · amp 1.87×`.
Right foot: `6.5% loss · 2 breaches · amp 1.33×`.

> "Same shock, both sides. Before: four funds, three rounds, nine point one percent of system equity
> gone."
>
> ⏸ *(hold on the split, ~2s)*
>
> "After: two funds, one round, six point five. Amplification one point eight seven down to one point
> three three. For one point seven million dollars — seven hundredths of one percent of one
> position."


>
> *Say "two funds", never "it survives". Millennium and Renaissance still breach — the fix clears the
> condition we asked about, which was three or more. If you say "survives" over a panel reading
> "2 breaches", you are contradicting your own screen.*


#### Shot 2.12 · 2:30 – 2:42  — **NEW. Do not cut this one.**
**On screen:** No slide. Stay on the split and push in on the `bought` line sitting above it, which
has been on screen since the fix line landed. It reads, verbatim:
`critical distance 5.27% → 5.28% · no measurable change (difference of two searches has to clear 0.01pp) — defends this shock, not the next one`

> "And here's the part we'd rather say than have you find. The stabiliser re-runs the search against
> the patched books. The smallest shock that breaks us doesn't measurably move. Three point seven
> million dollars of NVIDIA clears *this* failure condition against *this* shock, and buys us nothing
> we can measure against the next one."
>
> ⏸ *(beat)*
>
> "That's a targeted patch, not structural repair, and it's what a one-position, one-scenario
> optimiser is honestly capable of. The fix for that isn't a slider. It's a different objective —
> maximise the smallest shock that breaks you, instead of minimising the cost of surviving one you
> already named. That's the next build."

> *Where this comes from: the `bought` object on `/api/stabilise` — `before_pct` 5.2734,
> `after_pct` 5.2773, `delta_pct` +0.0039, `resolution_pct` 0.005, `measurable: false`, note
> `"no measurable change in break point — a targeted patch, not structural repair"`. `showBought()`
> renders it; it is live, and it is on screen from the moment Stabilise returns.*
>
> **Do not read the arrow out loud.** The screen prints `5.27% → 5.28%`, but the delta behind it is
> +0.0039pp against the 0.01pp a difference of two searches has to clear — inside its own error bar. The line's own second
> half is the claim that survives: **"no measurable change"**. Say that, and if the cursor is
> anywhere near the arrow, say why it doesn't mean anything. *(Flagged to the team: the app printing
> `5.28%` at all is the same fake-precision mistake the hero number was fixed for, one level up. If
> it gets changed before you record, re-check this line.)*
>
> **Do not demonstrate this by clicking Find weakest shock after Stabilise.** `/api/break` reloads
> the dataset from disk, so it re-searches the **unpatched** books — it would print 5.27% again for
> the wrong reason and you'd be showing the right conclusion off a broken mechanism. The button is
> perfectly clickable and takes about 3.2 seconds; that is exactly the trap. The `bought` line
> already says the thing, live. Use it.*


---

## ACT 3 — TECHNICAL DESIGN (2:42 – 3:12)

### Shot 3.1 · 2:42 – 2:52
**On screen:** Architecture diagram, four boxes left to right: `ingest → engine → search → ui`, with
`engine` labelled "pure function (H, λ, γ, s) → trajectory".

> "Four units. Ingest pulls the 13F XML off EDGAR for six registrants across five firms, filters out
> options rows, aggregates by CUSIP. The
> engine is a pure function: holdings, leverage, impact, shock, in; full trajectory out. Everything
> else treats it as a black box, which is what let us build the optimiser and the front end at the
> same time."

### Shot 3.2 · 2:52 – 3:02
**On screen:** `matlab/stabilise.m` open, `patternsearch` call highlighted. Cut to the solver strip
in the app showing the live solver name, evaluation count and status. It is a CARD on the Model
page now — "What computed the institutional patch" — not a strip on a rail.

> "The search is the product. Forward, breach count is monotone in shock size, so a grid scan brackets
> the threshold and bisection refines it. Backwards, the objective is a simulation. No gradient,
> piecewise-constant landscape, discrete feasible set. That's MATLAB pattern search, and the app tells
> you which solver actually produced the number on screen."

### Shot 3.3 · 3:02 – 3:12
**On screen:** Click **Assumptions** in the masthead. The panel opens instantly over the stage with
eight rows, each tagged `measured`, `declared` or `limit`, filled from the live payload — Holdings
(SEC 13F-HR, 2026-06-30, 5 managers, 10 names, $40.9B), Leverage (5.0×), Breach band (1.05, reading
"At these settings, 1.02 gives −1.73% and 1.30 gives −27.33%" — the row shows that pair only at
leverage 5.0 with ≥3 breaching, and names those settings instead when you are anywhere else, because
the pair is a measurement and it drifts), Price impact (γ = 0.20), ADV,
What 13F omits, Scale (~$8.2B system equity, "the mechanism transfers; the magnitude does not"),
Not a prediction ("not a proven threshold"). *No slide needed — this is the product now.* Escape or
**Close** puts it away.

> "And the honesty is not an afterthought. We do not predict market moves. Leverage is not in a 13F,
> it's our parameter. Neither is the breach band, the one I flagged earlier — that's ours too, it
> defaults to one point oh five, and it moves the headline number more than leverage or impact do.
> Thirteen-F is long-only, quarterly, forty-five days late. The claim is that the boundary exists and
> moves predictably, not that any one point on it is the truth."


---

## ACT 4 — IMPACT AND FUTURE (3:12 – 3:42)

### Shot 4.1 · 3:12 – 3:24
**On screen:** Back to the phase diagram with the marker on it.

> "Reverse stress testing is already mandatory. UK PRA, EBA guidelines: firms have to find the
> scenarios that break them. They mostly do it by hand, on one balance sheet at a time. Nothing does
> it interactively across portfolios that overlap, and overlap is exactly where the 2007 quant quake
> and every crowded-trade unwind since actually happened."

### Shot 4.2 · 3:24 – 3:36
**On screen:** Short list appears, in the order it is spoken: robust defence over a family of
shocks · multi-asset shocks · systemic-importance ranking · bystander exposure view.

> "Next, and first: a stabiliser that maximises the smallest shock that breaks you, instead of
> minimising the cost of surviving one you already named. Then shocks across several names at once,
> ranking which single asset is most dangerous to the whole configuration, and a view for people who
> hold these names with no leverage. They can't be forced to sell. They still pay for it."


### Shot 4.3 · 3:36 – 3:42
**On screen:** Back to the hero number, NVDA −5.27%, then the title card.

> "Five point two seven percent on one name, and four of five funds breach. The point isn't that
> number. The point is that you can go looking for it. Firebreak."


---

## Recording notes

- **Do not** talk during Shot 2.4's first two rounds or during the Shot 2.11 split-screen hold. Those
  two silences are what make the demo land — but know how long they actually are. Rounds 1 and 2 of
  the cascade take **2.2 seconds**, not six; the whole cascade settles at 3.2s. The split takes
  **2.6s** end to end. Hold silence for the real duration, not the one the old script imagined.
- **Shot 2.12 is not optional and not a caveat to mumble.** Being the first to say what the fix
  doesn't buy is worth more than the fix. If you are cutting for time, cut Act 4's list instead.
- Nothing in this app is slow. Every endpoint returns in under 50ms warm or cold; the only waits on
  screen are animations we chose. Use the cached demo path anyway so a wifi failure can't reach the
  server, but do not write "wait for it" into the edit anywhere — there is nothing to wait for.
- If asked live where leverage comes from, the answer is one sentence: it is not in the filing, it is a
  declared parameter, and it is the slider on screen.
- Numbers verified live 2026-09-12 by driving the real `web/app.js` against the real server and
  reading the rendered DOM, at leverage 5.0, γ 0.20, band 1.05, breaches ≥ 3. Re-run before recording and correct any drift rather than
  reading these from the page. Verified this pass — **screen value first, float in brackets**:
  hero NVDA −5.27% (5.2734); shock loss 4.9% (4.876%); after cascade 9.1% (9.122%); amplification
  1.87× (1.8710); 4 breaches, 3 rounds; order Millennium+Renaissance → Citadel → Two Sigma, Point72
  never; Point72 2.8% / 0.75% / 5.70%; fix `Citadel: sell $1.7M of NVDA · 0.073% of a $2.4B position
  · costs 0.0042% of gross assets` (reduction 0.000732421875, cost 0.00004234832, sell_usd
  1,731,560.15, position_usd 2,364,156,792, gross_usd 40,888,519,059, 124 evals); after 6.5%
  (6.483%) and 1.33× (1.3299), 2 breaches in
  1 round; shock stamp `5.27% NVDA`; boundary marker `L 5.0 · overlap 0.71` (0.7117); fund labels at
  t0 `L 5.18 · L 5.36 · L 5.03 · L 5.15 · L 5.25`, at round 3 / 3 `L 4.87 · L 4.91 · L 5.24 · L 4.80
  · L 4.92`; NVDA asset label −5.27% at t0, −5.76% at the end.
- Measured wall clock, click to settled, on a warm cache: attack → cascade **3.2s**; Map the boundary
  → grid on screen **0.05s**; Stabilise → fix and `bought` lines **0.1s**, split animation done
  **2.6s**; Assumptions → open **instant**. Every API call is under 50ms. The interaction costs
  almost nothing — all the time in this video is speech, which is the problem flagged at the top.
- `bought` on `/api/stabilise`: before 5.2734%, after 5.2773%, delta +0.0039pp against
  `resolution_pct` 0.005 → **`measurable: false`**, note "no measurable change in break point — a
  targeted patch, not structural repair". Quote the note, not the delta. It renders on screen above
  the split as soon as Stabilise returns, so Shot 2.12 is a live beat, not a slide.
- The solver strip will read **"SciPy-free Python · exhaustive position scan"** unless someone has
  run `matlab/stabilise.m` and dropped `solve_out.json` into `data/cache/` first — see
  `matlab/README.md`. Shot 3.2's line about MATLAB pattern search is only true if you do that step.
