# Firebreak — 3:30 shooting script

**This is what you read aloud.** `video-script.md` is the long reference: every number in it
is checked against a live run and it carries the shot-by-shot notes, but it is 1,143 words —
**7:37 of speech against a 3:42 cap.** This is 321.

Numbers verified live. If you change anything, re-check them before recording.

---

## ACT 1 — THE QUESTION (0:00 – 0:22)

**Shot 1** · Title, then the landing screen: *Find the market move your portfolio can't survive.*

> "Every stress test asks the same question. What if the market drops twenty percent? The
> scenario is an assumption — and the assumption is the part nobody checks."

**Shot 2** · Click **Try demo portfolio**. Holdings table fills.

> "Firebreak asks the inverse. Here's a portfolio. Fifteen thousand dollars, five names."

---

## ACT 2 — THE BREAK (0:22 – 1:20)

**Shot 3** · Click **Continue**, then **10%**.

> "How much loss would you refuse to tolerate? Ten percent. That's the whole configuration —
> no leverage, no gamma, no jargon."

**Shot 4** · Click **Find my Firebreak**. Let the search land.

> "NVIDIA, down twenty-four point seven percent. That's the smallest single-name move that
> pushes this portfolio past a ten percent loss. Nobody guessed it. It was solved for."

**Shot 5** · Point at the four readouts.

> "And here's the thing. NVIDIA falling only costs this portfolio seven point two directly.
> The loss is ten. Where did the other three points come from?"

---

## ACT 3 — WHY (1:20 – 2:05)

**Shot 6** · Click **Watch why**. Let the cascade play.

> "From everyone else. Crowded institutions hold the same names. NVIDIA falls, they breach
> their leverage limits, they're forced to sell — and they sell into a market where their
> positions are also *your* positions. That's the feedback. That's what turns seven into ten."

*(let a round land in silence)*

> "This is real filed data. Five hedge funds, their actual 13F holdings, forty billion dollars."

---

## ACT 4 — THE FIX AND THE PROOF (2:05 – 3:20)

**Shot 7** · Click **Find a fix**.

> "Now the useful part. Reduce NVIDIA by four hundred and seventy-eight dollars. That's the
> smallest change we found that survives this exact shock — and it moves to cash, so the
> portfolio is worth the same."

**Shot 8** · Click **Validate recommendation**.

> "But a recommendation isn't the end. How do you know it helped?"

> "Same shock, same assumptions, only the portfolio changed: ten percent becomes nine. Then we
> re-run the whole search on the new portfolio — the break point moves from twenty-four seven
> to twenty-seven eight. Three points further away."

**Shot 9** · Click through to **Simulated stress**, then **Historical**.

> "Four hundred simulated scenarios, both portfolios on identical draws. Worst case improves.
> And the historical tab says *not available* — we don't ship price history, so we won't show
> you a number we made up."

---

## ACT 5 — CLOSE (3:20 – 3:30)

**Shot 10** · Click **Risk Desk**.

> "Same engine, institutional question: what's the smallest move that forces three leveraged
> funds to deleverage at once? That's the prime brokerage version. Find the failure before it
> finds you."

---

## Timing

321 narration words. **2:08 at 150 wpm inside 3:42** — 94 seconds of headroom for the cascade to
play, the search to land, and you to breathe.

The headroom is the deliverable, not slack. A script with none doesn't get shorter when you read
it faster; it just gets delivered by someone visibly rushing. If the demo runs slower on the day
than it does here, this is what absorbs it.

(Counted with the same parser used on the long script. My first draft of this line said 430 — I
had estimated rather than counted, which on a page about not saying unverified numbers is the
wrong way round.)

## If you're long

Cut Act 5 (10s). Then Shot 9's second half. **Do not cut Shot 8** — the validation is the thing
that separates this from a visualisation, and the "not available" line is worth more to a judge
than any chart on the screen.

## If a number looks wrong on the day

Run `curl -s localhost:8765/api/portfolio/full?limit=0.10` and read the real ones. Do not say a
figure from this page that the screen is not showing.
