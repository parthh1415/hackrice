# Firebreak — demo video script

**Target length:** 3:30. Hard ceiling 4:00.
**Required HackRice structure:** 30s intro · 2min demo · 30s technical design · 30s impact and future.

**Before you record**

- Sliders at the golden path: gross leverage **5.0**, price impact **γ = 0.20**, failure condition
  **3 or more funds breach**. Every number below is the live output at those settings. If you move a
  slider, the numbers change and this script is wrong.
- Run the loop once to warm the cache. Serve with the cached demo path so wifi cannot kill you.
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
**On screen:** The live app, idle. Five fund nodes, ten asset nodes, edges visible. Sliders and the
solver strip legible at the bottom.

> "Real holdings from five hedge funds' SEC 13F filings. A Python cascade engine, MATLAB pattern
> search for the optimisation, and a plain JavaScript front end. Purpose: find the failure before it
> finds you."

---

## ACT 2 — DEMO (0:30 – 2:30)

### Beat 1 — ATTACK (0:30 – 0:57)

#### Shot 2.1 · 0:30 – 0:44
**On screen:** Cursor traces across the bipartite network, then rests on the assumptions strip
showing quarter 2026-06-30 and source SEC 13F-HR.

> "Citadel, Millennium, Point72, Two Sigma, Renaissance. Ten mega-cap names. These are their real
> filed books, second quarter twenty twenty-six. Mean pairwise overlap between these five portfolios
> is zero point seven one. Citadel and Two Sigma are at zero point nine two. Nearly the same fund."

#### Shot 2.2 · 0:44 – 0:50
**On screen:** Cursor on the sliders. Leverage 5.0, γ 0.20 highlighted briefly.

> "Leverage and price impact aren't in a 13F, so they're ours. Five times gross, impact coefficient
> zero point two, both adjustable, both on screen the whole time."

#### Shot 2.3 · 0:50 – 0:57
**On screen:** Click **Find weakest shock**. Solver strip ticks over. The hero number lands:
**NVDA −5.28%**.

> "Failure means three or more funds breach. Find me the smallest single-name drop that does it."
>
> ⏸ *(let the number land, ~1.5s)*
>
> "NVIDIA, down five point three percent. That's not a crash. That's a bad Tuesday."

### Beat 2 — CASCADE (0:57 – 1:32)

#### Shot 2.4 · 0:57 – 1:10
**On screen:** Cascade plays. Round counter visible. Millennium and Renaissance turn red in round 1.
**Presenter is silent for the first two rounds.**

> *The UI is monochrome plus exactly one red (`--alert #FF383B`). Healthy nodes are dim white,
> stressed nodes are full white, breached nodes are red. There is no amber or ember in the product —
> don't say those words on camera.*

> "Watch it move."
>
> ⏸ *(full silence through round 1 and round 2, ~6s)*
>
> "Millennium and Renaissance breach first. They're the two heaviest in NVIDIA. To get back under
> their limits they sell across the whole book, not just the name that fell. Everything they own
> ticks down."

#### Shot 2.5 · 1:10 – 1:19
**On screen:** Round 2, Citadel turns red. Round 3, Two Sigma turns red. Final state holds.

> "Nobody shocked Citadel. Citadel breaches in round two because of what Millennium had to sell. Two
> Sigma goes in round three. Four of five funds, three rounds."

#### Shot 2.6 · 1:19 – 1:32
**On screen:** Zoom to the Point72 node, which never turned red. Overlay its
numbers: `NVDA weight 2.8% · direct loss 0.75% · total loss 5.70%`.

> "But look at Point72. It holds two point eight percent NVIDIA, the smallest position in the system.
> The shock itself costs it three quarters of one percent of equity."
>
> ⏸ *(beat)*
>
> "It ends down five point seven. Seven and a half times its own exposure. It never breached. It never
> sold a share. That damage is entirely other people liquidating names it happens to share with them.
> That's the part a single-fund stress test cannot see."

**On screen at 1:30:** Metrics panel: `shock loss 4.88% → final loss 9.13% · amplification 1.87×`.

### Beat 3 — BOUNDARY (1:32 – 1:57)

#### Shot 2.7 · 1:32 – 1:42
**On screen:** Click **Map the boundary**. A 16×16 phase diagram fills in cell by cell. Leverage on
one axis 1.5 to 8.0, crowding on the other, running from every fund holding something different,
through the books exactly as filed, up to every fund holding the same thing.

> "Fair question: did we get unlucky, or is the structure the problem? So sweep it. Leverage from one
> and a half to eight. Crowding from every fund holding something different, through the books
> exactly as filed, all the way up to every fund holding the same thing."
>
> ⏸ *(let the grid finish, ~2s)*

#### Shot 2.8 · 1:42 – 1:57
**On screen:** Critical contour draws. "You are here" marker lands at leverage 5.0, overlap 0.712,
close to the line.

> "Every cell is a full cascade, computed, not drawn. And there's a boundary. Below it the shock gets
> absorbed. Above it, it runs. You are here."
>
> ⏸ *(beat on the marker)*
>
> "Right on the edge. Which means this isn't bad luck. It's a place you're standing. And if it's a
> place, you can move."

> *Say "below / above", not "one side / the other". The sharp transition is in **leverage** — at the
> filed overlap, amplification goes 1.00 at λ≈4.5 to 1.86 at λ≈5.0. Along the crowding axis the
> reference shock is single-name, so amplification is not monotone in crowding. If a judge points at
> the right-hand columns and asks why they're cooler, that's why: blending toward the mean dilutes
> the shocked name. Don't claim a crowding threshold on camera.*


### Beat 4 — DEFEND (1:57 – 2:30)

