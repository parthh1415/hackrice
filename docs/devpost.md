# Firebreak

**Reverse stress testing for your portfolio.** Not "what if NVDA drops 20%", but "what is the smallest
drop that pushes *my* portfolio past the loss I refuse to tolerate — and what is the smallest change
that buys me distance from it".

You upload a portfolio — a CSV, parsed in your browser — and name the loss you will not accept.
(A brokerage connection is not in this build; the button is there and disabled, and says so.) Firebreak searches for the
smallest single-name shock that crosses it, models how crowded institutional selling amplifies the
damage on the way to you, shows the cascade round by round, recommends the smallest position change
that helps — and then **tests whether that recommendation actually helped**, by replaying the
identical shock, recomputing the new break point, and scoring both portfolios across 400 simulated
stress scenarios.

```
Portfolio  →  Risk limit  →  Firebreak  →  Cascade  →  Fix  →  Validate
```

On the demo portfolio at a 10% limit: **NVDA −25.05%** breaks it, a **7.33%** direct loss becomes
**10.00%** after the cascade, and reducing NVDA by **$472** moves the break point out to **−28.17%**.

The same engine, asked the institutional question instead, is Risk Desk Mode: *what is the smallest
market move that forces three leveraged funds to deleverage at once?* That is the prime-brokerage
version, and the engine that answers it is unchanged. It is not a mode you can switch to in this
build: the six-page product is the portfolio question, and the institutional answer surfaces as the
"What computed the institutional patch" card on the Model page and through /api/stabilise.

HackRice 16 — Finance track. Also submitted to the Capital One and MathWorks challenges.

---

## Inspiration

Every stress test we had ever seen runs forwards. You pick a scenario, you run it, you get a number.
The scenario is the assumption, and the assumption is the part nobody checks.

Reverse stress testing runs the other way: start from failure and search backwards for the scenarios
that produce it. It is not a new idea, and it is not optional. UK PRA supervisory statements on
ICAAP/SREP and the EBA stress-testing guidelines both require firms to identify the scenarios that
render their business model unviable. Banks do it, mostly by hand, on their own balance sheet.

Nobody does it interactively, and nobody does it across *overlapping* portfolios, which is where the
interesting failures live. A fund does not blow up alone. It blows up because four other funds owned
the same ten names and all hit their leverage limit in the same hour.

The trigger for building it was a number we found in the first two hours: across Citadel, Millennium,
Point72, Two Sigma and Renaissance, on their actual Q2 2026 13F filings, restricted to ten mega-cap
names, the mean pairwise cosine similarity of portfolio weights is **0.712**. Citadel and Two Sigma
sit at **0.92**. We had planned a fallback where we would build synthetic portfolios if the real ones
were not crowded enough to cascade. We did not need it.

## What it does

Firebreak loads the real books, then runs two searches around a forced-deleveraging simulator.

**The attack.** Given a failure condition you choose (default: three or more funds breach their
leverage limit), it searches every asset for the smallest single-name price drop that trips it. On the
real filings at gross leverage 5.0, impact coefficient γ = 0.2 and a breach band of 1.05, the answer
is **NVDA −5.27%**. Not a crash. A bad Tuesday.

**The cascade.** That 5.27% drop costs the system 4.88% of equity directly. Then the forced selling
starts. Millennium and Renaissance breach first, sell pro rata across their whole books to get back
under their limits, and push down the price of everything they own. That moves Citadel over the line
in round 2, and Two Sigma in round 3. Final equity loss: **9.12%**. Amplification **1.87×**, three
rounds, four of five funds breached. (The metrics band rounds to one decimal on screen — 4.9% and
9.1% — so quote those if you are reading off the display.)

The clearest thing in the whole demo is Point72. It holds 2.8% NVDA, the smallest position in the
system. The direct hit costs it 0.75% of equity. It ends the cascade down **5.70%**, roughly seven and
a half times its own exposure, without ever breaching and without selling a share. All of that damage
arrives through other people's liquidations of names it happens to share with them.

