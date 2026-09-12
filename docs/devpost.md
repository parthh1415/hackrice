# Firebreak

**Reverse stress testing for overlapping portfolios.** Not "what if NVDA drops 20%", but "what is the
smallest drop that breaks this system, and what is the cheapest change that prevents it".

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
in every cell rather than sketched.
It puts a marker on the configuration you are currently looking at: leverage 5.0, overlap 0.71 —
just past the leverage boundary, where amplification jumps from 1.00 to 1.86 between λ≈4.5 and
λ≈5.0. The question it answers is whether you got unlucky or whether you are standing somewhere
structurally bad. Worth saying plainly: *where* that boundary sits is a function of the breach band
we declared. At the same −5% reference, a band of 1.02 would put it near λ 2.4 and a band of 1.10
near λ 6.7. The shape of the map is the finding; the location of the marker on it is a consequence of
parameters we chose and show.

**The defence.** The inverse search. It scans every (fund, asset) position for the smallest reduction
that survives the *same* shock. The answer at these settings: **Millennium cuts its GOOGL position by
5%**, which is 0.04% of the system's gross assets — four basis points. Re-run NVDA −5.27% against the
patched books and the outcome goes from four breaches over three rounds to two breaches in one round,
final loss 9.12% down to **6.48%**, amplification 1.87 down to **1.33**.

**And then we say what the fix does not buy.** The stabilise response re-runs the reverse search
against the patched books and reports it. The critical shock moves from **−5.27% to −5.27%** — a
delta of **+0.00pp**. Four basis points of GOOGL survives *this* shock and buys essentially nothing
in structural terms. That is not a flaw we are hiding; it is the honest reading of a one-position,
one-shock optimiser, it is on the payload as `bought`, and a judge who clicks Find-weakest-shock
straight after Stabilise finds it in ten seconds. We would rather say it first. The genuine next
version minimises over a *family* of shocks rather than one, and that is a real piece of work, not a
slider.

The intervention is in GOOGL, not NVDA. That is the point of solving it rather than guessing. GOOGL is
the third most crowded name in the system, behind NVDA and AMZN, and Millennium is one of the two
funds whose round-one breach starts the chain. Cutting the shocked name would have been the obvious
move and it is not the cheapest one. Read it as a targeted patch for a named scenario, not as
structural repair.

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
UI**, with the solver name, evaluation count and exit flag on screen. We would rather show the fallback
than imply a solver we did not run.

**Frontend.** Vanilla JS and inline SVG on a stdlib `http.server`. No npm, no bundler, no CDN. Nothing
to install on a demo machine and nothing that breaks when conference wifi does. The cascade animation
reads `trajectory[t]` frame by frame; it never interpolates between precomputed endpoints, because the
animation is supposed to *be* the mechanism rather than illustrate it.

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
residual case at λ=3.0, γ=0.5 where MSFT −32% gives five breaches and −33% gives four, with nobody
insolvent, which is a VWAP and round-ordering effect rather than the original hole. Final *loss* is
non-monotone by design and we have a test that asserts it stays that way, so nobody later "fixes" it
into a claim we cannot support.

**The most important parameter was invisible.** The breach band — how far over its target leverage a
fund runs before it is forced to sell — was hardcoded at 1.05 while leverage and γ sat on sliders. It
moves the hero harder than either of them: band 1.02 gives NVDA −1.73% and amplification 3.10, band
1.30 gives NVDA −27.33% and 1.43. A five-fold swing in the headline number, controlled by a constant
nobody could see and nobody was declaring. It is a declared parameter now (`band`, default 1.05,
range 1.0–1.5), it comes back in the `params` block on every response, and it belongs in the
what-we-do-not-claim list next to leverage and γ.

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

**The GOOGL CUSIP was Alphabet Class C.** 02079K30 is GOOG. Class A, 02079K10, is a different CUSIP and
was being silently dropped. Because managers hold different Class A / Class C mixes, the undercount was
heterogeneous: 48% of Citadel's Alphabet position missing, 15% of Millennium's, 100% of Point72's. This
is the nastiest category of data bug, because nothing errors and nothing looks wrong. It just quietly
renormalises every other column in the weight matrix, per fund, by a different amount. GOOGL weights
moved by up to 9× when we fixed it, and the CUSIP map is many-to-one now.

**One firm, two registrants.** Two Sigma Investments and Two Sigma Advisers are separate CIKs filing
separate 13Fs for the same quarter, and our manager map held one CIK per name, so we were reading
half the firm. Nothing errored — we just had a smaller, differently-weighted Two Sigma book than the
real one. A manager now maps to a list of CIKs and the holdings are summed. Total book across the
five went from $38.4B to $40.9B.

