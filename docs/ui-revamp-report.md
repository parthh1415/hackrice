# Firebreak — UI revamp report

Commissioned as "investigate hackathon winners, draft a revamp of our entire UI".
I did the investigation. The recommendation it produced is not the one that was
asked for, so that goes first.

---

## 0. Read this before anything else

**The submission deadline is 09:00 CDT today. This was written at 02:45. You
have about six hours, and three things are not shipped:**

| | state | why it matters |
|---|---|---|
| **Demo video** | **not recorded** | Devpost submissions are judged from it. Most judges watch the video and never run the code. |
| **GitHub repo** | **19 commits behind** | `github.com/parthh1415/hackrice` currently shows the *old dark UI*, no MATLAB, no waterfall, no 3-D surface. A judge opening that link sees a different, worse project. |
| **Devpost entry** | drafted in `docs/devpost.md`, not submitted | An unsubmitted draft scores zero. |

**Do not revamp the UI today.** The current frontend is finished, tested (411
tests + a UI harness) and internally consistent. Six hours before a deadline,
a redesign trades a working product for an unfinished one. Everything in §5 is
for after the deadline.

The next six hours belong to §4.

---

## 1. What the research actually says

### HackRice 16's own rubric

Five dimensions, equally weighted:

1. **Relevance** — alignment with the track
2. **Originality / Creativity** — "original ideas or new angles on existing ideas"
3. **Practicality / Impact** — real-world problems, scalability
4. **User experience / Design** — "aesthetic appeal and intuitive interfaces"
5. **Technical Rigor** — "advanced solutions to challenging problems"

Design is **one fifth** of the score. It is not nothing, and it is not the
thing you are behind on. Tracks this year are Healthcare, Finance, Games and
Gamification, Work and Productivity. Firebreak is Finance.

### What actually won HackRice 15

Finance & Entrepreneurship track winners were **GrowFi** (gamified financial
literacy with an evolving frog mascot, React + MongoDB + Gemini) and
**CodeScribe**. Across all tracks the pattern is consistent: consumer-shaped,
approachable, AI-assisted, and technically modest. GrowFi's stack is React 18,
Express, MongoDB Atlas, Gemini API.

Read that honestly in both directions:

- **You are not behind on technical rigor. You are far ahead of it.** A
  deterministic cascade engine, 411 tests, mutation testing, a second
  independent implementation in MATLAB agreeing to 0.00e+00 — nothing in that
  winners list is close. Dimension 5 is yours.
- **You are behind on approachability.** Every winner is instantly legible in
  one sentence. "Gamified financial literacy with a frog" lands in three
  seconds. "Reverse stress testing with fire-sale contagion modelling" does
  not.

### What won elsewhere

TreeHacks 2025's grand prize went to **Hawkwatch**, real-time video
surveillance alerting on crime and life-threatening events. The Education grand
prize went to **HiveMind**, an AI platform that assesses student understanding
live in Zoom. Same pattern: a one-sentence promise a judge can repeat to
another judge.

### The sponsor prize you are positioned to win

**MathWorks — "best use of MathWorks tools", a special prize plus an article on
the MathWorks website.** As of tonight you have:

- `patternsearch` solving the institutional patch, 658 evaluations, exit flag 1
- `cascade.m` independently recomputing all 256 boundary cells, agreeing with
  the Python engine to **0.00e+00**
- two MATLAB-generated figures in the product, in the product's own palette
- a standing test (`test_matlab_agrees_with_python.py`) that keeps the
  agreement true

That is a stronger MathWorks story than a normal entry, and you assembled it
four hours ago. **Make sure the Devpost says so in its own section.** Also note
Capital One is running a challenge; `docs/devpost.md` already claims both.

---

## 2. The current UI, assessed honestly

Seven screens, monochrome on paper, ink hairlines, one red that means exactly
one thing. It is coherent, disciplined and — unusually for a hackathon — it
looks like it was *designed* rather than assembled from a component library.
The waterfall, the two-book overlay on Fix, the canvas boundary map and the
animated cascade flow are all genuinely good.

**Its strength is also its risk.** The aesthetic reads as a printed risk memo.
Next to a frog mascot it reads as austere, and a tired judge at 11am skims. The
problem is not that it is ugly. The problem is:

> **The first ten seconds do not say what this is for.**

The landing page opens with *"What are we stress testing?"* — which assumes
the visitor already knows why they would stress test anything. There is no
one-line promise, no "who is this for", no before/after. Every winner above
leads with the promise.

Concrete gaps, in order of how much they cost you:

1. **No hook above the fold.** Nothing states the product's claim before the
   first control.
2. **The best frame is on page 5.** The Fix page's two-book overlay — the
   undefended book crossing the limit line, the defended one stopping above it
   — is the single most persuasive image in the product, and a judge reaches it
   only by clicking four times.
3. **The number that matters is never dramatised.** 7.33% → 10.00% is the whole
   thesis and it is rendered at the same weight as everything else.
4. **No empty-state story.** A cold visit shows a form, not the product.

---

## 3. What *not* to change