**The boundary.** A 16×16 phase diagram over gross leverage (1.5 to 8.0) and portfolio crowding
(sweeping both ways from the books as filed — sharpened away from the system mean on one side,
blended toward it on the other, so measured overlap runs 0.00 to 1.00), with amplification computed
in every cell rather than sketched, and a marching-squares contour traced at 1.5× on top of the
shading so the boundary is a line you can point at rather than a colour change you have to argue for.
It puts a marker on the configuration you are currently looking at: leverage 5.0, overlap 0.71 —
just past the leverage boundary. At the filed overlap, amplification sits flat at 1.00 up to λ≈4.1,
is 1.16 at λ≈4.5 and 1.86 at λ≈5.0, and the 1.5× contour crosses at λ≈4.7. The question it answers
is whether you got unlucky or whether you are standing somewhere structurally bad. Worth saying
plainly: *where* that boundary sits is a function of the breach band we declared, and the sweep
honours it: at the same −5% reference, a band of 1.02 puts the boundary at λ≈2.7 and a band of 1.10
at λ≈7.7, and at 1.30 the filed-overlap column never leaves 1.00 at all — only 16 of 256 cells
cascade, and they are not where you would guess: they span seven leverage rows from λ=5.40 to 8.00
and sit at the *low*-overlap edge, overlap 0.00 to 0.18. Twelve of the sixteen cross 1.5×. (An
earlier draft of this paragraph said "only the top of the plot, λ=8.0" — it was one row, and it is
seven.) The shape of the map is the finding; the location of the
marker on it is a consequence of parameters we chose and show.

**The defence.** The inverse search. It scans every (fund, asset) position and bisects on *how deep*
the cut has to be. The answer at these settings: **Citadel sells $2.24M of NVDA** — 0.095% of a
$2.36B position, and 0.0042% of the system's $40.9B gross book. Four ten-thousandths of one percent.
Re-run NVDA −5.27% against the patched books and the outcome goes from four breaches over three
rounds to two breaches in one round, final loss 9.12% down to **6.48%**, amplification 1.87 down to
**1.33**.

The depth matters as much as the position, and it took us two goes to measure it. Our first version
searched a 5% grid, so it answered *which* position to cut and never *how much* — every scenario came
back "5%", which is what a grid floor looks like when you mistake it for a result. Bisecting fixed
the shape but not the resolution: the depth tolerance was an absolute 0.002 while the true answer had
shrunk to 0.0007, so the search was halting with a bracket wider than the number it reported and
printing the top of it — 2.15× the true minimum, on the one number the product exists to produce.
With a relative tolerance the cheapest cuts across our recorded scenarios run from 0.0027% to
0.1465%, $63K to $3.2M: varied, because finally measured rather than quantised.

**And then we say what the fix does not buy.** The stabilise response re-runs the reverse search
against the patched books and reports it as `bought`. The measured delta is +0.0039pp against a
search resolution of 0.01pp — *inside its own error bar* — so the payload sets `measurable: false`
and the note reads **"no measurable change in break point — a targeted patch, not structural
repair"**. We deliberately do not quote the delta as though it meant something; that would be the
same fake-precision mistake as the hero number, one level up. $2.24M of Citadel's NVDA — under a
basis point of gross assets — clears *this* failure condition against *this* shock and buys nothing
we can measure against the next one.
That is the honest reading of a one-position, one-shock optimiser, and we would rather be the ones
to say it. The genuine next version optimises over a *family* of shocks, and that is real work, not
a slider.

Worth one clarification, because the screen says it plainly: after the fix the system does not
"survive" in the sense of nothing breaking. Millennium and Renaissance still breach. It clears the
failure condition we set, which is *three or more*. Two is fewer than three.

Read it as a targeted patch for a named scenario, not as structural repair. And note what the
optimiser is actually exploiting: Citadel does not breach first — Millennium and Renaissance do —
but Citadel is the largest book in the system at $14.6B, so the smallest *fractional* cut there
removes the most dollars of round-two selling pressure. That is not the move anyone would guess, and
it is why you solve it rather than eyeball it.

## How we built it

