# Minima — Devpost story

<!-- Paste everything below the rule into Devpost's story field.

     MATH: $$ ... $$ only, never $ ... $. On the live page inline `$x$` printed
     as literal source while the $$ blocks rendered (they copy-pasted back as
     blank, which is what rendered math does). So every equation is a display
     block, and every symbol that appears mid-sentence is Unicode — λ γ Δ ×
     − ′ — which no renderer can drop.

     Every figure comes from the running engine. If the engine's answers move,
     this file is wrong and has to move with it. -->

---

## Inspiration

Every stress test asks the same question: *what if NVDA drops 20%?* But the scenario is the part nobody checks — you pick a number, the model prices it, and you have learned something about a guess. The question a person actually has is the inverse: **how bad does it have to get before I'm in trouble?**

And your loss is not just your loss. When a leveraged fund breaches its limit it is forced to sell, and it sells across its *whole* book — not just the name that fell. If you hold what it holds, the damage reaches you through names nobody shocked.

So: solve backwards, and count the contagion.

## What it does

You give Minima a portfolio — a CSV, parsed in your browser — and name the loss you refuse to accept. It answers four questions.

**Where does this break?** The smallest single-name fall that pushes you past your limit. On the demo book: **NVDA −25.05%**.

**Why is it worse than the fall?** At that shock the direct damage is **7.33%**. After five leveraged funds hit their limits and liquidate across their books over 3 rounds, it is **10.00%** — **1.36× amplification**, arriving through names that were never shocked.

**What is the cheapest way out?** **Move $472 of NVDA to cash, 13.1% of that position**, and the loss at the same shock falls to **9.00%**.

**Did that actually help?** A recommendation is not evidence. The app replays the identical shock, recomputes the break point from scratch against the defended book (−25.05% → −28.17%), and scores both portfolios across 400 simulated stresses on identical draws: **395/400 within limit before, 398/400 after**.

There is also a systemic map: 256 full cascades over a grid of leverage × crowding, showing where the configuration stops absorbing shocks and starts amplifying them.

## How we built it

A fixed-point iteration on balance sheets. Prices start at $1.00, so a 13F's dollar values *are* the unit counts. A fund holds assets A against debt D fixed at t₀, so its equity and leverage are

$$A = \sum_i u_i p_i, \qquad E = A - D, \qquad \lambda = \frac{A}{E}$$

It breaches when λ exceeds its ceiling, and must then raise

$$q = A - \lambda_{\text{target}} \cdot E$$

sold pro-rata across everything it holds. That selling moves prices by a linear impact,

$$\frac{\Delta p}{p} = -\gamma \cdot \frac{V}{\text{ADV}}$$

where V is the dollar volume sold into that name this round. The new prices push other funds over *their* limits, and it goes again until nobody breaches.

Two details are load-bearing, and both were wrong in our first version:

**Insolvency.** A fund with negative equity has λ = A/E < 0, so a naive λ > λmax test is *false* and the most distressed fund silently stops selling. That made damage non-monotone — bigger shock, fewer sellers, less damage — which makes "the smallest shock that breaks you" meaningless, because it isn't a threshold at all. Insolvent funds are treated as infinitely levered and liquidate everything.

**Execution price.** Settled at book prices, a fund liquidating 100% of its holdings takes *zero* fire-sale loss — the funds causing the crash come out immune to it. Sales settle at the round's VWAP instead:

$$p_{\text{exec}} = \frac{p + p'}{2}$$

**The stack.** Python and NumPy for the engine, `http.server` for the API, vanilla JavaScript for the frontend — no framework, no build step, no network. Every font and byte of data is vendored, so the demo survives dead wifi. Real SEC Form 13F-HR filings for Citadel, Millennium, Point72, Two Sigma and Renaissance, CUSIP → ticker across 18 names.

**MATLAB** does the institutional optimisation, because that problem earns it: the objective is a *simulation*, so it cannot be differentiated, and breach events make the landscape piecewise constant. That is what `patternsearch` is for. It ran 1,569 full cascades to find the cheapest single cut, and the Model page shows the search itself. `cascade.m` is an independent reimplementation of the Python engine; `boundary.m` recomputes all 256 cells and **refuses to draw the figure** if the two disagree by more than 1e-4. They agree at **0.00e+00**.

**It is a published model, not one we invented.** The deleveraging mechanism is Greenwood, Landier & Thesmar (2015). Overlapping portfolios as a contagion channel — no counterparty link required — is Caccioli et al. (2014, 2015), who predict *"a critical threshold for leverage; below it financial networks are always stable."* Our Boundary page is that prediction drawn from our own engine, and the cliff is there: at the filed overlap the five books absorb a 5% NVDA shock up to **4.53× leverage** and amplify it **1.93×** by **4.97×**. Nothing was fitted to put it there. The impact form is Amihud's ILLIQ (2002).

## Challenges we ran into

**Real filings are messy.** CUSIP → ticker is many-to-one — GOOGL arrives as Class A, Class C and two depositary-share lines, and summing them wrong quietly changes a name's weight. Amended filings supersede originals rather than adding to them. Money-market lines are cash wearing a ticker.

**Our tests passed on broken code.** We ran mutation testing — deliberately break the engine, check the suite goes red — and found tests that *couldn't* fail. One compared a value to itself. One asserted over an empty set. One checked a figure's filename was spelled right, which proved the page could spell and nothing else, while the figure had been silently 404ing and deleting itself for days.

**The bugs that looked like answers.** `?limit=nan` returned "no shock in the tested range pushed this portfolio past the limit" — our honest-negative wording, from a search that could never have succeeded, because every comparison against NaN is false. A short spelled as −20 shares at $180 priced fine while the same position spelled −3600 was refused. Two concurrent requests answered $2,236,598 or $2,251,028 depending on the traffic around them. None of these looked like errors. They looked like results.

## Accomplishments that we're proud of

**Two independent engines agreeing exactly.** `cascade.m` was written from the model, not ported line by line, and matches Python to 0.00e+00 across 256 cells. The figure refuses to render if that stops being true.

**A product that says what it does not know.** Every input is labelled by where it came from: one is measured, four are numbers we chose, three are outside the model entirely. Upload a book with names we cannot model and we refuse to score it, and price what excluding them would cost, rather than dropping them and renormalising around the hole. When nothing in range crosses your limit we say *"that is the edge of what was tested, not a clean bill of health."*

**428 tests, and a harness that checks the tests** — 96 deliberate mutations, plus a test that fails if any mutation stops matching the code it targets.

## What we learned

**The honest failure mode is the hard one.** Anyone can catch a crash. What nearly shipped were numbers that looked right: a cached answer served for a question nobody asked (off by 25.8× on the one line that tells somebody to trade), a −0.00%, a chart labelled 13% whose axis topped out at 12.61%, an amplification of 1.00× printed where the ratio was undefined. Each was a confident sentence about something that had not been computed.

**The fix is mechanical, not moral.** Don't proof-read — break the code and watch the test go red. We found more real defects in one afternoon of mutation testing than in three days of careful reading.

## What's next for Minima

**More of the market.** 18 names is the honest limit of what we hand-mapped; the same pipeline scales to the whole 13F universe, which turns "we cannot model VOO" into "here is your ETF's look-through."

**The institutional mode.** The same search with a different failure condition answers a risk desk's question — which position is the system's single point of failure — and the engine already computes it. It needs a switch and a screen, not new math.

**Historical replay.** The one thing we refused to fake. We would rather show nothing than a backtest computed from returns we invented.

---

**References.** Greenwood, R., Landier, A., & Thesmar, D. (2015). Vulnerable banks. *Journal of Financial Economics, 115*(3), 471–485. https://doi.org/10.1016/j.jfineco.2014.11.006 · Caccioli, F., Shrestha, M., Moore, C., & Farmer, J. D. (2014). Stability analysis of financial contagion due to overlapping portfolios. *Journal of Banking & Finance, 46*, 233–245. https://doi.org/10.1016/j.jbankfin.2014.05.021 · Caccioli, F., Farmer, J. D., Foti, N., & Rockmore, D. (2015). Overlapping portfolios, contagion, and financial stability. *Journal of Economic Dynamics and Control, 51*, 50–63. https://doi.org/10.1016/j.jedc.2014.09.041 · Amihud, Y. (2002). Illiquidity and stock returns. *Journal of Financial Markets, 5*(1), 31–56. https://doi.org/10.1016/S1386-4181(01)00024-6