Do not repaint it. The monochrome discipline is an asset — it is the reason
this looks like a product rather than a project, and the §7 constraints
("no green", one meaningful colour) are what make the red readable when it
appears. Three of the last four improvements came from *enforcing* that
discipline, not relaxing it.

---

## 4. The next six hours, ranked

Time-boxed. Stop when the clock says stop, in this order.

### 4.1 — Push the repo. (2 minutes) — **do this first**

Nineteen commits. The public repo is a different project. This is the single
cheapest, highest-consequence action on the list.

### 4.2 — Submit the Devpost as a draft. (15 minutes)

Fill it from `docs/devpost.md`, paste the repo link, save. A submitted entry
with a missing video beats a perfect unsubmitted one. You can edit until the
deadline.

### 4.3 — Record the video. (60–90 minutes including retakes)

`docs/video-shooting-guide.md` is current and was rewritten against this build.
It has the five frames worth filming, the demo path, and every number verified
against the running engine. Follow it.

Two things it tells you that are easy to get wrong:
- Open every shot with `?demo` rather than filming yourself clicking to it.
- Say the MATLAB claim as **agreement, not precision** — Python's search is
  equal or finer on depth in all three measured scenarios.

**If you do nothing else on this list, do 4.1, 4.2 and 4.3.**

### 4.4 — Fix the first ten seconds. (30 minutes, low risk)

The only UI change I would make today, because it is additive and touches one
page. On `index.html`, above the existing header, add a hook block:

```
Your portfolio is fine until someone else is forced to sell.

Firebreak finds the smallest shock that breaks your limit, shows you how
crowded institutional selling amplifies it on the way to you, and tests
whether the fix actually helped.

                 7.33%  →  10.00%
        the shock alone     after other people's selling
```

Two sentences and the one comparison that is the whole product. Set the two
figures in `--font-num` at `--t-fig`, the arrow as a word or a hairline (`→`
is in no vendored subset — see `tokens.css`). This is a `<header>` change in
one file, it cannot break the engine, and the harness will tell you if it does.

### 4.5 — If time remains: put the Fix overlay on the landing page. (30 minutes)

Your best image, above the fold, as a static `<img>` of the two-book waterfall.
Nothing else in the product argues as fast.

### 4.6 — Do not start anything else.

---

## 5. The revamp — for after the deadline

The brief asked for this, so here it is properly. None of it is for today.

### 5.1 An entry screen that sells before it asks

The product currently starts with a form. It should start with an argument and
*then* the form. One scroll: the hook, the 7.23 → 10.00 comparison as the hero,
the two-book overlay, then "use the demo portfolio / import a CSV".

### 5.2 One continuous narrative instead of seven pages

The stepper is honest but it makes the reader click six times for one story. A
single scrolling document, with the rail becoming a progress indicator that
tracks scroll position, would let a judge see the whole argument without a
decision at every step. The seven pages become seven sections; the state
machine underneath does not change.

### 5.3 Make the cascade the centrepiece it already deserves to be

It now has animated flow, leverage gauges against the band, per-name fall bars
and a "your book" strip. What it still lacks is *time*: a scrubber with the
rounds marked, a small always-visible sparkline of your loss across all rounds,
and the ability to drag rather than click Next. Cheap, and it converts the
diagram from a stepper into an instrument.

### 5.4 A live parameter panel

λ, γ and the breach band are declared on the Model page and adjustable nowhere.
The boundary map already answers "what if leverage were different" across 256
cells — letting a judge *drag* leverage and watch the marker cross the contour
would be the most convincing ten seconds in the product. The engine already
computes this in 11–20ms. This is the highest-value item on this list.

### 5.5 Density where density is earned

The Model page is a table of prose. The Validate page is three tables. Both
would benefit from the treatment the Fix page got: one figure that carries the
claim, with the table underneath as evidence rather than as the argument.

### 5.6 The third MATLAB figure

The 400-scenario distribution — current book vs defended, overlaid, with the
limit line — is the chart that literally shows the product working, and it is
the most conventionally "quant" visual you do not yet have. `validate.py`
already produces the data.

---

## 6. The honest summary

Firebreak's problem is not its interface. It is that a genuinely rigorous
project is one unpushed repo and one unrecorded video away from being invisible
to the people scoring it. The interface costs you a fraction of one rubric
dimension. The missing video costs you all five.

Push, submit, record. Then fix the first ten seconds if the clock allows.

---

## Sources

- HackRice 16 — tracks, prizes, rubric: <https://hackrice-16.devpost.com/>
- HackRice 15 — winners gallery: <https://hackrice-15.devpost.com/project-gallery>
- GrowFi (Finance track winner, HackRice 15): <https://devpost.com/software/growfi>
- TreeHacks 2025 results: <https://stanforddaily.com/2025/02/18/treehacks-awards-200000-in-prizes-to-students-from-around-the-world/>
- TreeHacks 2026 results: <https://stanforddaily.com/2026/02/15/12th-annual-treehacks/>
- HiveMind (TreeHacks Education grand prize): <https://newsroom.niu.edu/niu-student-samarth-shiramshetty-wins-grand-prize-at-stanford-universitys-treehacks/>
- MathWorks student competitions / hackathons: <https://www.mathworks.com/academia/students/competitions.html>