**Data.** SEC EDGAR, directly. `data.sec.gov/submissions/CIK{cik}.json` for the filing index, then the
information table XML out of the archive. Five firms across six registrants — Two Sigma files under
two CIKs and both books are summed — period of report 2026-06-30 for all of them, $40.9B of gross
long equity in the ten names. Cached to disk so we are not pulling 8 MB of XML in front of a judge.

**Engine.** Pure Python and numpy, about 250 lines. Prices normalised to 1.0 at t0 so a 13F dollar
column works as a units vector. A fund over its leverage limit sells `q = A(L − L_target)/L`, pro rata
across its book, proceeds to debt. Selling pressure `V_i` moves price by `−γ_i · V_i / ADV_i`. Repeat
until nobody breaches or twenty-four rounds elapse. The engine is a pure function `(H, λ, γ, s) → trajectory`,
which is what let the optimiser, the API and the frontend be built at the same time.

**Search.** Breach count is monotone in shock size at the demo settings, so the critical drop behaves
like a genuine threshold. We find it with a 1% grid scan to bracket, then bisection inside the
bracket. Pure bisection stalls on the flat regions between breaches. The search reports the smallest
crossing the grid found rather than advertising a proven threshold, because monotonicity is checked,
not proved — see below.

**Stabilisation.** This is the piece that goes to MATLAB. The objective is a simulation, so there is no
gradient; the feasible set is defined by whether a cascade crosses a discrete condition, so the
landscape is piecewise constant. `patternsearch` is built for exactly that, and `matlab/stabilise.m`
runs the solve over (fund, asset, reduction). The bridge is a JSON spec file in and a JSON result file
out, rather than the Engine API, specifically so it runs from MATLAB Online with no local install. If
MATLAB is not present the API falls back to an exhaustive Python position scan and **says so in the
UI** — the Model page carries the engine name, solver, evaluation count, exit flag and solve
time, and prints "not recorded" rather than a zero when a replayed run carries no timing. We would
rather show the fallback than imply a solver we did not run.

**Frontend.** Vanilla JS and inline SVG on a stdlib `http.server`. No npm, no bundler, no build step,
no CDN — nothing to install on a demo machine and nothing that breaks when conference wifi does.
That last part we had to earn twice: the page linked Geist from Google Fonts while this very
paragraph claimed "no CDN", which one look at a network tab would have shown a judge. The font is
self-hosted now (`web/fonts/`, `web/fonts.css`, 92KB of Latin and Latin-Ext), so the claim and the
page finally agree. Writing *that* sentence cost us a third pass: the first version of it said
"Latin and Greek subsets — the app needs γ, λ and δ", and not one clause of that was true. Geist
publishes no Greek subset; λ and δ appear nowhere in the app; and the one γ that does appear, in the
`Price impact γ` label, has been rendering in `-apple-system` since the day it was written — under
the Google Fonts link exactly as much as now. We only found out by reading the cmap. Three
consecutive claims about our own typography, all confident, all wrong, all in the paragraph about
being wrong. The cascade animation
reads `trajectory[t]` frame by frame; it never interpolates between precomputed endpoints, because the
animation is supposed to *be* the mechanism rather than illustrate it.

## The pivot, and what it did not cost

Firebreak began as an institutional tool: five leveraged funds, a failure condition of "N of them
breach", a control rail of four sliders. Technically strong, and it started in the middle of a story —
it assumed you already cared about a preloaded network of hedge funds.

Turning it into a product for someone with an actual portfolio required **no change to the engine at
all**, and that is the part worth knowing.

`find_weakest_shock` already took an arbitrary `condition(CascadeResult) -> bool`. A finished cascade
already carried the price vector it ended on. So "this person crossed the loss they told us they would
not tolerate" slots in beside "three funds breached" as just another predicate:

```python
def portfolio_loss_above(weights, cash, limit):
    return lambda r: 1.0 - (weights @ r.prices + cash) >= limit
```

That is the whole pivot at the numerical level. `engine.py`, `search.py` and `stabilise.py` are
untouched, every one of their tests still passes, and the institutional mode is not a legacy path —
it is step four of the new product, running the same code it always did.