**`13F-HR` did not match `13F-HR/A`.** Our "latest filing" filter was an exact string match on form
type, so a Citadel *restatement* of Q2 2026 was skipped and we spent a while reading superseded data as
if it were current. Form 13F FAQ 58 covers amendment semantics; we follow it now.

**The search asserted that zero shock was safe.** With the leverage slider pushed past the max-leverage
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

Eight of these eleven came out of handing the project to independent reviewers who had no stake in it
being right. Not one of them was found by a failing test — every single one produced a plausible
number and shipped.

## Accomplishments that we're proud of

The crowding is real and reproducible. Mean overlap 0.712 on filings anyone can download, with a
natural stable node (Point72, minimum pairwise overlap 0.44) so the demo shows a contrast instead of
everything turning red at once.

Point72's number. 2.8% exposure, 0.75% direct loss, 5.70% total. That single line is the whole thesis
about overlapping portfolios, and it came out of real filings rather than a constructed example.

The fix is non-obvious and it is *priced*. 0.04% of gross assets, in a name nobody shocked. Output is
a sentence a PM could act on, not a risk score — and we report what it does not buy in the same
breath.

Every number on screen is derivable, and we shipped honest magnitudes: amplification 1.87, not the
11.8 we could have had by leaving the broken metric in; a hero that prints only the digits the search
resolves; and a `bought` figure of +0.00pp on our own headline intervention, said out loud rather
than left for a judge to find.

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

And a metric that looks impressive deserves more suspicion than one that looks boring.

## What's next for Firebreak

Sparse multi-asset shocks, minimising `‖s‖₁` so the search can find the cheapest *pair* of names rather
than the cheapest single one. Real reverse stress testing is multi-dimensional.

Systemic-importance ranking per asset: which single name, if it moved, does the most damage per unit of
move, across the whole configuration space rather than at one slider setting.

Square-root price impact (`−Y σ √(V/ADV)`) alongside the linear form, so the boundary can be shown to
be robust to the functional form and not an artefact of it.

A bystander view. 13F holders are participants; a retail investor with no leverage cannot breach and
cannot be forced to sell, but still eats the price impact. Import a broker CSV, get an exposure
measurement. Exposure, never a prediction.

Robust defence, and this is the one that matters most. Our stabiliser minimises cost subject to
surviving *one named shock*, which is why the fix it finds buys +0.00pp of critical-shock headroom.
The right objective is to maximise the critical shock itself, or to minimise cost subject to
surviving a whole family of shocks. That turns a targeted patch into structural repair, and it is the
first thing we would build next.

## Built With

Python 3.13, numpy, pytest. MATLAB with the Global Optimization Toolbox (`patternsearch`) for the
stabilisation solve. Python stdlib `http.server` for the API. Vanilla JavaScript and inline SVG for the
frontend, no framework and no build step. SEC EDGAR 13F-HR filings for holdings.

## What this does not claim

These are stated here and said out loud in the demo. *(The in-app assumptions panel is not built —
the declared parameters are visible on the control strip and echoed in the `params` block of every
API response, but there is no panel in the UI rendering the bullets below. It is on the list.)*

We do not predict market moves. Firebreak computes a stability property of a declared configuration.

Leverage is not disclosed in 13F. `λ` is our parameter. It is visible and adjustable in the UI.

Neither is the breach band. `band` — how far over target leverage a fund runs before it is forced to
sell — is our parameter too, it defaults to 1.05, and it swings the headline number harder than
leverage or γ. Today it is set by URL rather than by a slider, which is the least visible place for
the most influential knob; every response declares the value it used.

13F is long-only US equity, filed quarterly with a 45-day lag. It excludes shorts and derivatives.
Options rows are filtered out, rows are aggregated by CUSIP across internal managers, and our universe
is ten names. The books are real; they are not complete.

Price impact is not observable. `γ` is a slider with a stated functional form and ADV figures that are
order-of-magnitude public volumes. The finding is that the stability boundary exists and moves
predictably with leverage, not any single point estimate on it. Where that boundary sits in leverage
depends on the band as much as on anything we measured, so "you are here, right on the edge" is a
statement about a configuration we declared, not a discovery about the funds.

The fix solves one shock. `bought` reports what it buys against a re-run of the search, and at the
demo settings that is +0.00pp. A targeted patch, not structural repair.

No number is shown to more precision than the model supports.
