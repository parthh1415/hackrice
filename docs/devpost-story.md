# Minima — Devpost story

<!-- Paste everything below the rule into Devpost's story field. It is Markdown
     with LaTeX, which Devpost renders. Every figure in it comes from the
     committed dataset and can be reproduced with the commands in README.md —
     if the engine's answers move, this file is wrong and has to move with it. -->

---

## Inspiration

Every stress test we could find asks the same question: *what if NVDA drops 20%?*

The trouble is that the scenario is the part nobody checks. You pick a number, the model tells you what it costs, and you have learned something about a guess. The question a person actually has is the inverse — **"how bad does it have to get before I'm in trouble?"** — and almost nothing answers it.

The second thing that bothered us is that a portfolio's loss is not just its own loss. When a leveraged fund breaches its limit it is forced to sell, and it sells *across its whole book* — not just the name that fell. If you hold what it holds, the damage reaches you through names nobody shocked. That feedback is well documented in the literature (Greenwood, Landier & Thesmar, *Vulnerable Banks*, JFE 2015) and completely absent from anything a retail investor can open.

So: solve backwards, and count the contagion.

## What it does

You give Minima a portfolio — a CSV, parsed in your browser — and name the loss you refuse to accept. It answers four questions in order.

**Where does this break?** It searches every modelled name for the smallest single-name fall that pushes you past your limit. On the demo book that is **NVDA −25.05%**.

**Why is it worse than the fall?** At that shock the direct damage is **7.33%**. After five leveraged funds hit their limits and liquidate across their books over **3 rounds**, it is **10.00%** — **1.36× amplification**, and the extra arrives through names that were never shocked.

**What is the cheapest way out?** It searches every position for the smallest change that clears the limit: **move $472 of NVDA to cash — 13.1% of that position** — and the loss at the same shock falls to **9.00%**.

**Did that actually help?** A recommendation is not evidence, so the app replays the identical shock, recomputes the break point from scratch against the defended book (**−25.05% → −28.17%**, 3.12 points further away), and scores both portfolios across **400 simulated stresses on identical draws** — 395/400 stayed within the limit before, 398/400 after.

There is also a systemic map: 256 full cascades over a grid of leverage × crowding, showing where the whole configuration stops absorbing shocks and starts amplifying them.

## How we built it

The engine is a fixed-point iteration on balance sheets. Prices start at $1.00, so a 13F's dollar values *are* the unit counts.

A fund holds assets $A = \sum_i u_i p_i$ against debt $D$ fixed at $t_0$, so equity is $E = A - D$ and leverage is $\lambda = A/E$. Given a target $\lambda_0$, debt has to be $D = A(1 - 1/\lambda_0)$ for the arithmetic to close.

A fund breaches when $\lambda > \lambda_{\max}$, and must then raise

$$q = A - \lambda_{\text{target}} \cdot E$$

sold pro-rata across everything it holds. That selling moves prices by an Amihud-style linear impact,

$$p' = p \left(1 - \gamma \frac{V}{\text{ADV}}\right)$$

where $V$ is the dollar volume sold into that name this round. The new prices push other funds over *their* limits, and it goes again until nobody breaches.

Two details are load-bearing and both were wrong in our first version:

1. **Insolvency.** A fund with negative equity has $\lambda = A/E < 0$, so a naive $\lambda > \lambda_{\max}$ test is *false* and the most distressed fund in the system silently stops selling. That made damage non-monotone in shock size — bigger shock, fewer sellers, less damage — which makes "the smallest shock that breaks you" meaningless, because it isn't a threshold at all. Insolvent funds are treated as infinitely levered and liquidate everything.

2. **Execution price.** Selling is equity-neutral only if you get book prices for the whole block, which is exactly what a fire sale does not give you. Settled at book, a fund liquidating 100% of its holdings takes *zero* fire-sale loss — the funds causing the crash come out immune to it. Sales settle at the round's VWAP, $(p + p')/2$.