**Your portfolio is an observer, and we say so.** It takes the price damage; it does not join the
network. The institutions deleverage identically whether or not you trim NVDA, because a retail
account does not move markets. So the cascade is computed once and every candidate cut is scored
against the same price path — not an optimisation, a modelling statement. On screen: *your position
doesn't move the market, it decides how much of the market's move lands on you.*

**The first fix it recommended was zero dollars.** Correctly. The break point is by construction the
shock where the loss lands exactly *on* the limit, so an infinitesimal cut already puts you under it,
and the bisection dutifully found one. True, useless, and exactly the kind of number this project
keeps catching. A recommendation has to buy real distance, so the margin is a declared parameter: a
10% limit is defended to 9%.

**Validation is three tests, not four.** Same-shock replay, recomputed break point, and 400 seeded
synthetic scenarios with both portfolios scored on identical draws. Historical replay is **absent and
says so** — we ship one frozen quarter of holdings and no price history, and building it on invented
returns would put a confident number with nothing beneath it on the screen whose whole purpose is
evidence. There is a test asserting that feature is missing and reports no figure.

## Challenges we ran into

**Insolvent funds quietly left the simulation.** Equity `E` goes negative, so `A/E` goes negative, so
`L > L_max` is false, so the single most distressed fund in the system stops breaching and stops
selling. The symptom was bizarre: damage was non-monotone in shock size. AMZN −53% produced five
breaches and −54% produced four, on the real books, at default sliders, in 30 of 32 (leverage, γ)
combinations we swept.

That is not a cosmetic bug. The entire product claim is "the smallest shock that breaks the system",
and if damage is not monotone then there is no smallest shock, there are several disconnected bands and
the phrase means nothing. The search was bisecting over a function that had no threshold to find. Fix:
insolvency is `+inf` leverage, full liquidation, marked defaulted. Breach count is now monotone at the
demo settings, which we check rather than assert: a test sweeps all ten assets from 0% to 60% at
λ=5.0 and γ=0.2 and asserts the count never falls. We do not claim it globally — there is still a
residual case at λ=7.5, γ=0.1 where TSLA −20% gives five breaches and −21% gives four, with nobody
insolvent. A bigger shock kills the distressed funds a round sooner, so they liquidate at a higher
VWAP and less damage reaches the funds behind them — a round-ordering effect rather than the original
hole. (We have a second, independently found case at λ=3.0, γ=0.5 on MSFT that behaves identically.
Two of us went looking and found two; we are not claiming those are the only ones.) Final *loss* is
non-monotone by design and we have a test that asserts it stays that way, so nobody later "fixes" it
into a claim we cannot support.

**The optimiser answered "which position" and never "how much".** The stabiliser searched a 5%
reduction grid, so every scenario we recorded came back with the same answer: cut 5%. Ten
recordings, one number. That is not a result, it is the floor of the grid wearing a result's
clothes, and we read it as a finding for hours. Bisecting on depth as well as position, the cheapest
cuts come out between 0.0027% and 0.14% — and the headline got dramatically stronger, because the
real answer is that selling $2.24M out of a $2.36B position prevents the whole cascade. We nearly
shipped a much weaker claim because we never questioned a number that looked round. Then we did it
again one level down: the bisection's *tolerance* was absolute where the answer was shrinking, so it
reported 2.15× the true minimum. Same lesson twice in one night — the resolution of your search is
part of your answer, and it has to be checked against the answer's own scale.

**The most important parameter was invisible.** The breach band — how far over its target leverage a
fund runs before it is forced to sell — was hardcoded at 1.05 while leverage and γ sat on sliders. It
moves the hero harder than either of them: at leverage 5.0 with ≥3 breaching, band 1.02 gives NVDA
−1.73% and amplification 3.10, band 1.30 gives NVDA −27.33% and 1.43. (Those two figures are
leverage-specific — at 3.0 the same pair is −4.59% and −57.12% — which we only noticed because the
assumptions panel was quoting them at every leverage as though they were the band's behaviour in
general.) A five-fold swing in the headline number, controlled by a constant
nobody could see and nobody was declaring. It is a declared knob now — `band`, default 1.05, range
1.0–1.5 — it comes back in the `params` block on every response, it has its own row on the Model
page reading `Breach band · 1.05× target, so a book sells above 5.25×`, and it sits in the
what-we-do-not-claim list next to leverage and γ. (It sat on a slider in the institutional build;
the six-page rewrite ships one declared configuration and prints it rather than offering it.)