#### Shot 2.9 · 1:57 – 2:08
**On screen:** Click **Stabilise**. Solver strip shows the pattern search running, evaluation count
climbing. The instruction line resolves:
`Millennium: cut GOOGL exposure 15%. Cost: 0.13% of gross assets.`

> "Now run it backwards again. Same failure condition, same shock. What is the smallest change
> anywhere in this system that survives it?"
>
> ⏸ *(let the instruction render)*
>
> "Millennium cuts Alphabet by fifteen percent. Thirteen basis points of the system's gross assets."

#### Shot 2.10 · 2:08 – 2:18
**On screen:** Cursor underlines the word GOOGL in the instruction, then flicks to the NVDA node.

> "Notice it isn't NVIDIA. We shocked NVIDIA. The cheapest fix is in Alphabet, because Alphabet is
> the third most crowded name here and Millennium is one of the two funds that breach in round one.
> That's why you solve it instead of guessing."

> *Crowding rank by share of total pairwise overlap: NVDA 26%, AMZN 26%, GOOGL 15%. Third, not
> second. And Millennium breaches alongside Renaissance in round 1 — don't say "the" fund.*


#### Shot 2.11 · 2:18 – 2:30
**On screen:** Split screen. Both sides run **NVDA −5.28%**, the identical shock stamped underneath
both panels. Left: 4 breaches, 3 rounds, 9.13% loss. Right: 2 breaches, 1 round, 6.49% loss.

> "Same shock, both sides. Before: four funds, three rounds, nine point one percent of system equity
> gone."
>
> ⏸ *(hold on the split, ~2s)*
>
> "After: two funds, one round, six point five. Amplification one point eight seven down to one point
> three three. For thirteen basis points."

---

## ACT 3 — TECHNICAL DESIGN (2:30 – 3:00)

### Shot 3.1 · 2:30 – 2:40
**On screen:** Architecture diagram, four boxes left to right: `ingest → engine → search → ui`, with
`engine` labelled "pure function (H, λ, γ, s) → trajectory".

> "Four units. Ingest pulls the 13F XML off EDGAR for six registrants across five firms, filters out
> options rows, aggregates by CUSIP. The
> engine is a pure function: holdings, leverage, impact, shock, in; full trajectory out. Everything
> else treats it as a black box, which is what let us build the optimiser and the front end at the
> same time."

### Shot 3.2 · 2:40 – 2:50
**On screen:** `matlab/stabilise.m` open, `patternsearch` call highlighted. Cut to the solver strip
in the app showing the live solver name, evaluation count and exit flag.

> "The search is the product. Forward, breach count is monotone in shock size, so a grid scan brackets
> the threshold and bisection refines it. Backwards, the objective is a simulation. No gradient,
> piecewise-constant landscape, discrete feasible set. That's MATLAB pattern search, and the app tells
> you which solver actually produced the number on screen."

### Shot 3.3 · 2:50 – 3:00
**On screen:** The assumptions panel, "what we do not claim" bullets visible.

> "And the honesty panel is not an afterthought. We do not predict market moves. Leverage is not in a
> 13F, it's our parameter. 13F is long-only, quarterly, forty-five days late. Price impact is a stated
> functional form with a coefficient you can move. The claim is that the boundary exists and moves
> predictably, not that any one point on it is the truth."

---

## ACT 4 — IMPACT AND FUTURE (3:00 – 3:30)

### Shot 4.1 · 3:00 – 3:12
**On screen:** Back to the phase diagram with the marker on it.

> "Reverse stress testing is already mandatory. UK PRA, EBA guidelines: firms have to find the
> scenarios that break them. They mostly do it by hand, on one balance sheet at a time. Nothing does
> it interactively across portfolios that overlap, and overlap is exactly where the 2007 quant quake
> and every crowded-trade unwind since actually happened."

### Shot 4.2 · 3:12 – 3:24
**On screen:** Short list appears: multi-asset shocks · systemic-importance ranking · square-root
impact · bystander exposure view.

> "Next: shocks across several names at once, ranking which single asset is most dangerous to the
> whole configuration, a second impact model to prove the boundary isn't an artefact of the first one,
> and a view for people who hold these names with no leverage. They can't be forced to sell. They
> still pay for it."

### Shot 4.3 · 3:24 – 3:30
**On screen:** Back to the hero number, NVDA −5.28%, then the title card.

> "Five point three percent on one name, and four of five funds breach. The point isn't that number.
> The point is that you can go looking for it. Firebreak."

---

## Recording notes

- **Do not** talk during Shot 2.4's first two rounds or during the Shot 2.11 split-screen hold. Those
  two silences are what make the demo land.
- If a run is slow on the day, use the cached demo path. Do not fill the gap with narration.
- If asked live where leverage comes from, the answer is one sentence: it is not in the filing, it is a
  declared parameter, and it is the slider on screen.
- Numbers verified live 2026-09-12 at leverage 5.0, γ 0.20, breaches ≥ 3, against
  `/api/break` and `/api/stabilise`. Re-run before recording and correct any drift rather than
  reading these from the page. Verified this pass: NVDA −5.28%, shock loss 4.88%, final loss 9.13%,
  amplification 1.87, 3 rounds, breaches Millennium+Renaissance → Citadel → Two Sigma (4 of 5,
  Point72 never); Point72 2.8% / 0.75% / 5.70%; fix Millennium GOOGL −15% at 0.13% of gross assets;
  after 6.49% and 1.33 with 2 breaches in 1 round; marker at leverage 5.0, overlap 0.7117.
- The solver strip will read **"SciPy-free Python · exhaustive position scan"** unless someone has
  run `matlab/stabilise.m` and dropped `solve_out.json` into `data/cache/` first — see
  `matlab/README.md`. Shot 3.2's line about MATLAB pattern search is only true if you do that step.