**The stack.** Python with NumPy for the engine, `http.server` for the API, and vanilla JavaScript for the frontend — no framework, no build step, no network. Every font and every byte of data is vendored, so the demo survives dead wifi.

**Real data.** SEC Form 13F-HR filings for Citadel, Millennium, Point72, Two Sigma and Renaissance, Q2 2026, mapped CUSIP → ticker across 18 names.

**MATLAB** does the institutional optimisation, because that problem earns it: the objective is a *simulation*, so it cannot be differentiated, and breach events make the landscape piecewise constant. That is what `patternsearch` exists for. It ran **1,569 full cascades** to find the cheapest single cut, and the Model page shows the search itself — best cost and mesh size against evaluations — drawn by MATLAB on the app's own palette. `cascade.m` is an independent reimplementation of the Python engine, and `boundary.m` recomputes all 256 cells and **refuses to draw the figure** if the two disagree by more than $10^{-4}$. They agree at **0.00e+00**.

## Research grounding, and how we checked it

This is not a model we invented. It is a published one, implemented from the primary literature, with the parts we could not verify labelled as such.

**The mechanism** — leverage-targeting institutions forced to deleverage, whose selling moves prices for everyone holding the same names — is Greenwood, Landier & Thesmar (2015), *Vulnerable banks* (553 citations). Their vulnerability accounting is what `src/minima/engine.py` computes: a shock, a leverage breach, a proportional sale, a price impact, and the same test again.

**The network** — why *overlapping portfolios* alone are enough to propagate a shock with no counterparty link at all — is Caccioli, Shrestha & Moore (2014) and Caccioli, Farmer & Foti (2015). The first predicts something specific and testable: *"there is a critical threshold for leverage; below it financial networks are always stable, and above it the unstable region grows as leverage increases."* Our Boundary page is that claim drawn from our own engine — 256 full cascades over leverage × crowding — and the cliff is there: at the filed overlap of 0.71 the five books absorb a 5% NVDA shock up to **4.53× leverage** and amplify it **1.93×** by **4.97×**. We did not fit that threshold; it fell out.

**The price impact** — $\Delta p / p = -\gamma \cdot V / \text{ADV}$ — is Amihud's ILLIQ form (2002, 3,415 citations), which as Amihud & Mendelson put it *"emulates Kyle's price impact measure. This measure estimates how much trading it takes to move the stock price by one unit."* We use dollar volume over ADV for exactly that reason.

**How we checked we implemented it rather than approximated it.** Three things, all falsifiable:

1. **The control.** At $\gamma = 0$ there is no impact, so there is no contagion, so amplification must be exactly $1.00\times$ — and it is. That is a test in the suite, not a claim.
2. **Two engines.** `cascade.m` is an independent MATLAB implementation of the same model. `boundary.m` recomputes all 256 cells and refuses to draw the figure if they disagree by more than $10^{-4}$. They agree at **0.00e+00**.
3. **The monotonicity the model demands.** A bigger shock must not produce *less* damage. Our first version broke this — insolvent funds have $\lambda < 0$ and silently stopped selling — and the suite now pins it, because a "smallest shock that breaks you" is meaningless if damage is not monotone in the shock.

**What we could not verify, stated plainly.** *Vulnerable banks* is paywalled and we could not read its price-impact specification, so we implemented the mechanism as described in the abstract and in the open citing literature, and calibrated impact the Amihud way. Two of our choices are ours, not theirs: sales settle at the round's VWAP rather than at book prices, and rounds are solver iterations rather than time steps. Both are documented in the code at the line that implements them, including the one place where the second assumption is only approximately true.

## Challenges we ran into

**Real filings are messy.** CUSIP → ticker is many-to-one: GOOGL arrives as Class A, Class C and two depositary-share lines, and summing them wrong quietly changes a name's weight. Amended filings (13F-HR/A) supersede originals rather than adding to them. Money-market lines are cash wearing a ticker.

**Our tests passed on broken code.** This was the real education. We ran mutation testing — deliberately break the engine, check the suite goes red — and found tests that *couldn't* fail. One compared a value to itself. One asserted over an empty set. One checked that a figure's filename was spelled right, which proved the page could spell and nothing else — while the figure had been silently 404ing and deleting itself for days. A test that cannot fail is worse than no test, because it is a claim of coverage.