**The hero was printing precision the search could not resolve.** The bisection tolerance was 5e-4
while the hero renders two decimals, so the last digit was decoration. It was not imprecise, it was
wrong: what we had been showing as −5.28% is −5.27%. Tolerance is 5e-5 now, which actually resolves
the digit we print.

**The after-panel was drawing the unpatched book.** The before/after split re-ran the cascade on the
patched holdings but rendered the original matrix, so the two halves showed the same network with
different numbers underneath. The whole point of that scene is that one position is smaller on the
right.

**Fire-sellers were immune to their own fire sale.** Sales were settling at book prices. A fund
liquidating 100% of its book therefore took exactly zero fire-sale loss, while every bystander ate the
price impact it caused. The funds driving the crash were the only ones untouched by it. Sales now
settle at the round's VWAP, midway between the pre- and post-impact price, which is both defensible and
the reason the headline amplification number is 1.87 rather than something flattering.

**We mapped one class of Alphabet and dropped the rest.** Our GOOGL entry was `02079K30`, which the
filings label `CAP STK CL A`. Alphabet's Class C is `02079K10` (`CAP STK CL C`), and there are two
depositary-share lines besides (`DEP SHS RP1/20 A` and `…B`). Citadel and Renaissance both file both
classes and both label them the same way, so this is not one filer's idiosyncrasy. All three were being silently dropped. In Citadel's Q2-2026 table the
mapped class is **$1.069B of a $2.229B Alphabet position — 47.9% captured, 52.1% missing**, and because
managers hold different class mixes the undercount was heterogeneous fund by fund. That is the nastiest
category of data bug: nothing errors, nothing looks wrong, and it quietly renormalises every other
column of the weight matrix by a different amount per fund. GOOGL weights moved by up to 10.25× when we
fixed it. The CUSIP map is many-to-one now, and a test asserts every prefix is exactly eight characters
and every name is held by at least two managers.

> This paragraph was itself wrong for most of the project's life, in a way worth admitting on a page
> about data bugs. It said "the GOOGL CUSIP was Alphabet Class C" and named `02079K10` as Class A —
> both inverted — and gave per-fund percentages (48/15/100) that no single-CUSIP map reproduces; the
> 48% was the share we *captured*, printed as the share we lost. We only caught it because a review
> agent went back to the filings and read `titleOfClass` instead of trusting the write-up. Every figure
> above is now taken from Citadel's actual information table, accession 0001104659-26-104387.

**One firm, two registrants.** A firm can file under several registrants — Two Sigma Investments and
Two Sigma Advisers are separate CIKs — and our manager map held one CIK per name, so we were reading
whichever registrant we happened to have picked. A manager now maps to a list of CIKs and the books are
summed.

> For *this* quarter it changes nothing, and the `$38.4B → $40.9B` move that used to sit in this
> paragraph belongs entirely to the Alphabet class fix above. But it is not decorative either. Two
> Sigma Advisers ran a real book until very recently and then consolidated into the Investments
> registrant — cover-page totals, whole book:
>
> | quarter | Advisers | Investments |
> |---|---|---|
> | 2025-09-30 | $50.0B | $67.2B |
> | 2025-12-31 | $51.4B | $70.9B |
> | 2026-03-31 | **$0** (1 placeholder row) | $123.9B |
> | 2026-06-30 | **$0** (1 placeholder row) | $138.1B |
>
> Advisers stopped filing a real table in Q1 2026 exactly as Investments jumped by $53B. So against
> Q4 2025 this fix would have been the difference between $70.9B and $122.3B of Two Sigma, and a
> one-CIK map would have read whichever registrant we happened to have picked. (Those are whole-book
> totals including options and debt, not the ten-name restriction — they are here to show Advisers was
> a real book, not to be compared with our $40.9B.)

**`13F-HR` did not match `13F-HR/A`.** Our "latest filing" filter was an exact string match on form
type, so a Citadel *restatement* of Q2 2026 was skipped and we read superseded data as if it were
current. Form 13F FAQ 58 covers amendment semantics; we follow it now.

> Measured honestly, this one is also inert for this quarter: Citadel's restatement moves $84,487,104
> across its whole book and **$0 inside our ten names**. We keep it because it is right, and because
> following that thread is what surfaced the real bug — a `13F-HR/A` whose cover page omits
> `<amendmentType>` was being summed with the filing it amends, doubling Citadel's book from $14.6B to
> $29.2B, gross from $40.9B to $55.5B, and taking the demo from four funds breaching to all five. The
> form string says "/A" and the cover page says `<isAmendment>true</isAmendment>`; we were reading
> neither. An amendment we cannot classify now raises instead of being guessed at, because the two
> ways of guessing wrong differ by a factor of two.

**The search asserted that zero shock was safe.** With leverage set past the max-leverage
limit, the system is already in breach before anything is shocked. The search took safety-at-zero as a
precondition rather than testing it, bisected down, and confidently reported a critical shock of
−0.0003%. A fabricated hero number is worse than no hero number. It tests zero first now.

**We measured leverage and called it contagion.** Our first amplification metric was `final loss /
direct loss` with mismatched denominators, direct loss as a fraction of gross assets and final loss as
a fraction of equity. It produced a very impressive 11.8×. It also equalled the leverage ratio exactly,
to three decimals, with market impact switched completely off. It was not measuring contagion at all.
Both terms are equity-denominated now and the invariant is a test: γ = 0 must give amplification
exactly 1.000000.

**A citation was wrong.** We had credited Caccioli et al. (2014) for the deleveraging rule. That paper
has no partial deleveraging — portfolios are fixed until default and then fully liquidated — and uses
exponential impact. The actual ancestor is Greenwood, Landier & Thesmar (2015), JFE 115(3), whose
`b_n = d/e` gives `q = (λ−1)·loss`, identical to ours. Caccioli is cited for overlapping-portfolio
contagion and the critical-leverage boundary, which is what it is actually about.

Nine of these twelve came out of handing the project to independent reviewers who had no stake in it
being right. Not one of them was found by a failing test — every single one produced a plausible
number and shipped.

## Accomplishments that we're proud of

The crowding is real and reproducible. Mean overlap 0.712 on filings anyone can download, with a
natural stable node (Point72, minimum pairwise overlap 0.44) so the demo shows a contrast instead of
everything turning red at once.

Point72's number. 2.8% exposure, 0.75% direct loss, 5.70% total. That single line is the whole thesis
about overlapping portfolios, and it came out of real filings rather than a constructed example.

The fix is non-obvious and it is *priced*. Selling $2.24M out of a $2.36B position — 0.0051% of the
system's gross assets — stops a cascade that costs 9.1% of system equity. It is not the fund that
breaches first, and it is a depth no one would have guessed, which is the whole argument for solving
it rather than eyeballing it. The output is a trade a PM could actually place, not a risk score, and
we report what it does not buy in the same breath.

Every number on screen is derivable, and we shipped honest magnitudes: amplification 1.87, not the
11.8 we could have had by leaving the broken metric in; a hero that prints only the digits the search
resolves; and a `bought` readout that says "no measurable change" about our own headline
intervention rather than quoting a delta smaller than the error bar around it.

## What we learned

Monotonicity is a product property, not a numerical nicety. "The smallest shock that breaks you" is
only a coherent sentence if damage is monotone in shock size, and we did not realise our headline claim
depended on a modelling detail about negative equity until it broke.

Silent data bugs are the dangerous ones. The options rows, the duplicate issuer rows, the amended
filings, the wrong share class: none of them raise an exception. They all produce a plausible number.
The only defence we found was checking intermediate quantities against something external rather than
checking that the pipeline ran.