**The bugs that looked like answers.** A `?limit=nan` came back as *"no shock in the tested range pushed this portfolio past the limit"* — our honest-negative wording, produced by a search that could never have succeeded, because every comparison against NaN is false. A short spelled as `-20` shares at `$180` priced fine while the same position spelled `-3600` was refused. Two `/api/stabilise` requests in flight together answered $2,236,598 or $2,251,028 depending on the traffic around them. None of these looked like errors. They looked like results.

**Getting MATLAB to exist.** The installer defaults to base MATLAB, so `patternsearch` simply isn't there and no amount of signing in changes it — a licence is an entitlement, not a download. That cost an hour and is now the first section of our MATLAB README.

## Accomplishments that we're proud of

**Two independent engines agreeing exactly.** `cascade.m` was written from the model, not ported line by line, and it matches Python to **0.00e+00 across 256 cells**. The figure refuses to render if that ever stops being true.

**A product that says what it does not know.** Every input on the Model page is labelled by where it came from: **one is measured, four are numbers we chose, three are outside the model entirely.** When you upload a book with names we cannot model, we refuse to score it and say what it would cost to exclude them, rather than dropping them and renormalising the rest around the hole. When no shock in range crosses your limit, we say *"that is the edge of what was tested, not a clean bill of health."*

**428 tests, and a harness that checks the tests.** 96 deliberate mutations of the engine and the interface — break this line, confirm the suite goes red — plus a test that fails if any mutation stops matching the code it targets, because a mutation that no longer applies is a coverage claim measuring nothing.

## What we learned

That **the honest failure mode is the hard one.** Anyone can catch a crash. What nearly shipped here were numbers that looked right: a cached answer served for a question nobody asked (off by 25.8× on the one line that tells somebody to trade), a `−0.00%`, a chart labelled `13%` whose axis topped out at 12.61%, an amplification of `1.00×` printed where the ratio was undefined. Each was a confident sentence about something that had not been computed.

And that **the fix is mechanical, not moral.** Don't proof-read — break the code and watch the test go red. We found more real defects in one afternoon of mutation testing than in three days of careful reading.

## What's next for Minima

**More of the market.** 18 names is the honest limit of what we hand-mapped; the same pipeline scales to the whole 13F universe, which turns "we cannot model VOO" into "here is your ETF's look-through."

**A band you can drag.** Our own review found the Boundary page is latent-correct for any breach band but that no control sends one — the engine has supported it all along.

**The institutional mode.** The same search with a different failure condition answers a risk desk's question — *which of my positions is the system's single point of failure* — and the engine already computes it. It needs a switch and a screen, not new math.

**Historical replay.** The one thing we refused to fake. We would rather show nothing than a backtest computed from returns we invented.

---

## References

Amihud, Y. (2002). Illiquidity and stock returns: cross-section and time-series effects. *Journal of Financial Markets, 5*(1), 31–56. https://doi.org/10.1016/S1386-4181(01)00024-6

Caccioli, F., Farmer, J. D., Foti, N., & Rockmore, D. (2015). Overlapping portfolios, contagion, and financial stability. *Journal of Economic Dynamics and Control, 51*, 50–63. https://doi.org/10.1016/j.jedc.2014.09.041

Caccioli, F., Shrestha, M., Moore, C., & Farmer, J. D. (2014). Stability analysis of financial contagion due to overlapping portfolios. *Journal of Banking & Finance, 46*, 233–245. https://doi.org/10.1016/j.jbankfin.2014.05.021

Greenwood, R., Landier, A., & Thesmar, D. (2015). Vulnerable banks. *Journal of Financial Economics, 115*(3), 471–485. https://doi.org/10.1016/j.jfineco.2014.11.006

Data: SEC Form 13F-HR filings, Q2 2026, via EDGAR — reproducible with `scripts/refresh_dataset.py`.