Sanity tests that encode invariants catch more than tests that check outputs. `γ = 0 ⟹ amplification
== 1.0` is one line and it is the test that caught the metric bug. Checking that amplification came out
"about right" would have sailed past it.

And a metric that looks impressive deserves more suspicion than one that looks boring. So does one
that looks round. "Cut 5%" came back from ten different scenarios and we read it as a finding for
hours before noticing it was the resolution of the grid we were searching.

## What's next for Firebreak

Sparse multi-asset shocks, minimising `‖s‖₁` so the search can find the cheapest *pair* of names rather
than the cheapest single one. Real reverse stress testing is multi-dimensional.

Systemic-importance ranking per asset: which single name, if it moved, does the most damage per unit of
move, across the whole configuration space rather than at one slider setting.

Square-root price impact (`−Y σ √(V/ADV)`) alongside the linear form, so the boundary can be shown to
be robust to the functional form and not an artefact of it.

A bystander view. 13F holders are participants; a retail investor with no leverage cannot breach and
cannot be forced to sell, but still eats the price impact. That is what the six-page product now
is — you import a broker CSV and get an exposure measurement — so what is left here is the harder
half: ranking which bystanders are most exposed across a family of shocks rather than one.
Exposure, never a prediction.

Robust defence, and this is the one that matters most. Our stabiliser minimises cost subject to
clearing the failure condition under *one named shock*, which is why the fix it finds buys no
measurable critical-shock headroom. The right objective is to maximise the critical shock itself, or
to minimise cost subject to surviving a whole family of shocks. That turns a targeted patch into
structural repair, and it is the first thing we would build next.

## Built With

Python 3.13, numpy, pytest. MATLAB with the Global Optimization Toolbox (`patternsearch`), or
Optimization Toolbox alone (`fmincon`), for the
stabilisation solve. Python stdlib `http.server` for the API. Vanilla JavaScript and inline SVG for the
frontend, no framework and no build step. SEC EDGAR 13F-HR filings for holdings.

## What this does not claim

There is a **Model** page in the app — it is one of the six, in the nav — and it says all of this
on screen: eight rows, each tagged `measured`, `declared` or `not modelled`, filled from the live
payload so the leverage, band, γ and ADV it shows are the ones the numbers beside it were computed
with. We say them out loud as well.

We do not predict market moves. Firebreak computes a stability property of a declared configuration.

Leverage is not disclosed in 13F. `λ` is our parameter. The Model page prints the value every
number on screen was computed with — `Gross leverage · 5.0×` — and the API takes it as a knob. It
is not adjustable from the six pages; this build ships one declared configuration and shows you
what it is.

Neither is the breach band. `band` — how far over target leverage a fund runs before it is forced to
sell — is our parameter too, it defaults to 1.05, and it swings the headline number harder than
leverage or γ. It gets its own row on the Model page, printed as `Breach band · 1.05× target, so a
book sells above 5.25×`, because the most influential knob in a model should not be the least
visible one.

13F is long-only US equity, filed quarterly with a 45-day lag. It excludes shorts and derivatives.
Options rows are filtered out, rows are aggregated by CUSIP across internal managers, and our universe
is ten names. The books are real; they are not complete.

Price impact is not observable. `γ` is a declared parameter with a stated functional form — the
Model page prints `Price impact · γ = 0.2` and the form beside it — and ADV figures that are
order-of-magnitude public volumes. The finding is that the stability boundary exists and moves
predictably with leverage, not any single point estimate on it. Where that boundary sits in leverage
depends on the band as much as on anything we measured, so "you are here, right on the edge" is a
statement about a configuration we declared, not a discovery about the funds.

The fix solves one shock. `bought` reports what it buys against a re-run of the search, along with
the resolution of the search that measured it; at the demo settings the change is smaller than that
resolution, so we report "no measurable change" rather than a number. A targeted patch, not
structural repair. And "clears the failure condition" is not "nothing breaks" — two funds still
breach, which is fewer than the three we asked about.

No number is shown to more precision than the model supports.
